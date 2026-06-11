"""H3.3 Chaos Test Suite — CI-enforced durability, security, and bounded-execution tests.

Per Ω spec VII.14: these 7 tests run on every PR and verify the four guarantees:
1. Durable:       test_kill_worker_mid_mission, test_replay_yields_same_state
2. Type-checked:   test_type_violation_rejected
3. Capability-bounded: test_revoke_capability_mid_run, test_attenuation_preserves_subset,
                       test_no_ambient_authority
4. Bounded:        test_exhaust_budget

All tests must pass for CI to be green (Invariant I.19).
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID, uuid4

import pytest

# ═══════════════════════════════════════════════════════════════════
# Test 1: Kill worker mid-mission (Durable execution)
# ═══════════════════════════════════════════════════════════════════


class TestKillWorkerMidMission:
    """Verify that the event-sourced substrate survives worker crashes.

    Start a run, record events for 3 nodes, then simulate a crash by
    rebuilding state from the event log.  Verify the resumed state matches.
    """

    def test_event_structure_and_types(self):
        """Substrate events can be constructed with correct types."""
        from app.models.substrate_models import SubstrateEventType

        run_id = str(uuid4())
        events = [
            {
                "type": SubstrateEventType.MISSION_STARTED,
                "payload": {"title": "test"},
                "actor": "test",
            },
            {
                "type": SubstrateEventType.TASK_STARTED,
                "payload": {"task_id": "t1"},
                "actor": "test",
            },
            {
                "type": SubstrateEventType.TASK_COMPLETED,
                "payload": {"task_id": "t1", "tokens": 42},
                "actor": "test",
            },
        ]

        # Verify events can be constructed (append needs DB, but construction doesn't)
        from app.models.substrate_models import SubstrateEvent

        for event_dict in events:
            event = SubstrateEvent(
                id=str(uuid4()),
                sequence=0,
                run_id=run_id,
                type=event_dict["type"],
                payload=event_dict.get("payload", {}),
                actor=event_dict.get("actor", "system"),
            )
            assert event.run_id == run_id
            assert event.type in {
                SubstrateEventType.MISSION_STARTED,
                SubstrateEventType.TASK_STARTED,
                SubstrateEventType.TASK_COMPLETED,
            }

    def test_run_state_rebuilds_from_events(self):
        """RunState.apply() correctly processes each event type."""
        from app.models.substrate_models import (
            SubstrateEvent,
            SubstrateEventType,
            SubstrateRunState,
        )

        run_id = str(uuid4())
        state = SubstrateRunState(run_id=run_id)

        # Apply mission.started
        state.apply(
            SubstrateEvent(
                id=str(uuid4()),
                sequence=1,
                run_id=run_id,
                type=SubstrateEventType.MISSION_STARTED,
                payload={"title": "test"},
                actor="test",
            )
        )
        assert state.status == "executing"

        # Apply task.started
        state.apply(
            SubstrateEvent(
                id=str(uuid4()),
                sequence=2,
                run_id=run_id,
                type=SubstrateEventType.TASK_STARTED,
                payload={"task_id": "t1"},
                actor="test",
            )
        )
        assert state.task_states.get("t1", {}).get("status") == "running"

        # Apply task.completed
        state.apply(
            SubstrateEvent(
                id=str(uuid4()),
                sequence=3,
                run_id=run_id,
                type=SubstrateEventType.TASK_COMPLETED,
                payload={"task_id": "t1", "tokens": 42, "cost_usd": 0.01},
                actor="test",
            )
        )
        assert "t1" in state.completed_tasks
        assert state.total_tokens == 42
        assert state.total_cost_usd == 0.01

        # Apply mission.failed (simulate crash after completion)
        state2 = SubstrateRunState(run_id=run_id)
        state2.apply(
            SubstrateEvent(
                id=str(uuid4()),
                sequence=4,
                run_id=run_id,
                type=SubstrateEventType.MISSION_FAILED,
                payload={"error": "worker crash"},
                actor="test",
            )
        )
        assert state2.status == "failed"
        assert state2.error_message == "worker crash"

    def test_apply_is_deterministic(self):
        """SubstrateRunState.apply() is a pure function — same events → same state."""
        from app.models.substrate_models import (
            SubstrateEvent,
            SubstrateEventType,
            SubstrateRunState,
        )

        run_id = str(uuid4())
        events_data = [
            (SubstrateEventType.MISSION_STARTED, {"title": "replay_test"}),
            (SubstrateEventType.TASK_STARTED, {"task_id": "a"}),
            (
                SubstrateEventType.TASK_COMPLETED,
                {"task_id": "a", "tokens": 100, "cost_usd": 0.05},
            ),
            (SubstrateEventType.TASK_STARTED, {"task_id": "b"}),
            (SubstrateEventType.TASK_FAILED, {"task_id": "b", "error": "timeout"}),
            (SubstrateEventType.MISSION_COMPLETED, {}),
        ]

        def build_state():
            state = SubstrateRunState(run_id=run_id)
            for seq, (etype, payload) in enumerate(events_data, start=1):
                state.apply(
                    SubstrateEvent(
                        id=str(uuid4()),
                        sequence=seq,
                        run_id=run_id,
                        type=etype,
                        payload=payload,
                        actor="test",
                    )
                )
            return state

        state1 = build_state()
        state2 = build_state()

        assert state1.status == state2.status == "completed"
        assert state1.completed_tasks == state2.completed_tasks == {"a"}
        assert state1.failed_tasks == state2.failed_tasks == {"b"}
        assert state1.total_tokens == state2.total_tokens == 100
        assert state1.current_sequence == state2.current_sequence == 6


# ═══════════════════════════════════════════════════════════════════
# Test 2: Revoke capability mid-run (OCap security)
# ═══════════════════════════════════════════════════════════════════


class TestRevokeCapabilityMidRun:
    """Verify that capability revocation takes effect immediately."""

    def test_token_revocation_blocks_action(self):
        """A revoked token can() returns False for all actions."""
        from app.models.capability_models import Action, CapabilityToken, ResourceRef

        token = CapabilityToken(
            resource=ResourceRef(kind="tool", name="web_search"),
            actions={Action.EXECUTE, Action.READ},
            issued_to=uuid4(),
        )

        assert token.can(Action.EXECUTE) is True
        assert token.can(Action.READ) is True

        token.revoked = True

        assert token.can(Action.EXECUTE) is False
        assert token.can(Action.READ) is False

    def test_cascading_revoke(self):
        """Revoking a parent revokes all descendant tokens."""
        from app.models.capability_models import Action
        from app.services.capability_engine import (
            CapabilityEngine,
            reset_capability_engine,
        )

        reset_capability_engine()
        engine = CapabilityEngine()

        agent_id = uuid4()
        from app.models.capability_models import ResourceRef

        parent = engine.issue(
            resource=ResourceRef(kind="tool", name="dangerous_tool"),
            actions={Action.EXECUTE},
            to=agent_id,
        )
        child = engine.attenuate(parent, remove_actions=set())

        assert parent.id != child.id
        assert child.parent == parent.id
        assert engine.verify(parent, Action.EXECUTE) is True
        assert engine.verify(child, Action.EXECUTE) is True

        # Revoke parent — should cascade
        revoked_count = engine.revoke(parent.id, "mid-run revocation", cascade=True)
        assert revoked_count >= 2  # parent + child

        # Both tokens should now be rejected
        assert engine.verify(parent, Action.EXECUTE) is False
        assert engine.verify(child, Action.EXECUTE) is False

    def test_revoked_token_raises_on_verify_and_require(self):
        """verify_and_require raises PermissionError for revoked tokens."""
        from app.models.capability_models import Action
        from app.services.capability_engine import (
            CapabilityEngine,
            reset_capability_engine,
        )

        reset_capability_engine()
        engine = CapabilityEngine()

        agent_id = uuid4()
        from app.models.capability_models import ResourceRef

        token = engine.issue(
            resource=ResourceRef(kind="tool", name="test_tool"),
            actions={Action.EXECUTE},
            to=agent_id,
        )
        engine.revoke(token.id, "test revocation")

        with pytest.raises(PermissionError, match="revoked"):
            engine.verify_and_require(token, Action.EXECUTE)


# ═══════════════════════════════════════════════════════════════════
# Test 3: Exhaust budget (Bounded execution)
# ═══════════════════════════════════════════════════════════════════


class TestExhaustBudget:
    """Verify that the budget enforcer aborts when limits are hit."""

    def test_budget_exhausted_on_cost(self):
        """Budget.is_exhausted() returns True when cost limit is hit."""
        from app.models.capability_models import Budget

        budget = Budget(
            max_cost_usd=Decimal("1.00"),
            max_wall_time_seconds=60,
            max_iterations=100,
        )
        assert budget.is_exhausted() == (False, "")

        budget.spent_usd = Decimal("1.00")
        is_exhausted, reason = budget.is_exhausted()
        assert is_exhausted is True
        assert "Cost budget exhausted" in reason

    def test_budget_exhausted_on_iterations(self):
        """Budget.is_exhausted() returns True when iteration limit is hit."""
        from app.models.capability_models import Budget

        budget = Budget(max_iterations=3)
        budget.iterations_used = 3
        is_exhausted, reason = budget.is_exhausted()
        assert is_exhausted is True
        assert "Iteration budget exhausted" in reason

    def test_budget_exhausted_on_depth(self):
        """Budget.is_exhausted() returns True when depth limit is hit."""
        from app.models.capability_models import Budget

        budget = Budget(max_depth=2)
        budget.depth_used = 2
        is_exhausted, reason = budget.is_exhausted()
        assert is_exhausted is True
        assert "Depth budget exhausted" in reason

    def test_budget_exhausted_exception(self):
        """BudgetExhausted carries the reason and remaining budget."""
        from app.models.capability_models import Budget, BudgetExhausted

        budget = Budget(max_cost_usd=Decimal("0.50"))
        budget.spent_usd = Decimal("0.50")

        with pytest.raises(BudgetExhausted) as exc_info:
            is_exhausted, reason = budget.is_exhausted()
            if is_exhausted:
                raise BudgetExhausted(reason, budget)

        assert "0.50" in str(exc_info.value)

    def test_pricing_table_estimate(self):
        """PricingTable correctly estimates costs for known models."""
        from app.services.budget_enforcer import PricingTable

        pricing = PricingTable()

        # DeepSeek
        cost = pricing.estimate("deepseek-chat", 1000, 500)
        assert cost > Decimal("0")

        # Local (free)
        cost = pricing.estimate("llamacpp-qwen3.6-27b", 10000, 5000)
        assert cost == Decimal("0")

        # Unknown model falls back to default
        cost = pricing.estimate("unknown-model", 1000, 500)
        assert cost > Decimal("0")

    def test_budget_enforcer_check_rejects_overspend(self):
        """BudgetEnforcer.check_budget() rejects calls that would overspend."""
        from decimal import Decimal

        from app.models.capability_models import Budget
        from app.services.budget_enforcer import BudgetEnforcer

        enforcer = BudgetEnforcer()
        budget = Budget(max_cost_usd=Decimal("0.01"))

        # Call that would cost more than remaining
        assert enforcer.check_budget(budget, Decimal("0.02")) is False

        # Call within budget
        assert enforcer.check_budget(budget, Decimal("0.005")) is True


# ═══════════════════════════════════════════════════════════════════
# Test 4: Type violation rejected (Type-checked composition)
# ═══════════════════════════════════════════════════════════════════


class TestTypeViolationRejected:
    """Verify that the type system rejects invalid compositions."""

    def test_pydantic_adapter_validates_input(self):
        """PydanticAdapter.validate_input catches missing required fields."""
        from app.models.capability_models import (
            Capability,
            PydanticAdapter,
        )

        cap = Capability(
            id="test:tool",
            name="Test",
            description="A test capability",
            category="test",
        )
        cap.__dict__["__input_schema__"] = {
            "required": ["query"],
            "properties": {
                "query": {"type": "string"},
                "limit": {"type": "integer"},
            },
        }

        # Missing required field
        is_valid, error = PydanticAdapter.validate_input(cap, {"limit": 5})
        assert is_valid is False
        assert "query" in error

        # Valid input
        is_valid, error = PydanticAdapter.validate_input(cap, {"query": "hello", "limit": 5})
        assert is_valid is True
        assert error is None

        # Type mismatch
        is_valid, error = PydanticAdapter.validate_input(cap, {"query": "hello", "limit": "not_a_number"})
        assert is_valid is False
        assert "limit" in error

    def test_capability_lattice_rejects_cycles(self):
        """CapabilityLattice detects and rejects cycles in composition."""
        from app.services.nexus.capability_lattice import (
            CapabilityLattice,
            CompositionType,
            LatticeError,
        )

        lattice = CapabilityLattice(max_depth=5)

        # Register leaves
        lattice.register_leaf("a", "Leaf A")
        lattice.register_leaf("b", "Leaf B")

        # Register a → b composition
        lattice.register_composed("ab", "A→B", ["a", "b"], CompositionType.SEQUENTIAL)

        # Try to register a composition where "a" depends on "ab",
        # but "ab" already depends on "a" — this creates a cycle: a → ab → a
        with pytest.raises(LatticeError, match="Cycle"):
            lattice.register_composed("a", "A→AB", ["ab"], CompositionType.SEQUENTIAL)

    def test_capability_lattice_enforces_max_depth(self):
        """CapabilityLattice rejects compositions that exceed max_depth."""
        from app.services.nexus.capability_lattice import (
            CapabilityLattice,
            CompositionType,
            LatticeError,
        )

        lattice = CapabilityLattice(max_depth=2)

        # Depth 0 leaf
        lattice.register_leaf("x", "Leaf X")
        lattice.register_leaf("y", "Leaf Y")

        # Depth 1: compose x with y (SEQUENTIAL: depth = 1 + 0 + 0 = 1)
        lattice.register_composed("xy", "X-Y", ["x", "y"], CompositionType.SEQUENTIAL)

        # Depth 2: compose xy with x (SEQUENTIAL: depth = 1 + 1 + 0 = 2) — within limit
        lattice.register_composed("xyx", "XY-X", ["xy", "x"], CompositionType.SEQUENTIAL)

        # Depth would be 1 + sum(2 + 1) = 4 > max_depth 2 — REJECTED
        with pytest.raises(LatticeError, match="exceeds max_depth"):
            lattice.register_composed("deep", "Deep", ["xyx", "xy"], CompositionType.SEQUENTIAL)


# ═══════════════════════════════════════════════════════════════════
# Test 5: Replay yields same state (Deterministic replay)
# ═══════════════════════════════════════════════════════════════════


class TestReplayYieldsSameState:
    """Verify that replaying the event log produces identical state."""

    def test_full_mission_replay(self):
        """A complete mission lifecycle replays deterministically."""
        from app.models.substrate_models import (
            SubstrateEvent,
            SubstrateEventType,
            SubstrateRunState,
        )

        run_id = str(uuid4())

        def build_full_run():
            state = SubstrateRunState(run_id=run_id)
            events = [
                (SubstrateEventType.MISSION_STARTED, {"title": "deterministic_test"}),
                (SubstrateEventType.TASK_STARTED, {"task_id": "t1"}),
                (
                    SubstrateEventType.TASK_COMPLETED,
                    {"task_id": "t1", "tokens": 150, "cost_usd": 0.02},
                ),
                (SubstrateEventType.TASK_STARTED, {"task_id": "t2"}),
                (
                    SubstrateEventType.TASK_COMPLETED,
                    {"task_id": "t2", "tokens": 200, "cost_usd": 0.03},
                ),
                (SubstrateEventType.MISSION_COMPLETED, {}),
            ]
            for seq, (etype, payload) in enumerate(events, start=1):
                state.apply(
                    SubstrateEvent(
                        id=str(uuid4()),
                        sequence=seq,
                        run_id=run_id,
                        type=etype,
                        payload=payload,
                        actor="test",
                    )
                )
            return state

        state1 = build_full_run()
        state2 = build_full_run()

        assert state1.status == state2.status
        assert state1.completed_tasks == state2.completed_tasks
        assert state1.total_tokens == state2.total_tokens
        assert state1.total_cost_usd == state2.total_cost_usd
        assert state1.current_sequence == state2.current_sequence

    def test_partial_replay_at_sequence(self):
        """State at sequence 3 is consistent regardless of later events."""
        from app.models.substrate_models import (
            SubstrateEvent,
            SubstrateEventType,
            SubstrateRunState,
        )

        run_id = str(uuid4())
        events = [
            (SubstrateEventType.MISSION_STARTED, {"title": "partial"}),
            (SubstrateEventType.TASK_STARTED, {"task_id": "t1"}),
            (
                SubstrateEventType.TASK_COMPLETED,
                {"task_id": "t1", "tokens": 50, "cost_usd": 0.01},
            ),
            (SubstrateEventType.TASK_STARTED, {"task_id": "t2"}),
            (SubstrateEventType.MISSION_FAILED, {"error": "later error"}),
        ]

        # Replay only first 3 events
        state = SubstrateRunState(run_id=run_id)
        for seq, (etype, payload) in enumerate(events[:3], start=1):
            state.apply(
                SubstrateEvent(
                    id=str(uuid4()),
                    sequence=seq,
                    run_id=run_id,
                    type=etype,
                    payload=payload,
                    actor="test",
                )
            )

        assert state.status == "executing"  # not failed yet
        assert "t1" in state.completed_tasks
        assert state.total_tokens == 50


# ═══════════════════════════════════════════════════════════════════
# Test 6: Attenuation preserves subset (OCap attenuation)
# ═══════════════════════════════════════════════════════════════════


class TestAttenuationPreservesSubset:
    """Verify that attenuated tokens have strictly subset actions."""

    def test_attenuation_removes_actions(self):
        """Attenuating a token produces a child with fewer actions."""
        from app.models.capability_models import Action, CapabilityToken, ResourceRef

        parent = CapabilityToken(
            resource=ResourceRef(kind="tool", name="powerful_tool"),
            actions={Action.READ, Action.WRITE, Action.EXECUTE, Action.DELEGATE},
            issued_to=uuid4(),
        )

        child = parent.attenuate(remove_actions={Action.WRITE, Action.DELEGATE})

        assert child.actions == {Action.READ, Action.EXECUTE}
        assert child.actions.issubset(parent.actions)
        assert child.parent == parent.id
        assert child.id != parent.id

    def test_attenuation_preserves_subset_invariant(self):
        """Child actions are always a strict subset of parent actions."""
        from app.models.capability_models import Action, CapabilityToken, ResourceRef

        parent = CapabilityToken(
            resource=ResourceRef(kind="tool", name="test_tool"),
            actions={Action.EXECUTE},
            issued_to=uuid4(),
        )

        # Empty removal = same actions (still a subset)
        child = parent.attenuate(remove_actions=set())
        assert child.actions == parent.actions
        assert child.actions.issubset(parent.actions)

    def test_attenuation_preserves_expiry(self):
        """Child inherits parent's expiry unless overridden."""
        from app.models.capability_models import Action, CapabilityToken, ResourceRef

        parent_expiry = datetime.now(UTC) + timedelta(hours=1)
        parent = CapabilityToken(
            resource=ResourceRef(kind="tool", name="timed_tool"),
            actions={Action.EXECUTE},
            issued_to=uuid4(),
            expires_at=parent_expiry,
        )

        child = parent.attenuate(remove_actions=set())
        assert child.expires_at == parent_expiry

        child_expiry = datetime.now(UTC) + timedelta(minutes=5)
        child2 = parent.attenuate(remove_actions=set(), expires_at=child_expiry)
        assert child2.expires_at == child_expiry

    def test_attenuation_engine_integration(self):
        """CapabilityEngine.attenuate() produces valid, persisted child."""
        from app.models.capability_models import Action
        from app.services.capability_engine import (
            CapabilityEngine,
            reset_capability_engine,
        )

        reset_capability_engine()
        engine = CapabilityEngine()

        agent_id = uuid4()
        from app.models.capability_models import ResourceRef

        parent = engine.issue(
            resource=ResourceRef(kind="tool", name="full_access_tool"),
            actions={Action.READ, Action.WRITE, Action.EXECUTE},
            to=agent_id,
        )

        child = engine.attenuate(parent, remove_actions={Action.WRITE})

        assert child.actions == {Action.READ, Action.EXECUTE}
        assert child.parent == parent.id
        assert engine.verify(child, Action.READ) is True
        assert engine.verify(child, Action.WRITE) is False  # attenuated away


# ═══════════════════════════════════════════════════════════════════
# Test 7: No ambient authority (OCap enforcement)
# ═══════════════════════════════════════════════════════════════════


class TestNoAmbientAuthority:
    """Verify that the runtime refuses tool invocation without a valid token."""

    def test_verify_and_require_raises_for_none_token(self):
        """Calling verify_and_require with None raises PermissionError."""
        from app.models.capability_models import Action
        from app.services.capability_engine import (
            CapabilityEngine,
            reset_capability_engine,
        )

        reset_capability_engine()
        engine = CapabilityEngine()

        with pytest.raises(PermissionError, match="No capability token"):
            engine.verify_and_require(None, Action.EXECUTE)

    def test_verify_and_require_raises_for_expired_token(self):
        """An expired token raises PermissionError."""
        from app.models.capability_models import Action
        from app.services.capability_engine import (
            CapabilityEngine,
            reset_capability_engine,
        )

        reset_capability_engine()
        engine = CapabilityEngine()

        agent_id = uuid4()
        from app.models.capability_models import ResourceRef

        token = engine.issue(
            resource=ResourceRef(kind="tool", name="expired_tool"),
            actions={Action.EXECUTE},
            to=agent_id,
            expires_at=datetime.now(UTC) - timedelta(hours=1),  # already expired
        )

        with pytest.raises(PermissionError, match="expired"):
            engine.verify_and_require(token, Action.EXECUTE)

    def test_verify_and_require_passes_for_valid_token(self):
        """A valid, active token passes verification."""
        from app.models.capability_models import Action
        from app.services.capability_engine import (
            CapabilityEngine,
            reset_capability_engine,
        )

        reset_capability_engine()
        engine = CapabilityEngine()

        agent_id = uuid4()
        from app.models.capability_models import ResourceRef

        token = engine.issue(
            resource=ResourceRef(kind="tool", name="valid_tool"),
            actions={Action.EXECUTE},
            to=agent_id,
        )

        # Should not raise
        verified = engine.verify_and_require(token, Action.EXECUTE)
        assert verified is token

    def test_engine_issue_rejects_empty_actions(self):
        """Cannot issue a token with no actions."""
        from app.models.capability_models import Action
        from app.services.capability_engine import (
            CapabilityEngine,
            reset_capability_engine,
        )

        reset_capability_engine()
        engine = CapabilityEngine()

        from app.models.capability_models import ResourceRef

        with pytest.raises(ValueError, match="no actions"):
            engine.issue(
                resource=ResourceRef(kind="tool", name="empty_tool"),
                actions=set(),
                to=uuid4(),
            )

    def test_unified_tool_bridge_ocap_enforcement(self):
        """UnifiedToolBridge raises CapabilityRequiredError without a token."""
        from app.services.unified_tool_bridge import (
            CapabilityRequiredError,
            UnifiedToolBridge,
        )

        bridge = UnifiedToolBridge(ocap_enabled=True)

        # Without a capability token, execution should be rejected
        with pytest.raises(CapabilityRequiredError, match="Capability token required"):
            asyncio.run(bridge.verify_capability("test_tool", None))
