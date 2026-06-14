"""TDD tests for Pydantic v2 schemas for Mission Programs (T2).

Covers:
- (a) ProgramCreate(name="") raises ValidationError (min_length)
- (b) ProgramCreate(name="x", per_run_budget_usd=-1.0) raises ValidationError
- (c) ProgramCreate(name="x", per_run_budget_usd=0.0) succeeds (boundary)
- (d) ConsolidateRequest(limit=0) raises ValidationError (ge=1)
- (e) ConsolidateRequest(limit=51) raises ValidationError (le=50)
- (f) ProgramCreate(trigger_config={"type": "cron", ...}) succeeds — discriminated union
- (g) ProgramCreate(trigger_config={"type": "manual"}) succeeds — discriminated union
- (h) ProgramCreate(trigger_config={"type": "cron"}) raises ValidationError (missing expression)
- (i) LearningBriefBase(user_notes="hello") succeeds — user_notes must default to "" and be writable
- (j) ConsolidateRequest() defaults to limit=10

Style notes:
- Tests are pure-Python (no DB). Pydantic v2 schemas are independent of SQLAlchemy.
- Import inside each test so RED-phase import errors are visible at the test boundary.
- Imports are written as `from app.schemas.program import ...` to match the project
  pattern (other schemas use `from app.schemas.mission import ...`).
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError


class TestProgramCreateValidation:
    """ProgramCreate input validation — name length and budget non-negativity."""

    def test_a_empty_name_raises_validation_error(self) -> None:
        """(a) Empty name violates min_length=1."""
        from app.schemas.program import ProgramCreate

        with pytest.raises(ValidationError) as exc_info:
            ProgramCreate(name="")

        # Confirm the error is on the name field, not something else.
        errors = exc_info.value.errors()
        assert any("name" in str(e.get("loc", [])) for e in errors), (
            f"Expected validation error on 'name', got: {errors}"
        )

    def test_b_negative_per_run_budget_raises(self) -> None:
        """(b) Negative per_run_budget_usd violates ge=0."""
        from app.schemas.program import ProgramCreate

        with pytest.raises(ValidationError) as exc_info:
            ProgramCreate(name="x", per_run_budget_usd=-1.0)

        errors = exc_info.value.errors()
        assert any(
            "per_run_budget_usd" in str(e.get("loc", [])) for e in errors
        ), f"Expected validation error on 'per_run_budget_usd', got: {errors}"

    def test_c_zero_per_run_budget_succeeds(self) -> None:
        """(c) Zero budget is the boundary case — must be accepted (ge=0)."""
        from app.schemas.program import ProgramCreate

        program = ProgramCreate(name="x", per_run_budget_usd=0.0)
        assert program.name == "x"
        assert program.per_run_budget_usd == 0.0

    def test_c2_negative_monthly_budget_raises(self) -> None:
        """Companion to (b): monthly_budget_usd also has ge=0."""
        from app.schemas.program import ProgramCreate

        with pytest.raises(ValidationError) as exc_info:
            ProgramCreate(name="x", monthly_budget_usd=-0.01)

        errors = exc_info.value.errors()
        assert any(
            "monthly_budget_usd" in str(e.get("loc", [])) for e in errors
        ), f"Expected validation error on 'monthly_budget_usd', got: {errors}"

    def test_c3_default_optional_fields(self) -> None:
        """Only `name` is required; everything else has sensible defaults."""
        from app.schemas.program import ProgramCreate

        program = ProgramCreate(name="minimal")
        assert program.name == "minimal"
        assert program.description == ""
        assert program.mission_type is None
        assert program.base_constraints is None
        assert program.base_context_files is None
        assert program.base_context_urls is None
        assert program.trigger_config is None
        assert program.per_run_budget_usd is None
        assert program.monthly_budget_usd is None

    def test_c4_extra_field_forbidden(self) -> None:
        """extra='forbid' means unknown fields are rejected (project pattern)."""
        from app.schemas.program import ProgramCreate

        with pytest.raises(ValidationError) as exc_info:
            ProgramCreate(name="x", unknown_field="boom")  # type: ignore[call-arg]

        errors = exc_info.value.errors()
        assert any("unknown_field" in str(e.get("loc", [])) for e in errors), (
            f"Expected validation error on 'unknown_field', got: {errors}"
        )


class TestConsolidateRequestValidation:
    """ConsolidateRequest.limit must be 1..50 (default 10)."""

    def test_d_limit_zero_raises(self) -> None:
        """(d) limit=0 violates ge=1."""
        from app.schemas.program import ConsolidateRequest

        with pytest.raises(ValidationError) as exc_info:
            ConsolidateRequest(limit=0)

        errors = exc_info.value.errors()
        assert any("limit" in str(e.get("loc", [])) for e in errors), (
            f"Expected validation error on 'limit', got: {errors}"
        )

    def test_e_limit_51_raises(self) -> None:
        """(e) limit=51 violates le=50."""
        from app.schemas.program import ConsolidateRequest

        with pytest.raises(ValidationError) as exc_info:
            ConsolidateRequest(limit=51)

        errors = exc_info.value.errors()
        assert any("limit" in str(e.get("loc", [])) for e in errors), (
            f"Expected validation error on 'limit', got: {errors}"
        )

    def test_j_default_limit_is_10(self) -> None:
        """(j) ConsolidateRequest() defaults to limit=10."""
        from app.schemas.program import ConsolidateRequest

        req = ConsolidateRequest()
        assert req.limit == 10

    def test_j2_boundary_limits_succeed(self) -> None:
        """limit=1 and limit=50 must both succeed (inclusive bounds)."""
        from app.schemas.program import ConsolidateRequest

        assert ConsolidateRequest(limit=1).limit == 1
        assert ConsolidateRequest(limit=50).limit == 50


class TestTriggerDiscriminatedUnion:
    """trigger_config is a Pydantic v2 discriminated union on `type`."""

    def test_f_cron_trigger_validates(self) -> None:
        """(f) Full cron trigger config (type + expression + timezone) succeeds."""
        from app.schemas.program import ProgramCreate

        program = ProgramCreate(
            name="x",
            trigger_config={
                "type": "cron",
                "expression": "0 9 * * *",
                "timezone": "UTC",
            },
        )
        assert program.trigger_config is not None
        assert program.trigger_config.type == "cron"
        assert program.trigger_config.expression == "0 9 * * *"
        assert program.trigger_config.timezone == "UTC"

    def test_g_manual_trigger_validates(self) -> None:
        """(g) Manual trigger (type-only) succeeds."""
        from app.schemas.program import ProgramCreate

        program = ProgramCreate(name="x", trigger_config={"type": "manual"})
        assert program.trigger_config is not None
        assert program.trigger_config.type == "manual"

    def test_g2_webhook_trigger_validates(self) -> None:
        """Webhook trigger (type + secret + path) succeeds."""
        from app.schemas.program import ProgramCreate

        program = ProgramCreate(
            name="x",
            trigger_config={
                "type": "webhook",
                "secret": "shhh",
                "path": "/hooks/x",
            },
        )
        assert program.trigger_config is not None
        assert program.trigger_config.type == "webhook"
        assert program.trigger_config.secret == "shhh"
        assert program.trigger_config.path == "/hooks/x"

    def test_h_cron_missing_expression_raises(self) -> None:
        """(h) Cron trigger without `expression` raises ValidationError."""
        from app.schemas.program import ProgramCreate

        with pytest.raises(ValidationError):
            ProgramCreate(name="x", trigger_config={"type": "cron"})

    def test_h2_webhook_missing_secret_raises(self) -> None:
        """Webhook trigger without `secret` raises ValidationError."""
        from app.schemas.program import ProgramCreate

        with pytest.raises(ValidationError):
            ProgramCreate(
                name="x",
                trigger_config={"type": "webhook", "path": "/hooks/x"},
            )

    def test_h3_unknown_trigger_type_raises(self) -> None:
        """Unknown `type` discriminator is rejected by the union."""
        from app.schemas.program import ProgramCreate

        with pytest.raises(ValidationError):
            ProgramCreate(
                name="x",
                trigger_config={"type": "totally-bogus"},  # type: ignore[typeddict-item]
            )

    def test_h4_cron_extra_field_forbidden(self) -> None:
        """Trigger variants use extra='forbid' — unknown fields rejected."""
        from app.schemas.program import ProgramCreate

        with pytest.raises(ValidationError):
            ProgramCreate(
                name="x",
                trigger_config={
                    "type": "cron",
                    "expression": "0 9 * * *",
                    "rogue_field": "boom",  # type: ignore[typeddict-item]
                },
            )


class TestLearningBriefBase:
    """LearningBriefBase structure and the user_notes guardrail."""

    def test_i_user_notes_default_empty(self) -> None:
        """(i) LearningBriefBase().user_notes defaults to ''."""
        from app.schemas.program import LearningBriefBase

        brief = LearningBriefBase()
        assert brief.user_notes == ""

    def test_i2_user_notes_settable(self) -> None:
        """(i) LearningBriefBase(user_notes='hello') succeeds."""
        from app.schemas.program import LearningBriefBase

        brief = LearningBriefBase(user_notes="hello")
        assert brief.user_notes == "hello"

    def test_i3_full_brief_round_trip(self) -> None:
        """All documented sub-keys round-trip on the LearningBriefBase."""
        from app.schemas.program import LearningBriefBase

        brief = LearningBriefBase(
            total_runs=5,
            success_rate=0.6,
            avg_cost_usd=0.42,
            avg_tokens=1200,
            common_failures=[{"pattern": "tool_timeout", "count": 3, "mitigation": "retry"}],
            effective_tools=["web_search"],
            ineffective_tools=["weather_api"],
            hitl_history=[{"outcome": "approved", "count": 2}],
            plan_adjustments="Use fewer parallel tools",
            last_consolidated_at="2026-06-13T00:00:00Z",
            user_notes="Avoid Mondays",
        )
        assert brief.total_runs == 5
        assert brief.common_failures[0]["pattern"] == "tool_timeout"
        assert brief.effective_tools == ["web_search"]
        assert brief.user_notes == "Avoid Mondays"

    def test_i4_extra_field_forbidden(self) -> None:
        """extra='forbid' on LearningBriefBase — unknown keys rejected."""
        from app.schemas.program import LearningBriefBase

        with pytest.raises(ValidationError):
            LearningBriefBase(rogue_key="boom")  # type: ignore[call-arg]


class TestResponseSchemas:
    """ProgramResponse / ProgramRunResponse use from_attributes (ORM-friendly)."""

    def test_program_response_extra_field_allowed(self) -> None:
        """ProgramResponse is a response model — it does NOT forbid extras
        (extra='forbid' is only on create/update, matching mission.py pattern)."""
        from app.schemas.program import ProgramResponse

        # Build a minimal payload and confirm it constructs.
        resp = ProgramResponse(
            id="00000000-0000-0000-0000-000000000001",
            user_id=1,
            workspace_id="ws-1",
            name="prog",
            description="",
            status="active",
        )
        assert resp.name == "prog"
        assert resp.status == "active"

    def test_program_run_response_minimal(self) -> None:
        """ProgramRunResponse constructs with the documented minimal fields."""
        from app.schemas.program import ProgramRunResponse

        resp = ProgramRunResponse(
            id="00000000-0000-0000-0000-000000000002",
            program_id="00000000-0000-0000-0000-000000000003",
            mission_id="00000000-0000-0000-0000-000000000004",
            trigger_type="manual",
            status="running",
        )
        assert resp.trigger_type == "manual"
        assert resp.status == "running"

    def test_consolidate_response_wraps_brief(self) -> None:
        """ConsolidateResponse.brief is a typed LearningBriefBase."""
        from app.schemas.program import ConsolidateResponse, LearningBriefBase

        resp = ConsolidateResponse(
            consolidated_runs=3,
            brief=LearningBriefBase(total_runs=3, success_rate=1.0),
            duration_ms=42,
        )
        assert resp.consolidated_runs == 3
        assert resp.duration_ms == 42
        assert resp.brief.total_runs == 3
        assert resp.brief.success_rate == 1.0


class TestFireRequest:
    """FireRequest is the manual-fire payload — trigger_payload is optional."""

    def test_fire_request_empty(self) -> None:
        from app.schemas.program import FireRequest

        req = FireRequest()
        assert req.trigger_payload is None

    def test_fire_request_with_payload(self) -> None:
        from app.schemas.program import FireRequest

        req = FireRequest(trigger_payload={"reason": "manual_test", "ticket": 42})
        assert req.trigger_payload == {"reason": "manual_test", "ticket": 42}

    def test_fire_request_extra_forbidden(self) -> None:
        from app.schemas.program import FireRequest

        with pytest.raises(ValidationError):
            FireRequest(rogue="boom")  # type: ignore[call-arg]


class TestProgramUpdate:
    """ProgramUpdate is PATCH semantics — all fields Optional."""

    def test_program_update_empty(self) -> None:
        from app.schemas.program import ProgramUpdate

        upd = ProgramUpdate()
        assert upd.name is None
        assert upd.status is None

    def test_program_update_status_validated(self) -> None:
        """status must be one of the documented literals."""
        from app.schemas.program import ProgramUpdate

        upd = ProgramUpdate(status="active")
        assert upd.status == "active"

        upd_paused = ProgramUpdate(status="paused")
        assert upd_paused.status == "paused"

        upd_archived = ProgramUpdate(status="archived")
        assert upd_archived.status == "archived"

    def test_program_update_status_garbage_rejected(self) -> None:
        from app.schemas.program import ProgramUpdate

        with pytest.raises(ValidationError):
            ProgramUpdate(status="zombie")  # type: ignore[arg-type]

    def test_program_update_extra_forbidden(self) -> None:
        from app.schemas.program import ProgramUpdate

        with pytest.raises(ValidationError):
            ProgramUpdate(rogue="boom")  # type: ignore[call-arg]

    def test_program_update_empty_name_rejected(self) -> None:
        """Even PATCH-style: if name is provided, it must satisfy min_length=1."""
        from app.schemas.program import ProgramUpdate

        with pytest.raises(ValidationError):
            ProgramUpdate(name="")
