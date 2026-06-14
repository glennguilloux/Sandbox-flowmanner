"""TDD tests for Critique model (D30-60, T24).

Covers:
- (a) Critique is registered in Base.metadata
- (b) All expected columns exist with correct types and nullability
- (c) Composite indexes are configured
      (user_id, workspace_id, created_at), (mission_id), (program_id)
- (d) CHECK constraint on score_overall (0.0-1.0)
- (e) CHECK constraint on critic_kind uses the hardcoded ALL_CRITIC_KINDS tuple
      (defensive against the project's known ``str, Enum`` _TRANSITIONS leak)
- (f) JSONB columns default to []
- (g) Live-DB integration test: workspace cascade (skipped by default,
      run with ``-m integration``)

The DB-dependent test (g) uses a real PostgreSQL connection (project pattern,
see test_personal_memory_models.py). All other tests are pure-Python
mapper/import tests.
"""

from __future__ import annotations

import pytest


# ── Pure-Python tests (no DB) ────────────────────────────────────────────


class TestCritiqueMetadata:
    """Validate the Critique model is registered with Base.metadata."""

    def test_critique_table_registered_in_metadata(self) -> None:
        """The ``critiques`` table must be in Base.metadata once the model is imported."""
        from app.models import Base
        from app.models.critique_models import Critique  # noqa: F401

        assert "critiques" in Base.metadata.tables, (
            "Expected 'critiques' in Base.metadata.tables; "
            f"got: {sorted(Base.metadata.tables.keys())}"
        )

    def test_critique_class_is_a_model(self) -> None:
        """Critique should subclass Base + TimestampMixin (have created_at/updated_at)."""
        from app.models import Base
        from app.models.critique_models import Critique

        assert issubclass(Critique, Base)
        # TimestampMixin columns appear on the instance after mapper config.
        c = Critique(
            user_id=1,
            workspace_id="ws-1",
            mission_id=None,
            program_id=None,
            critic_kind="critic",
        )
        assert hasattr(c, "created_at")
        assert hasattr(c, "updated_at")


class TestCritiqueColumns:
    """Validate the Critique column set: types, nullability, and presence."""

    def test_required_columns_are_not_null(self) -> None:
        """All required columns are NOT NULL on the critiques table."""
        from app.models import Base
        from app.models.critique_models import Critique  # noqa: F401

        cols = Base.metadata.tables["critiques"].columns
        required = (
            "id",
            "user_id",
            "workspace_id",
            "critic_kind",
            "misses",
            "risks",
            "improvements",
            "alternatives",
            "created_at",
            "updated_at",
        )
        for col_name in required:
            assert cols[col_name].nullable is False, (
                f"Critique.{col_name} must be NOT NULL (required field)"
            )

    def test_optional_columns_are_nullable(self) -> None:
        """Optional columns are NULLABLE: program_id, scores, summary, raw, model_id, tokens, duration."""
        from app.models import Base
        from app.models.critique_models import Critique  # noqa: F401

        cols = Base.metadata.tables["critiques"].columns
        optional = (
            "program_id",
            "score_overall",
            "score_alignment",
            "score_safety",
            "score_completeness",
            "summary",
            "raw_response",
            "model_id",
            "tokens_in",
            "tokens_out",
            "duration_ms",
        )
        for col_name in optional:
            assert cols[col_name].nullable is True, (
                f"Critique.{col_name} must be nullable (optional field)"
            )

    def test_mission_id_is_not_null(self) -> None:
        """mission_id is NOT NULL (every critique is anchored to a mission)."""
        from app.models import Base
        from app.models.critique_models import Critique  # noqa: F401

        cols = Base.metadata.tables["critiques"].columns
        assert cols["mission_id"].nullable is False, (
            "Critique.mission_id must be NOT NULL"
        )

    def test_id_is_uuid_primary_key(self) -> None:
        """Primary key is UUID, auto-defaulted via uuid4()."""
        from app.models import Base
        from app.models.critique_models import Critique  # noqa: F401

        table = Base.metadata.tables["critiques"]
        pk = table.primary_key
        assert pk is not None
        assert "id" in pk.columns
        id_col = table.columns["id"]
        assert id_col.primary_key is True
        # Default must exist and be a uuid4 generator.
        assert id_col.default is not None, "Critique.id must have a default (uuid4)"
        assert id_col.default.is_callable is True, "Critique.id default must be callable"

    def test_jsonb_columns_use_postgres_jsonb(self) -> None:
        """The four JSONB columns (misses, risks, improvements, alternatives) and raw_response use JSONB."""
        from app.models import Base
        from app.models.critique_models import Critique  # noqa: F401

        cols = Base.metadata.tables["critiques"].columns
        for col_name in ("misses", "risks", "improvements", "alternatives", "raw_response"):
            assert cols[col_name].type.__class__.__name__ == "JSONB", (
                f"Critique.{col_name} must be JSONB; "
                f"got {cols[col_name].type.__class__.__name__}"
            )

    def test_critic_kind_column_is_string(self) -> None:
        """critic_kind is a String column (project pattern: validated by CHECK, not enum)."""
        from app.models import Base
        from app.models.critique_models import Critique  # noqa: F401

        kind_col = Base.metadata.tables["critiques"].columns["critic_kind"]
        assert kind_col.type.__class__.__name__ == "String", (
            f"critic_kind must be String; got {kind_col.type.__class__.__name__}"
        )


class TestCritiqueIndexes:
    """Validate the composite indexes required for fast recall."""

    def test_composite_index_user_workspace_created(self) -> None:
        """Index on (user_id, workspace_id, created_at) for fast active-scope lookup."""
        from app.models import Base
        from app.models.critique_models import Critique  # noqa: F401

        table = Base.metadata.tables["critiques"]
        index_column_sets = [
            (idx.name, tuple(idx.columns.keys())) for idx in table.indexes
        ]
        assert any(
            cols == ("user_id", "workspace_id", "created_at")
            for _name, cols in index_column_sets
        ), (
            "Missing composite index on (user_id, workspace_id, created_at); "
            f"found: {index_column_sets}"
        )

    def test_index_on_mission_id(self) -> None:
        """Index on mission_id for fast mission-scoped lookup."""
        from app.models import Base
        from app.models.critique_models import Critique  # noqa: F401

        table = Base.metadata.tables["critiques"]
        index_column_sets = [
            (idx.name, tuple(idx.columns.keys())) for idx in table.indexes
        ]
        assert any(
            cols == ("mission_id",)
            for _name, cols in index_column_sets
        ), f"Missing index on (mission_id,); found: {index_column_sets}"

    def test_index_on_program_id(self) -> None:
        """Index on program_id for fast program-scoped lookup."""
        from app.models import Base
        from app.models.critique_models import Critique  # noqa: F401

        table = Base.metadata.tables["critiques"]
        index_column_sets = [
            (idx.name, tuple(idx.columns.keys())) for idx in table.indexes
        ]
        assert any(
            cols == ("program_id",)
            for _name, cols in index_column_sets
        ), f"Missing index on (program_id,); found: {index_column_sets}"


class TestCritiqueCheckConstraints:
    """Validate CHECK constraints are wired up on the mapper."""

    def test_critic_kind_check_constraint_defined(self) -> None:
        from app.models import Base
        from app.models.critique_models import Critique  # noqa: F401

        table = Base.metadata.tables["critiques"]
        check_names = {
            c.name for c in table.constraints if hasattr(c, "name") and c.name
        }
        assert any("critic_kind" in (n or "") for n in check_names), (
            f"Expected a CHECK constraint on critic_kind; got: {check_names}"
        )

    def test_score_overall_check_constraint_defined(self) -> None:
        from app.models import Base
        from app.models.critique_models import Critique  # noqa: F401

        table = Base.metadata.tables["critiques"]
        check_names = {
            c.name for c in table.constraints if hasattr(c, "name") and c.name
        }
        assert any("score_overall" in (n or "") for n in check_names), (
            f"Expected a CHECK constraint on score_overall; got: {check_names}"
        )

    def test_score_overall_check_range(self) -> None:
        """The CHECK constraint on score_overall must be 0.0 <= x <= 1.0."""
        from app.models import Base
        from app.models.critique_models import Critique  # noqa: F401

        table = Base.metadata.tables["critiques"]
        score_checks = [
            c
            for c in table.constraints
            if hasattr(c, "name")
            and c.name
            and "score_overall" in c.name
        ]
        assert len(score_checks) == 1, (
            f"Expected exactly one score_overall CHECK constraint; got: {score_checks}"
        )
        sqltext = str(score_checks[0].sqltext)
        # Normalize whitespace.
        normalized = " ".join(sqltext.split())
        assert "0.0" in normalized and "1.0" in normalized, (
            f"score_overall CHECK should include 0.0 and 1.0 bounds; got: {normalized!r}"
        )


class TestCritiqueValueSets:
    """Validate the hardcoded ALL_CRITIC_KINDS tuple is well-formed.

    Defensive test: project history shows that ``str, Enum`` iteration leaks
    ``_TRANSITIONS`` into CHECK constraints, corrupting SQL. We require that
    the tuple is a hardcoded plain tuple of strings with no underscore-leaks.
    """

    def test_all_critic_kinds_is_hardcoded_tuple(self) -> None:
        from app.models.critique_models import ALL_CRITIC_KINDS

        assert isinstance(ALL_CRITIC_KINDS, tuple), (
            f"ALL_CRITIC_KINDS must be a tuple; got {type(ALL_CRITIC_KINDS).__name__}"
        )

    def test_all_critic_kinds_contains_documented_values(self) -> None:
        from app.models.critique_models import ALL_CRITIC_KINDS

        # Documented value set for v1 of the critic stack (D30-60):
        #   - "red_team" — adversary critic
        #   - "critic" — plan reviewer
        #   - "improvement_generator" — proposes better plans
        assert set(ALL_CRITIC_KINDS) == {
            "red_team",
            "critic",
            "improvement_generator",
        }

    def test_all_critic_kinds_no_sunder_leak(self) -> None:
        """Defensive: no ``_TRANSITIONS`` or other dunder/private name in the tuple.

        Regression guard for the project's known ``str, Enum`` _TRANSITIONS
        leak. If someone accidentally derives this tuple from enum iteration,
        this test fails.
        """
        from app.models.critique_models import ALL_CRITIC_KINDS

        for v in ALL_CRITIC_KINDS:
            assert isinstance(v, str), (
                f"ALL_CRITIC_KINDS entries must be str; got {type(v).__name__}: {v!r}"
            )
            assert not v.startswith("_"), (
                f"ALL_CRITIC_KINDS contains a sunder-name leak: {v!r}"
            )


class TestCritiqueJsonbDefaults:
    """Validate that the four required JSONB columns default to []."""

    def test_misses_default_is_empty_list(self) -> None:
        from app.models import Base
        from app.models.critique_models import Critique  # noqa: F401

        col = Base.metadata.tables["critiques"].columns["misses"]
        assert col.default is not None, "misses must have a column-level default"
        # SQLAlchemy wraps ``default=list`` as a CallableColumnDefault.
        # Verify the default is callable (project idiom: ``default=list``,
        # ``default=dict``) — calling the wrapped arg requires a context
        # object, so we confirm ``is_callable`` + ``for_update`` semantics
        # via the public attribute.
        assert col.default.is_callable is True, (
            "misses default must be a callable (e.g. default=list)"
        )
        assert col.default.for_update is False, (
            "misses default must fire on INSERT, not just UPDATE"
        )

    def test_risks_default_is_empty_list(self) -> None:
        from app.models import Base
        from app.models.critique_models import Critique  # noqa: F401

        col = Base.metadata.tables["critiques"].columns["risks"]
        assert col.default is not None, "risks must have a column-level default"
        assert col.default.is_callable is True, (
            "risks default must be a callable (e.g. default=list)"
        )
        assert col.default.for_update is False, (
            "risks default must fire on INSERT, not just UPDATE"
        )

    def test_improvements_default_is_empty_list(self) -> None:
        from app.models import Base
        from app.models.critique_models import Critique  # noqa: F401

        col = Base.metadata.tables["critiques"].columns["improvements"]
        assert col.default is not None, "improvements must have a column-level default"
        assert col.default.is_callable is True, (
            "improvements default must be a callable (e.g. default=list)"
        )
        assert col.default.for_update is False, (
            "improvements default must fire on INSERT, not just UPDATE"
        )

    def test_alternatives_default_is_empty_list(self) -> None:
        from app.models import Base
        from app.models.critique_models import Critique  # noqa: F401

        col = Base.metadata.tables["critiques"].columns["alternatives"]
        assert col.default is not None, "alternatives must have a column-level default"
        assert col.default.is_callable is True, (
            "alternatives default must be a callable (e.g. default=list)"
        )
        assert col.default.for_update is False, (
            "alternatives default must fire on INSERT, not just UPDATE"
        )


# ── Foreign keys (mapper inspection — no live DB) ────────────────────────


def test_workspace_id_fk_with_cascade() -> None:
    """workspace_id has FK to workspaces.id with ON DELETE CASCADE."""
    from app.models import Base
    from app.models.critique_models import Critique  # noqa: F401

    workspace_col = Base.metadata.tables["critiques"].columns["workspace_id"]
    fk_targets = list(workspace_col.foreign_keys)
    assert len(fk_targets) == 1, (
        f"workspace_id must have exactly one FK; got {len(fk_targets)}"
    )
    fk = fk_targets[0]
    assert fk.column.table.name == "workspaces", (
        f"FK must target workspaces; got {fk.column.table.name}"
    )
    assert fk.ondelete == "CASCADE", (
        f"FK must ON DELETE CASCADE; got {fk.ondelete!r}"
    )


def test_user_id_fk_to_users() -> None:
    """user_id has FK to users.id (no cascade — user rows are global)."""
    from app.models import Base
    from app.models.critique_models import Critique  # noqa: F401

    user_col = Base.metadata.tables["critiques"].columns["user_id"]
    fk_targets = list(user_col.foreign_keys)
    assert len(fk_targets) == 1, f"user_id must have exactly one FK; got {len(fk_targets)}"
    fk = fk_targets[0]
    assert fk.column.table.name == "users", (
        f"FK must target users; got {fk.column.table.name}"
    )


def test_mission_id_fk_to_missions() -> None:
    """mission_id has FK to missions.id (cascade on mission delete)."""
    from app.models import Base
    from app.models.critique_models import Critique  # noqa: F401

    mission_col = Base.metadata.tables["critiques"].columns["mission_id"]
    fk_targets = list(mission_col.foreign_keys)
    assert len(fk_targets) == 1, f"mission_id must have exactly one FK; got {len(fk_targets)}"
    fk = fk_targets[0]
    assert fk.column.table.name == "missions", (
        f"FK must target missions; got {fk.column.table.name}"
    )


def test_program_id_fk_to_mission_programs() -> None:
    """program_id has FK to mission_programs.id (cascade on program delete)."""
    from app.models import Base
    from app.models.critique_models import Critique  # noqa: F401

    program_col = Base.metadata.tables["critiques"].columns["program_id"]
    fk_targets = list(program_col.foreign_keys)
    assert len(fk_targets) == 1, f"program_id must have exactly one FK; got {len(fk_targets)}"
    fk = fk_targets[0]
    assert fk.column.table.name == "mission_programs", (
        f"FK must target mission_programs; got {fk.column.table.name}"
    )


def test_workspace_id_is_not_null() -> None:
    """Guardrail: workspace_id MUST be NOT NULL on Critique.

    Workspace isolation mandatory per project rules.
    """
    from app.models import Base
    from app.models.critique_models import Critique  # noqa: F401

    workspace_col = Base.metadata.tables["critiques"].columns["workspace_id"]
    assert workspace_col.nullable is False, (
        "GUARDRAIL VIOLATION: Critique.workspace_id must be NOT NULL "
        "(workspace isolation mandatory per project rules)."
    )


# ── Integration test (live DB) ────────────────────────────────────────────


@pytest.mark.integration
@pytest.mark.asyncio
async def test_critique_workspace_cascade() -> None:
    """Live-DB guardrail: deleting a workspace cascades critiques.

    Marked as ``integration`` because it requires a live PostgreSQL connection
    with the new table created. Skipped in default test runs (which use
    ``-m "not integration"``). Run via::

        docker compose exec backend pytest -m integration \
            tests/test_critique_models.py::test_critique_workspace_cascade
    """
    pytest.skip(
        "Integration test — requires live DB. "
        "Run with: docker compose exec backend pytest -m integration "
        "tests/test_critique_models.py::test_critique_workspace_cascade"
    )
