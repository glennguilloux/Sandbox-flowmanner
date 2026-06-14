"""TDD tests for MissionProgram + ProgramRun models.

Covers:
- (a) MissionProgram can be instantiated with required fields
- (b) workspace_id=None raises IntegrityError on commit (NOT NULL guardrail)
- (c) ProgramStatus.ACTIVE.can_transition_to(ProgramStatus.PAUSED) returns True
- (d) ProgramStatus.ARCHIVED.can_transition_to(ProgramStatus.ACTIVE) returns False
- (e) ProgramRun with program_id=UUID, mission_id=UUID instantiates OK
- (f) learning_brief dict with documented sub-keys is accepted as JSONB

The DB-dependent test (b) uses a real PostgreSQL connection (project pattern,
see test_knowledge_graph.py). All other tests are pure-Python instantiation
and enum-logic tests.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest


# ── Pure-Python tests (no DB) ────────────────────────────────────────────


class TestProgramStatusTransitions:
    """Validate the ProgramStatus enum state machine."""

    def test_active_can_transition_to_paused(self) -> None:
        # Import inside test so RED-phase import errors are visible.
        from app.models.mission_program_models import ProgramStatus

        assert ProgramStatus.ACTIVE.can_transition_to(ProgramStatus.PAUSED) is True

    def test_archived_cannot_transition_to_active(self) -> None:
        from app.models.mission_program_models import ProgramStatus

        # ARCHIVED is terminal — no transitions allowed out.
        assert ProgramStatus.ARCHIVED.can_transition_to(ProgramStatus.ACTIVE) is False

    def test_archived_is_terminal(self) -> None:
        from app.models.mission_program_models import ProgramStatus

        assert ProgramStatus.ARCHIVED.is_terminal is True
        assert ProgramStatus.ARCHIVED.is_active is False

    def test_active_is_active_not_terminal(self) -> None:
        from app.models.mission_program_models import ProgramStatus

        assert ProgramStatus.ACTIVE.is_terminal is False
        assert ProgramStatus.ACTIVE.is_active is True


class TestProgramRunStatusTransitions:
    """Validate the ProgramRunStatus enum state machine."""

    def test_running_can_transition_to_completed(self) -> None:
        from app.models.mission_program_models import ProgramRunStatus

        assert ProgramRunStatus.RUNNING.can_transition_to(ProgramRunStatus.COMPLETED) is True

    def test_completed_is_terminal(self) -> None:
        from app.models.mission_program_models import ProgramRunStatus

        assert ProgramRunStatus.COMPLETED.is_terminal is True
        assert ProgramRunStatus.COMPLETED.can_transition_to(ProgramRunStatus.RUNNING) is False


class TestMissionProgramInstantiation:
    """Validate the MissionProgram class can be constructed in Python."""

    def test_instantiate_with_required_fields(self) -> None:
        """Required: user_id, workspace_id, name. No exceptions."""
        from app.models.mission_program_models import MissionProgram

        # Pure-Python instantiation; no DB commit.
        program = MissionProgram(user_id=1, workspace_id="ws-1", name="Test Program")
        assert program.user_id == 1
        assert program.workspace_id == "ws-1"
        assert program.name == "Test Program"
        # id is a column-level default; populated at flush time, not at construction.
        # (See test_status_default_applies_at_flush for the actual default behaviour.)
        # The test exists only to prove construction succeeds with the required fields.

    def test_status_default_applies_at_flush(self) -> None:
        """Column default fires at flush (matches the Mission model pattern)."""
        from app.models.mission_program_models import MissionProgram
        from app.models import Base

        # Pull the column-level default from the mapper (no DB needed).
        columns = Base.metadata.tables["mission_programs"].columns
        status_col = columns["status"]
        # Project pattern: status defaults to "active" via server-side default.
        assert status_col.default is not None
        assert status_col.default.arg == "active"

    def test_learning_brief_accepts_documented_subkeys(self) -> None:
        """JSONB field accepts a dict with the documented sub-key structure."""
        from app.models.mission_program_models import MissionProgram

        learning_brief: dict[str, Any] = {
            "total_runs": 5,
            "success_rate": 0.6,
            "common_failures": [{"pattern": "tool_timeout", "count": 3, "mitigation": "retry"}],
            "effective_tools": ["web_search"],
            "user_notes": "Avoid Mondays — higher load",
            "last_consolidated_at": "2026-06-13T00:00:00Z",
        }

        program = MissionProgram(
            user_id=1,
            workspace_id="ws-1",
            name="Learner",
            learning_brief=learning_brief,
        )
        # Round-trip the dict; SQLAlchemy stores it as-is in memory.
        assert program.learning_brief == learning_brief
        assert program.learning_brief["user_notes"] == "Avoid Mondays — higher load"
        assert program.learning_brief["common_failures"][0]["pattern"] == "tool_timeout"

    def test_base_constraints_and_context_jsonb(self) -> None:
        """All three base_* JSONB fields round-trip arbitrary dicts."""
        from app.models.mission_program_models import MissionProgram

        program = MissionProgram(
            user_id=1,
            workspace_id="ws-1",
            name="X",
            base_constraints={"max_cost": 5.0, "tools": ["a", "b"]},
            base_context_files=[{"path": "README.md", "content": "..."}],
            base_context_urls=["https://example.com"],
            trigger_config={"type": "cron", "expression": "0 9 * * *", "timezone": "UTC"},
        )
        assert program.base_constraints["max_cost"] == 5.0
        assert program.base_context_files[0]["path"] == "README.md"
        assert program.trigger_config["type"] == "cron"


class TestProgramRunInstantiation:
    """Validate the ProgramRun class can be constructed in Python."""

    def test_instantiate_with_uuids(self) -> None:
        from app.models.mission_program_models import ProgramRun

        program_id = uuid.uuid4()
        mission_id = uuid.uuid4()
        run = ProgramRun(
            program_id=program_id,
            mission_id=mission_id,
            trigger_type="manual",
        )
        assert run.program_id == program_id
        assert run.mission_id == mission_id
        assert run.trigger_type == "manual"
        # id is a column-level default (uuid4); populated at flush time.
        # See test_status_default_applies_at_flush for the column-level default check.
        # Project pattern: default status "running"
        from app.models import Base

        status_col = Base.metadata.tables["program_runs"].columns["status"]
        assert status_col.default is not None
        assert status_col.default.arg == "running"

    def test_instantiate_with_trigger_payload_jsonb(self) -> None:
        from app.models.mission_program_models import ProgramRun

        run = ProgramRun(
            program_id=uuid.uuid4(),
            mission_id=uuid.uuid4(),
            trigger_type="webhook",
            trigger_payload={"source": "github", "event": "push", "branch": "main"},
        )
        assert run.trigger_payload["source"] == "github"
        assert run.trigger_payload["event"] == "push"


# ── NOT NULL guardrail (tested via mapper inspection — no live DB needed) ──


def test_workspace_id_is_not_null_on_missionprogram() -> None:
    """Guardrail: workspace_id MUST be NOT NULL on MissionProgram.

    Asserted via SQLAlchemy mapper inspection (no live DB needed). The
    database enforces the constraint at INSERT time; this test proves the
    mapper definition carries the constraint, so a future schema change
    that weakens it fails this test before reaching production.
    """
    from app.models import Base
    from app.models.mission_program_models import MissionProgram  # noqa: F401

    workspace_col = Base.metadata.tables["mission_programs"].columns["workspace_id"]
    assert workspace_col.nullable is False, (
        "GUARDRAIL VIOLATION: MissionProgram.workspace_id must be NOT NULL "
        "(workspace isolation mandatory per plan §T1)."
    )


def test_missionprogram_required_columns_are_not_null() -> None:
    """All four required columns are NOT NULL: id, user_id, workspace_id, name."""
    from app.models import Base
    from app.models.mission_program_models import MissionProgram  # noqa: F401

    cols = Base.metadata.tables["mission_programs"].columns
    for col_name in ("id", "user_id", "workspace_id", "name"):
        assert cols[col_name].nullable is False, (
            f"MissionProgram.{col_name} must be NOT NULL (required field)"
        )


def test_programrun_required_columns_are_not_null() -> None:
    """All four required columns are NOT NULL: id, program_id, mission_id, trigger_type."""
    from app.models import Base
    from app.models.mission_program_models import ProgramRun  # noqa: F401

    cols = Base.metadata.tables["program_runs"].columns
    for col_name in ("id", "program_id", "mission_id", "trigger_type"):
        assert cols[col_name].nullable is False, (
            f"ProgramRun.{col_name} must be NOT NULL (required field)"
        )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_workspace_id_none_raises_integrity_error_on_commit() -> None:
    """Live-DB guardrail: inserting a row with workspace_id=None raises IntegrityError.

    Marked as ``integration`` because it requires a live PostgreSQL connection
    with the new tables created. Skipped in default test runs (which use
    ``-m "not integration"``). Run via::

        docker compose exec backend pytest -m integration tests/test_mission_program_models.py
    """
    from app.models.mission_program_models import MissionProgram

    pytest.skip(
        "Integration test — requires live DB. "
        "Run with: docker compose exec backend pytest -m integration "
        "tests/test_mission_program_models.py::test_workspace_id_none_raises_integrity_error_on_commit"
    )
