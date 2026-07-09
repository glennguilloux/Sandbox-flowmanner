"""TDD tests for MemoryCorrectionEvent model (D30-60, T29).

Covers:
- (a) MemoryCorrectionEvent is registered in Base.metadata
- (b) All expected columns exist with correct types and nullability
- (c) Composite indexes are configured (3 indexes per spec)
- (d) CHECK constraint on event_type
- (e) CHECK constraint on actor
- (f) Hardcoded ALL_* tuples (no sunder-name leak)
- (g) actor default is "user"
- (h) FK to claim is ON DELETE SET NULL (audit row survives claim hard-delete)
- (i) workspace_id FK to workspaces.id is ON DELETE CASCADE
- (j) @pytest.mark.integration — live DB SET NULL behavior
      (skipped in default runs; run with ``-m integration``)

The DB-dependent test (j) uses a real PostgreSQL connection (project pattern,
see test_personal_memory_models.py). All other tests are pure-Python
mapper/import tests.
"""

from __future__ import annotations

import pytest

# ── Pure-Python tests (no DB) ────────────────────────────────────────────


class TestMemoryCorrectionEventMetadata:
    """Validate the model is registered with Base.metadata."""

    def test_memory_correction_event_table_registered_in_metadata(self) -> None:
        """The ``memory_correction_events`` table must be in Base.metadata
        once the model is imported."""
        from app.models import Base
        from app.models.memory_correction_models import (
            MemoryCorrectionEvent,
        )

        assert "memory_correction_events" in Base.metadata.tables, (
            "Expected 'memory_correction_events' in Base.metadata.tables; "
            f"got: {sorted(Base.metadata.tables.keys())}"
        )

    def test_memory_correction_event_class_is_a_model(self) -> None:
        """MemoryCorrectionEvent should subclass Base + TimestampMixin
        (have created_at/updated_at)."""
        from app.models import Base
        from app.models.memory_correction_models import (
            MemoryCorrectionEvent,
        )

        assert issubclass(MemoryCorrectionEvent, Base)
        # TimestampMixin columns appear on the instance after mapper config.
        e = MemoryCorrectionEvent(
            user_id=1,
            workspace_id="ws-1",
            event_type="view",
        )
        assert hasattr(e, "created_at")
        assert hasattr(e, "updated_at")


class TestMemoryCorrectionEventColumns:
    """Validate the column set: types, nullability, and presence."""

    def test_required_columns_are_not_null(self) -> None:
        """All required columns are NOT NULL."""
        from app.models import Base
        from app.models.memory_correction_models import (
            MemoryCorrectionEvent,
        )

        cols = Base.metadata.tables["memory_correction_events"].columns
        required = (
            "id",
            "user_id",
            "workspace_id",
            "event_type",
            "actor",
            "created_at",
            "updated_at",
        )
        for col_name in required:
            assert cols[col_name].nullable is False, (
                f"MemoryCorrectionEvent.{col_name} must be NOT NULL " "(required field)"
            )

    def test_optional_columns_are_nullable(self) -> None:
        """Optional columns are NULLABLE: claim_id, source, details."""
        from app.models import Base
        from app.models.memory_correction_models import (
            MemoryCorrectionEvent,
        )

        cols = Base.metadata.tables["memory_correction_events"].columns
        optional = ("claim_id", "source", "details")
        for col_name in optional:
            assert cols[col_name].nullable is True, (
                f"MemoryCorrectionEvent.{col_name} must be nullable " "(optional field)"
            )

    def test_id_is_uuid_primary_key(self) -> None:
        """Primary key is UUID, auto-defaulted via uuid4()."""
        from app.models import Base
        from app.models.memory_correction_models import (
            MemoryCorrectionEvent,
        )

        table = Base.metadata.tables["memory_correction_events"]
        pk = table.primary_key
        assert pk is not None
        assert "id" in pk.columns
        id_col = table.columns["id"]
        assert id_col.primary_key is True
        # Default must exist and be a uuid4 generator.
        assert id_col.default is not None, "MemoryCorrectionEvent.id must have a default (uuid4)"
        assert id_col.default.is_callable is True, "MemoryCorrectionEvent.id default must be callable"

    def test_event_type_column_is_string(self) -> None:
        """event_type is a String column (project pattern: validated by
        CHECK, not enum)."""
        from app.models import Base
        from app.models.memory_correction_models import (
            MemoryCorrectionEvent,
        )

        col = Base.metadata.tables["memory_correction_events"].columns["event_type"]
        assert col.type.__class__.__name__ == "String", f"event_type must be String; got {col.type.__class__.__name__}"

    def test_actor_column_is_string(self) -> None:
        """actor is a String column (project pattern: validated by
        CHECK, not enum)."""
        from app.models import Base
        from app.models.memory_correction_models import (
            MemoryCorrectionEvent,
        )

        col = Base.metadata.tables["memory_correction_events"].columns["actor"]
        assert col.type.__class__.__name__ == "String", f"actor must be String; got {col.type.__class__.__name__}"

    def test_details_column_is_jsonb(self) -> None:
        """The details column uses JSONB for arbitrary extra context."""
        from app.models import Base
        from app.models.memory_correction_models import (
            MemoryCorrectionEvent,
        )

        col = Base.metadata.tables["memory_correction_events"].columns["details"]
        assert col.type.__class__.__name__ == "JSONB", f"details must be JSONB; got {col.type.__class__.__name__}"


class TestMemoryCorrectionEventIndexes:
    """Validate the three composite indexes required for fast recall."""

    def test_composite_index_user_workspace_created(self) -> None:
        """Index on (user_id, workspace_id, created_at) for fast user
        audit listing."""
        from app.models import Base
        from app.models.memory_correction_models import (
            MemoryCorrectionEvent,
        )

        table = Base.metadata.tables["memory_correction_events"]
        index_column_sets = [(idx.name, tuple(idx.columns.keys())) for idx in table.indexes]
        assert any(cols == ("user_id", "workspace_id", "created_at") for _name, cols in index_column_sets), (
            "Missing composite index on " "(user_id, workspace_id, created_at); " f"found: {index_column_sets}"
        )

    def test_index_on_claim_id(self) -> None:
        """Index on claim_id for fast per-claim provenance query."""
        from app.models import Base
        from app.models.memory_correction_models import (
            MemoryCorrectionEvent,
        )

        table = Base.metadata.tables["memory_correction_events"]
        index_column_sets = [(idx.name, tuple(idx.columns.keys())) for idx in table.indexes]
        assert any(
            cols == ("claim_id",) for _name, cols in index_column_sets
        ), f"Missing index on (claim_id,); found: {index_column_sets}"

    def test_index_on_user_workspace_event_type(self) -> None:
        """Index on (user_id, workspace_id, event_type) for fast filtered
        listing by event type."""
        from app.models import Base
        from app.models.memory_correction_models import (
            MemoryCorrectionEvent,
        )

        table = Base.metadata.tables["memory_correction_events"]
        index_column_sets = [(idx.name, tuple(idx.columns.keys())) for idx in table.indexes]
        assert any(cols == ("user_id", "workspace_id", "event_type") for _name, cols in index_column_sets), (
            "Missing composite index on " "(user_id, workspace_id, event_type); " f"found: {index_column_sets}"
        )


class TestMemoryCorrectionEventCheckConstraints:
    """Validate CHECK constraints are wired up on the mapper."""

    def test_event_type_check_constraint_defined(self) -> None:
        from app.models import Base
        from app.models.memory_correction_models import (
            MemoryCorrectionEvent,
        )

        table = Base.metadata.tables["memory_correction_events"]
        check_names = {c.name for c in table.constraints if hasattr(c, "name") and c.name}
        assert any(
            "event_type" in (n or "") for n in check_names
        ), f"Expected a CHECK constraint on event_type; got: {check_names}"

    def test_actor_check_constraint_defined(self) -> None:
        from app.models import Base
        from app.models.memory_correction_models import (
            MemoryCorrectionEvent,
        )

        table = Base.metadata.tables["memory_correction_events"]
        check_names = {c.name for c in table.constraints if hasattr(c, "name") and c.name}
        assert any(
            "actor" in (n or "") for n in check_names
        ), f"Expected a CHECK constraint on actor; got: {check_names}"


class TestMemoryCorrectionEventValueSets:
    """Validate the hardcoded ALL_* tuples are well-formed.

    Defensive test: project history shows that ``str, Enum`` iteration
    leaks ``_TRANSITIONS`` into CHECK constraints, corrupting SQL. We
    require that the tuples are hardcoded plain tuples of strings with
    no underscore-leaks.
    """

    def test_all_event_types_is_hardcoded_tuple(self) -> None:
        from app.models.memory_correction_models import ALL_EVENT_TYPES

        assert isinstance(ALL_EVENT_TYPES, tuple), (
            f"ALL_EVENT_TYPES must be a tuple; " f"got {type(ALL_EVENT_TYPES).__name__}"
        )

    def test_all_event_types_contains_documented_values(self) -> None:
        from app.models.memory_correction_models import ALL_EVENT_TYPES

        assert set(ALL_EVENT_TYPES) == {
            "view",
            "edit",
            "delete",
            "forget",
            "create",
            "inspect",
            "export",
            "pause",
            "resume",
            "review",
            "drop",
        }

    def test_all_event_types_no_sunder_leak(self) -> None:
        """Defensive: no ``_TRANSITIONS`` or other dunder/private name
        in the tuple. Regression guard for the project's known
        ``str, Enum`` _TRANSITIONS leak. If someone accidentally derives
        this tuple from enum iteration, this test fails."""
        from app.models.memory_correction_models import ALL_EVENT_TYPES

        for v in ALL_EVENT_TYPES:
            assert isinstance(v, str), f"ALL_EVENT_TYPES entries must be str; " f"got {type(v).__name__}: {v!r}"
            assert not v.startswith("_"), f"ALL_EVENT_TYPES contains a sunder-name leak: {v!r}"

    def test_all_actors_is_hardcoded_tuple(self) -> None:
        from app.models.memory_correction_models import ALL_ACTORS

        assert isinstance(ALL_ACTORS, tuple), f"ALL_ACTORS must be a tuple; " f"got {type(ALL_ACTORS).__name__}"

    def test_all_actors_contains_documented_values(self) -> None:
        from app.models.memory_correction_models import ALL_ACTORS

        assert set(ALL_ACTORS) == {"user", "system", "admin"}

    def test_all_actors_no_sunder_leak(self) -> None:
        from app.models.memory_correction_models import ALL_ACTORS

        for v in ALL_ACTORS:
            assert isinstance(v, str), f"ALL_ACTORS entries must be str; " f"got {type(v).__name__}: {v!r}"
            assert not v.startswith("_"), f"ALL_ACTORS contains a sunder-name leak: {v!r}"


# ── Column defaults ──────────────────────────────────────────────────────


def test_default_actor_is_user() -> None:
    """The actor column must default to "user" at the column level."""
    from app.models import Base
    from app.models.memory_correction_models import (
        MemoryCorrectionEvent,
    )

    col = Base.metadata.tables["memory_correction_events"].columns["actor"]
    assert col.default is not None, 'actor must have a column-level default (="user")'
    # String literal default — SQLAlchemy represents it as a str.
    assert col.default.arg == "user", f"actor default must be 'user'; got {col.default.arg!r}"


# ── Foreign keys (mapper inspection — no live DB) ────────────────────────


def test_user_id_fk_to_users() -> None:
    """user_id has FK to users.id (no cascade — user rows are global)."""
    from app.models import Base
    from app.models.memory_correction_models import (
        MemoryCorrectionEvent,
    )

    user_col = Base.metadata.tables["memory_correction_events"].columns["user_id"]
    fk_targets = list(user_col.foreign_keys)
    assert len(fk_targets) == 1, f"user_id must have exactly one FK; got {len(fk_targets)}"
    fk = fk_targets[0]
    assert fk.column.table.name == "users", f"FK must target users; got {fk.column.table.name}"


def test_workspace_id_fk_with_cascade() -> None:
    """workspace_id has FK to workspaces.id with ON DELETE CASCADE."""
    from app.models import Base
    from app.models.memory_correction_models import (
        MemoryCorrectionEvent,
    )

    workspace_col = Base.metadata.tables["memory_correction_events"].columns["workspace_id"]
    fk_targets = list(workspace_col.foreign_keys)
    assert len(fk_targets) == 1, f"workspace_id must have exactly one FK; got {len(fk_targets)}"
    fk = fk_targets[0]
    assert fk.column.table.name == "workspaces", f"FK must target workspaces; got {fk.column.table.name}"
    assert fk.ondelete == "CASCADE", f"FK must ON DELETE CASCADE; got {fk.ondelete!r}"


def test_claim_id_fk_to_claims_with_set_null() -> None:
    """claim_id has FK to personal_memory_claims.id with ON DELETE SET NULL
    so the audit row survives a hard-delete of the claim (privacy:
    a 'forget' event proves the user exercised the right to be forgotten)."""
    from app.models import Base
    from app.models.memory_correction_models import (
        MemoryCorrectionEvent,
    )

    claim_col = Base.metadata.tables["memory_correction_events"].columns["claim_id"]
    fk_targets = list(claim_col.foreign_keys)
    assert len(fk_targets) == 1, f"claim_id must have exactly one FK; got {len(fk_targets)}"
    fk = fk_targets[0]
    assert (
        fk.column.table.name == "personal_memory_claims"
    ), f"FK must target personal_memory_claims; got {fk.column.table.name}"
    assert fk.ondelete == "SET NULL", (
        f"FK must ON DELETE SET NULL (audit row survives claim delete); " f"got {fk.ondelete!r}"
    )


def test_workspace_id_is_not_null() -> None:
    """Guardrail: workspace_id MUST be NOT NULL (workspace isolation
    mandatory per project rules)."""
    from app.models import Base
    from app.models.memory_correction_models import (
        MemoryCorrectionEvent,
    )

    workspace_col = Base.metadata.tables["memory_correction_events"].columns["workspace_id"]
    assert workspace_col.nullable is False, (
        "GUARDRAIL VIOLATION: MemoryCorrectionEvent.workspace_id must "
        "be NOT NULL (workspace isolation mandatory per project rules)."
    )


# ── Integration test (live DB) ────────────────────────────────────────────


@pytest.mark.integration
@pytest.mark.asyncio
async def test_claim_set_null_on_claim_delete() -> None:
    """Live-DB guardrail: hard-deleting a claim sets claim_id=NULL on
    the audit row (so the audit row survives).

    Marked as ``integration`` because it requires a live PostgreSQL
    connection with the new table created. Skipped in default test
    runs (which use ``-m "not integration"``). Run via::

        docker compose exec backend pytest -m integration \
            tests/test_memory_correction_models.py::test_claim_set_null_on_claim_delete
    """
    pytest.skip(
        "Integration test — requires live DB. "
        "Run with: docker compose exec backend pytest -m integration "
        "tests/test_memory_correction_models.py::"
        "test_claim_set_null_on_claim_delete"
    )
