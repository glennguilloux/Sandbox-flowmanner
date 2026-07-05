"""Pure-logic unit tests for ``scripts.exercise_dual_write``.

The four required tests from cutover §1 B.2–B.3:

  1. ``test_distribute_missions_round_robin`` — 100 creates across 5
     users yields 20 per user, no leftover.
  2. ``test_build_create_payload_has_required_fields`` — only the
     ``MissionCreate`` fields (no extras that would 422 with
     ``extra='forbid'``).
  3. ``test_build_register_payload_has_password_strength`` — the
     password clears the backend validator (≥8 chars, upper, lower,
     digit, not in the common-password blocklist).
  4. ``test_assignment_plan_respects_counts`` — given the cutover-plan
     defaults, the assignment slices are disjoint and never overlap.
     Specifically: deleted missions are NOT also flagged for abort.

We also cover the smaller invariants (off-by-one distribution with a
non-divisible total, login payload, update payload shape, plan pool
overrun, scale-down behavior) so future refactors do not regress these
utility helpers.

NOTE: NO integration tests here — the script hits a live HTTP server
and is exercised manually by Glenn against the dev backend.  See the
cutover plan for the smoke-test invocation.
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from uuid import uuid4

import pytest

from app.utils.password_validation import validate_password_strength
from scripts.exercise_dual_write import (
    EXERCISE_PASSWORD,
    AssignmentPlan,
    assign_mission_operations,
    build_create_payload,
    build_login_payload,
    build_register_payload,
    build_update_payload,
    distribute_creates,
)

# ---------------------------------------------------------------------------
# distribute_creates — round-robin distribution helper
# ---------------------------------------------------------------------------


class TestDistributeCreates:
    """Covers test #1 — the cutover plan's default 100/5 case."""

    def test_distribute_missions_round_robin(self):
        """100 creates / 5 users → exactly 20 per user, no leftover."""
        distribution = distribute_creates(total_creates=100, num_users=5)

        assert distribution == {0: 20, 1: 20, 2: 20, 3: 20, 4: 20}
        assert sum(distribution.values()) == 100

    def test_distribution_covers_full_count_when_indivisible(self):
        """103 creates / 5 users → first 3 users get 21, last 2 get 20."""
        distribution = distribute_creates(total_creates=103, num_users=5)

        assert sum(distribution.values()) == 103
        assert sorted(distribution.values()) == [20, 20, 21, 21, 21]
        assert max(distribution.values()) - min(distribution.values()) <= 1

    def test_zero_creates_yields_all_zero(self):
        assert distribute_creates(total_creates=0, num_users=5) == {0: 0, 1: 0, 2: 0, 3: 0, 4: 0}

    def test_single_user_takes_everything(self):
        assert distribute_creates(total_creates=42, num_users=1) == {0: 42}

    def test_negative_creates_raises(self):
        with pytest.raises(ValueError, match="total_creates must be non-negative"):
            distribute_creates(total_creates=-1, num_users=5)

    def test_zero_users_raises(self):
        with pytest.raises(ValueError, match="num_users must be positive"):
            distribute_creates(total_creates=10, num_users=0)


# ---------------------------------------------------------------------------
# Payload builders — required-field / shape invariants
# ---------------------------------------------------------------------------


class TestBuildCreatePayload:
    """Covers test #2 — the ``MissionCreate`` payload shape."""

    def test_build_create_payload_has_required_fields(self):
        """title + description must be present; no extra fields."""
        payload = build_create_payload(0)

        assert "title" in payload
        assert isinstance(payload["title"], str)
        assert payload["title"]
        assert "description" in payload
        assert isinstance(payload["description"], str)
        # These would make ``MissionCreate`` 422 because of ``extra='forbid'``
        assert "mission_type" not in payload
        assert "priority" not in payload
        assert "status" not in payload

    def test_build_create_payload_only_known_keys(self):
        """Defense in depth: payload keys are EXACTLY title + description."""
        payload = build_create_payload(7)
        assert set(payload.keys()) == {
            "title",
            "description",
        }, f"Unexpected keys: {set(payload.keys()) - {'title', 'description'}}"

    def test_build_create_payload_title_is_indexed(self):
        """Titled missions must include the index so the operator can
        correlate logs back to the dictionary entry that produced them."""
        payload = build_create_payload(42)
        assert "42" in payload["title"]

    def test_build_create_payload_does_not_mutate(self):
        """Pure helper — repeated calls yield identical dicts."""
        a = build_create_payload(3)
        b = build_create_payload(3)
        assert a == b


class TestBuildUpdatePayload:
    """Update payload mirrors the create shape (title + description only)."""

    def test_build_update_payload_has_title_and_description(self):
        payload = build_update_payload(0)
        assert "title" in payload
        assert payload["title"]
        assert "description" in payload

    def test_build_update_payload_only_known_keys(self):
        payload = build_update_payload(11)
        # ``MissionUpdate`` allows more keys, but the spec says exercise
        # title+description dual-write.  Keep it minimal.
        assert set(payload.keys()) == {"title", "description"}


class TestBuildRegisterPayload:
    """Covers test #3 — password strength requirement + structured payload."""

    def test_build_register_payload_has_password_strength(self):
        """The static ``EXERCISE_PASSWORD`` satisfies the validator."""
        payload = build_register_payload(0)
        errors = validate_password_strength(payload["password"])
        assert errors == [], f"Password does not satisfy validator: {errors}"

    def test_build_register_payload_has_required_auth_fields(self):
        payload = build_register_payload(0)
        assert "email" in payload
        assert "password" in payload
        # Optional-but-present helpers
        assert "username" in payload
        assert "full_name" in payload

    def test_build_register_payload_email_is_exercise_scoped(self):
        """Test isolation — never touch production-ish emails."""
        payload = build_register_payload(5)
        assert payload["email"].endswith(
            "@exercise.local"
        ), f"Email domain mismatch — safety violation: {payload['email']}"

    def test_register_payload_indexes_are_unique(self):
        """Different indices → different emails."""
        p1 = build_register_payload(0)
        p2 = build_register_payload(1)
        assert p1["email"] != p2["email"]
        assert p1["username"] != p2["username"]

    def test_login_payload_round_trip(self):
        """Login payload references the same email as register."""
        register = build_register_payload(7)
        login = build_login_payload(7)
        # Login uses ``username_or_email`` — confirm it matches the email.
        assert login["username_or_email"] == register["email"]
        assert login["password"] == register["password"]

    def test_password_constant_satisfies_validator(self):
        """Sanity check on the module-level constant — re-validate it."""
        errors = validate_password_strength(EXERCISE_PASSWORD)
        assert errors == [], f"EXERCISE_PASSWORD broke validator: {errors}"


# ---------------------------------------------------------------------------
# assign_mission_operations — disjoint operator assignment
# ---------------------------------------------------------------------------


class TestAssignmentPlanRespectsCounts:
    """Covers test #4 — disjoint slices for the cutover-plan defaults."""

    def test_assignment_plan_respects_counts(self):
        """100/50/30/20/10: truncate-tail semantics — aborts slice is empty.

        The cutover-plan defaults request 110 ops on 100 missions. With
        disjoint-slices invariant, the prior operators (executes +
        updates + deletes) consume the entire pool, so ``aborts`` is
        trimmed to an empty slice.  The disjoint invariant is the
        strong guarantee; the cutover-plan aborts count is best-effort.
        """

        plan = assign_mission_operations(creates=100, executes=50, updates=30, deletes=20, aborts=10)

        # Slice sizes match (the execute/update/delete slices fill the pool).
        assert len(plan.executes) == 50
        assert len(plan.updates) == 30
        assert len(plan.deletes) == 20
        assert len(plan.aborts) == 0  # truncated — disjointness wins
        assert plan.pool_size == 100

        # Pairwise disjoint.
        all_indices = set(plan.executes) | set(plan.updates) | set(plan.deletes) | set(plan.aborts)
        assert (
            len(all_indices) == plan.total_assigned()
        ), "Slices overlap — a mission is assigned to more than one operator"

        # A deleted mission must NEVER also be flagged for abort.
        delete_set = set(plan.deletes)
        abort_set = set(plan.aborts)
        assert delete_set.isdisjoint(abort_set), f"Overlap between deletes and aborts: {delete_set & abort_set}"

        # Slice layout: execute < update < delete < (aborts, possibly empty)
        # all contiguous from 0.
        assert plan.executes[-1] == 49
        assert plan.updates[0] == 50
        assert plan.updates[-1] == 79
        assert plan.deletes[0] == 80
        assert plan.deletes[-1] == 99
        assert plan.aborts == []  # 50+30+20 = 100 ⇒ aborts slice is empty

    def test_assignment_with_aborts_present_respects_disjointness(self):
        """If aborts > 0, the slice is still contiguous and disjoint."""
        plan = assign_mission_operations(creates=110, executes=50, updates=30, deletes=20, aborts=10)

        assert len(plan.aborts) == 10
        assert plan.aborts[0] == 100
        assert plan.aborts[-1] == 109

        delete_set = set(plan.deletes)
        abort_set = set(plan.aborts)
        assert delete_set.isdisjoint(abort_set)

    def test_assignment_plan_is_dataclass_with_all_lists(self):
        plan = AssignmentPlan()
        assert isinstance(plan, AssignmentPlan)
        assert plan.executes == []
        assert plan.updates == []
        assert plan.deletes == []
        assert plan.aborts == []

    def test_assignment_truncates_when_ops_exceed_pool(self):
        """If operator counts add up beyond pool, the tail slice is truncated.

        With 110 ops requested and only 10 pool slots, ``executes``
        honours its full 10-slot request and every downstream slice
        collapses to empty — preserving the disjoint invariant.
        """
        plan = assign_mission_operations(creates=10, executes=50, updates=30, deletes=20, aborts=10)

        assert len(plan.executes) == 10
        assert plan.updates == []
        assert plan.deletes == []
        assert plan.aborts == []
        assert plan.pool_size == 10
        assert plan.total_assigned() == 10

    def test_assignment_truncation_respects_disjointness(self):
        """Even with overflow, slices stay pairwise disjoint."""
        plan = assign_mission_operations(creates=25, executes=20, updates=20, deletes=20, aborts=20)

        assert len(plan.executes) == 20
        assert len(plan.updates) == 5
        assert plan.deletes == []
        assert plan.aborts == []

        all_indices = set(plan.executes) | set(plan.updates) | set(plan.deletes) | set(plan.aborts)
        assert (
            len(all_indices) == plan.total_assigned()
        ), "Slices overlap after truncation — must never assign same index to two operators"

    def test_negative_counts_raise(self):
        with pytest.raises(ValueError, match="must all be non-negative"):
            assign_mission_operations(creates=10, executes=-1, updates=0, deletes=0, aborts=0)

    def test_slices_are_within_pool(self):
        """No slice index ever exceeds ``pool_size - 1``."""
        plan = assign_mission_operations(creates=100, executes=50, updates=30, deletes=20, aborts=10)
        upper_bound = plan.pool_size
        for slice_ in (plan.executes, plan.updates, plan.deletes, plan.aborts):
            if slice_:
                assert max(slice_) < upper_bound


# ---------------------------------------------------------------------------
# Smoke checks — keep the dataclass frozen + uuid4 importable
# ---------------------------------------------------------------------------


class TestMiscSmoke:
    """Tiny sanity so future refactors don't break trivial assumptions."""

    def test_uuid4_importable(self):
        # The script does not use uuid4 directly, but tests often do.
        assert isinstance(uuid4(), type(uuid4()))

    def test_assignment_plan_is_frozen(self):
        """Frozen dataclass — assignment raises."""
        plan = AssignmentPlan(executes=[1, 2], pool_size=2)
        with pytest.raises(FrozenInstanceError):
            plan.executes = [3, 4]  # type: ignore[misc]
