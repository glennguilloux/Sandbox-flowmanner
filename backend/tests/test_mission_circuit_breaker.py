"""Tests for mission circuit breaker (H5.4).

Covers:
- LLM call limit enforcement
- Cost USD limit enforcement
- Duration limit enforcement
- Per-agent tool call limits
- Destructive-action gate
- CircuitBreakerTrip exception details
- Limits.from_constraints() parsing
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.orchestration.circuit_breaker import (
    CircuitBreakerTrip,
    MissionCircuitBreaker,
    MissionLimits,
)


# ═══════════════════════════════════════════════════════════════════
# MissionLimits
# ═══════════════════════════════════════════════════════════════════


class TestMissionLimits:

    def test_defaults(self):
        limits = MissionLimits()
        assert limits.max_llm_calls == 150
        assert limits.max_cost_usd == 5.00
        assert limits.max_duration_seconds == 3600
        assert limits.max_tool_calls_per_agent == 50
        assert limits.destructive_actions_allowed is False

    def test_from_constraints(self):
        limits = MissionLimits.from_constraints({
            "max_llm_calls": 10,
            "max_cost_usd": 1.00,
            "destructive_actions_allowed": True,
        })
        assert limits.max_llm_calls == 10
        assert limits.max_cost_usd == 1.00
        assert limits.destructive_actions_allowed is True
        # defaults preserved
        assert limits.max_duration_seconds == 3600
        assert limits.max_tool_calls_per_agent == 50

    def test_from_constraints_none(self):
        limits = MissionLimits.from_constraints(None)
        assert limits.max_llm_calls == 150  # default


# ═══════════════════════════════════════════════════════════════════
# CircuitBreakerTrip
# ═══════════════════════════════════════════════════════════════════


class TestCircuitBreakerTrip:

    def test_exception_stores_limit_details(self):
        trip = CircuitBreakerTrip("too many calls", "max_llm_calls", 151, 150)
        assert trip.reason == "too many calls"
        assert trip.limit == "max_llm_calls"
        assert trip.current == 151
        assert trip.max_val == 150
        assert "151" in str(trip)
        assert "150" in str(trip)


# ═══════════════════════════════════════════════════════════════════
# LLM call limit
# ═══════════════════════════════════════════════════════════════════


class TestLLMCallLimit:

    def test_exceeding_calls_trips_breaker(self):
        limits = MissionLimits(max_llm_calls=3)
        breaker = MissionCircuitBreaker(limits=limits)

        breaker.record_llm_call()
        breaker.record_llm_call()
        breaker.record_llm_call()

        with pytest.raises(CircuitBreakerTrip) as exc:
            breaker.check()
        assert "max_llm_calls" in str(exc.value)

    def test_within_limit_passes(self):
        limits = MissionLimits(max_llm_calls=5)
        breaker = MissionCircuitBreaker(limits=limits)
        breaker.record_llm_call()
        breaker.record_llm_call()
        breaker.check()  # no exception


# ═══════════════════════════════════════════════════════════════════
# Cost limit
# ═══════════════════════════════════════════════════════════════════


class TestCostLimit:

    def test_exceeding_cost_trips_breaker(self):
        limits = MissionLimits(max_cost_usd=1.00)
        breaker = MissionCircuitBreaker(limits=limits)

        breaker.record_llm_call(cost=0.40)
        breaker.record_llm_call(cost=0.40)
        breaker.record_llm_call(cost=0.30)  # total = 1.10 > 1.00

        with pytest.raises(CircuitBreakerTrip) as exc:
            breaker.check()
        assert "max_cost_usd" in str(exc.value)

    def test_within_budget_passes(self):
        limits = MissionLimits(max_cost_usd=2.00)
        breaker = MissionCircuitBreaker(limits=limits)
        breaker.record_llm_call(cost=1.99)
        breaker.check()  # no exception (1.99 < 2.00)


# ═══════════════════════════════════════════════════════════════════
# Duration limit
# ═══════════════════════════════════════════════════════════════════


class TestDurationLimit:

    def test_exceeding_duration_trips_breaker(self):
        limits = MissionLimits(max_duration_seconds=1)
        breaker = MissionCircuitBreaker(limits=limits)

        # Set started_at in the past
        breaker.started_at = datetime.now(timezone.utc) - timedelta(seconds=2)

        with pytest.raises(CircuitBreakerTrip) as exc:
            breaker.check()
        assert "max_duration_seconds" in str(exc.value)

    def test_within_duration_passes(self):
        limits = MissionLimits(max_duration_seconds=3600)
        breaker = MissionCircuitBreaker(limits=limits)
        breaker.check()  # just started, well within limit


# ═══════════════════════════════════════════════════════════════════
# Per-agent tool call limit
# ═══════════════════════════════════════════════════════════════════


class TestAgentToolCallLimit:

    def test_exceeding_agent_calls_trips_breaker(self):
        limits = MissionLimits(max_tool_calls_per_agent=2)
        breaker = MissionCircuitBreaker(limits=limits)

        breaker.record_tool_call("agent-1")
        breaker.record_tool_call("agent-1")

        with pytest.raises(CircuitBreakerTrip) as exc:
            breaker.check(agent_id="agent-1")
        assert "agent-1" in str(exc.value)
        assert "tool call" in str(exc.value).lower()

    def test_separate_agents_independent(self):
        limits = MissionLimits(max_tool_calls_per_agent=2)
        breaker = MissionCircuitBreaker(limits=limits)

        breaker.record_tool_call("agent-1")
        breaker.record_tool_call("agent-1")
        breaker.record_tool_call("agent-2")

        # agent-1 is at limit but we check agent-2
        breaker.check(agent_id="agent-2")  # no exception

        # agent-1 at limit → trips
        with pytest.raises(CircuitBreakerTrip):
            breaker.check(agent_id="agent-1")


# ═══════════════════════════════════════════════════════════════════
# Destructive-action gate
# ═══════════════════════════════════════════════════════════════════


class TestDestructiveActionGate:

    def test_destructive_action_blocked_by_default(self):
        limits = MissionLimits(destructive_actions_allowed=False)
        breaker = MissionCircuitBreaker(limits=limits)

        with pytest.raises(CircuitBreakerTrip) as exc:
            breaker.check(action_type="destructive_delete")
        assert "Destructive" in str(exc.value)

    def test_destructive_action_allowed_when_gate_open(self):
        limits = MissionLimits(destructive_actions_allowed=True)
        breaker = MissionCircuitBreaker(limits=limits)
        breaker.check(action_type="destructive_delete")  # no exception

    def test_explicit_destructive_action_types_blocked(self):
        for action in ("delete_file", "drop_table"):
            limits = MissionLimits(destructive_actions_allowed=False)
            breaker = MissionCircuitBreaker(limits=limits)
            with pytest.raises(CircuitBreakerTrip):
                breaker.check(action_type=action)

    def test_non_destructive_actions_pass(self):
        limits = MissionLimits(destructive_actions_allowed=False)
        breaker = MissionCircuitBreaker(limits=limits)
        breaker.check(action_type="read_file")  # no exception
        breaker.check(action_type="search")     # no exception


# ═══════════════════════════════════════════════════════════════════
# Status
# ═══════════════════════════════════════════════════════════════════


class TestBreakerStatus:

    def test_status_reports_current_state(self):
        limits = MissionLimits(max_llm_calls=10)
        breaker = MissionCircuitBreaker(limits=limits)
        breaker.record_llm_call(cost=0.50)

        s = breaker.status()
        assert s["llm_calls"] == 1
        assert s["cost_usd"] == 0.50
        assert "elapsed_seconds" in s
        assert s["limits"]["max_llm_calls"] == 10
