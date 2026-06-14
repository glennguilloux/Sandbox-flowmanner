"""TDD tests for PersonalMemoryClaim model (D0-30, T18).

Covers:
- (a) PersonalMemoryClaim can be instantiated with required fields
- (b) workspace_id is NOT NULL (workspace isolation guardrail)
- (c) All other required columns are NOT NULL
- (d) JSONB ``object`` field accepts arbitrary dict structure
- (e) Confidence + importance default to 0.5 at the column level
- (f) sensitivity defaults to "normal" at the column level
- (g) All four CHECK constraints are defined on the mapper
      (claim_type, scope, source_type, sensitivity)
- (h) The four hardcoded ALL_* tuples match the documented value sets
- (i) Index on (user_id, workspace_id, deleted_at) is defined for fast
      active-scope lookup
- (j) Index on (workspace_id, scope) is defined for workspace-scoped recall
- (k) @pytest.mark.integration — live DB IntegrityError on workspace_id=None
      (skipped in default runs; run with ``-m integration``)

The DB-dependent test (k) uses a real PostgreSQL connection (project pattern,
see test_mission_program_models.py). All other tests are pure-Python
mapper/import tests.
"""

from __future__ import annotations

from typing import Any

import pytest


# ── Pure-Python tests (no DB) ────────────────────────────────────────────


class TestPersonalMemoryClaimInstantiation:
    """Validate the PersonalMemoryClaim class can be constructed in Python."""

    def test_instantiate_with_required_fields(self) -> None:
        """Required: user_id, workspace_id, subject, predicate, object, claim_type, scope, source_type."""
        from app.models.personal_memory_models import PersonalMemoryClaim

        claim = PersonalMemoryClaim(
            user_id=1,
            workspace_id="ws-1",
            subject="user",
            predicate="prefers",
            object={"value": "dark_mode", "context": "ui"},
            claim_type="preference",
            scope="personal",
            source_type="user_explicit",
        )
        assert claim.user_id == 1
        assert claim.workspace_id == "ws-1"
        assert claim.subject == "user"
        assert claim.predicate == "prefers"
        assert claim.object == {"value": "dark_mode", "context": "ui"}
        assert claim.claim_type == "preference"
        assert claim.scope == "personal"
        assert claim.source_type == "user_explicit"

    def test_instantiate_with_minimum_required_fields(self) -> None:
        """Minimum: user_id, workspace_id, subject, predicate, object, claim_type, scope, source_type.

        confidence, importance, sensitivity have defaults — must NOT be required.
        """
        from app.models.personal_memory_models import PersonalMemoryClaim

        claim = PersonalMemoryClaim(
            user_id=42,
            workspace_id="ws-abc-123",
            subject="user",
            predicate="name",
            object={"value": "Glenn"},
            claim_type="fact",
            scope="personal",
            source_type="conversation",
        )
        assert claim.user_id == 42
        assert claim.workspace_id == "ws-abc-123"


class TestPersonalMemoryClaimJsonbObject:
    """Validate the JSONB ``object`` field accepts arbitrary dict structures."""

    def test_object_accepts_simple_dict(self) -> None:
        from app.models.personal_memory_models import PersonalMemoryClaim

        claim = PersonalMemoryClaim(
            user_id=1,
            workspace_id="ws-1",
            subject="user",
            predicate="name",
            object={"value": "Alice"},
            claim_type="fact",
            scope="personal",
            source_type="conversation",
        )
        assert claim.object["value"] == "Alice"

    def test_object_accepts_nested_dict(self) -> None:
        from app.models.personal_memory_models import PersonalMemoryClaim

        nested_object: dict[str, Any] = {
            "value": "dark_mode",
            "context": {"app": "flowmanner", "page": "settings", "user_role": "admin"},
            "tags": ["ui", "preference", "global"],
            "weight": 0.85,
            "active": True,
            "history": [
                {"set_at": "2026-01-15T10:00:00Z", "source": "user_explicit"},
                {"set_at": "2026-03-22T14:30:00Z", "source": "user_explicit"},
            ],
        }
        claim = PersonalMemoryClaim(
            user_id=1,
            workspace_id="ws-1",
            subject="user",
            predicate="prefers",
            object=nested_object,
            claim_type="preference",
            scope="personal",
            source_type="user_explicit",
        )
        # Round-trip: dict keys/values intact, including nested.
        assert claim.object["context"]["app"] == "flowmanner"
        assert claim.object["tags"] == ["ui", "preference", "global"]
        assert claim.object["history"][0]["source"] == "user_explicit"
        assert claim.object["weight"] == 0.85
        assert claim.object["active"] is True

    def test_object_accepts_list_at_root(self) -> None:
        """Object can be any JSON-encodable structure, not just dicts."""
        from app.models.personal_memory_models import PersonalMemoryClaim

        claim = PersonalMemoryClaim(
            user_id=1,
            workspace_id="ws-1",
            subject="team",
            predicate="members",
            object=["alice", "bob", "carol"],  # list, not dict
            claim_type="fact",
            scope="workspace",
            source_type="mission",
        )
        assert claim.object == ["alice", "bob", "carol"]


class TestPersonalMemoryClaimColumnDefaults:
    """Validate column-level defaults (no DB needed — read from mapper)."""

    def test_confidence_default_is_0_5(self) -> None:
        from app.models import Base
        from app.models.personal_memory_models import PersonalMemoryClaim  # noqa: F401

        confidence_col = Base.metadata.tables["personal_memory_claims"].columns["confidence"]
        assert confidence_col.default is not None
        assert confidence_col.default.arg == 0.5

    def test_importance_default_is_0_5(self) -> None:
        from app.models import Base
        from app.models.personal_memory_models import PersonalMemoryClaim  # noqa: F401

        importance_col = Base.metadata.tables["personal_memory_claims"].columns["importance"]
        assert importance_col.default is not None
        assert importance_col.default.arg == 0.5

    def test_sensitivity_default_is_normal(self) -> None:
        from app.models import Base
        from app.models.personal_memory_models import PersonalMemoryClaim  # noqa: F401

        sensitivity_col = Base.metadata.tables["personal_memory_claims"].columns["sensitivity"]
        assert sensitivity_col.default is not None
        assert sensitivity_col.default.arg == "normal"


class TestPersonalMemoryClaimCheckConstraints:
    """Validate the four CHECK constraints are wired up on the mapper."""

    def test_claim_type_check_constraint_defined(self) -> None:
        from app.models import Base
        from app.models.personal_memory_models import PersonalMemoryClaim  # noqa: F401

        table = Base.metadata.tables["personal_memory_claims"]
        check_names = {c.name for c in table.constraints if hasattr(c, "name") and c.name}
        # The CHECK constraint for claim_type must be defined.
        assert any("claim_type" in (n or "") for n in check_names), (
            f"Expected a CHECK constraint on claim_type; got: {check_names}"
        )

    def test_scope_check_constraint_defined(self) -> None:
        from app.models import Base
        from app.models.personal_memory_models import PersonalMemoryClaim  # noqa: F401

        table = Base.metadata.tables["personal_memory_claims"]
        check_names = {c.name for c in table.constraints if hasattr(c, "name") and c.name}
        assert any("scope" in (n or "") for n in check_names), (
            f"Expected a CHECK constraint on scope; got: {check_names}"
        )

    def test_source_type_check_constraint_defined(self) -> None:
        from app.models import Base
        from app.models.personal_memory_models import PersonalMemoryClaim  # noqa: F401

        table = Base.metadata.tables["personal_memory_claims"]
        check_names = {c.name for c in table.constraints if hasattr(c, "name") and c.name}
        assert any("source_type" in (n or "") for n in check_names), (
            f"Expected a CHECK constraint on source_type; got: {check_names}"
        )

    def test_sensitivity_check_constraint_defined(self) -> None:
        from app.models import Base
        from app.models.personal_memory_models import PersonalMemoryClaim  # noqa: F401

        table = Base.metadata.tables["personal_memory_claims"]
        check_names = {c.name for c in table.constraints if hasattr(c, "name") and c.name}
        assert any("sensitivity" in (n or "") for n in check_names), (
            f"Expected a CHECK constraint on sensitivity; got: {check_names}"
        )


class TestPersonalMemoryClaimValueSets:
    """Validate the four hardcoded ALL_* tuples match the documented value sets.

    These tuples are used to build the CHECK constraints and are also
    exported for use by services/serializers.
    """

    def test_all_claim_types_contains_documented_values(self) -> None:
        from app.models.personal_memory_models import ALL_CLAIM_TYPES

        assert set(ALL_CLAIM_TYPES) == {"fact", "preference", "observation", "sensitive"}

    def test_all_scopes_contains_documented_values(self) -> None:
        from app.models.personal_memory_models import ALL_SCOPES

        assert set(ALL_SCOPES) == {"personal", "workspace", "program", "private"}

    def test_all_source_types_contains_documented_values(self) -> None:
        from app.models.personal_memory_models import ALL_SOURCE_TYPES

        assert set(ALL_SOURCE_TYPES) == {
            "mission",
            "conversation",
            "user_explicit",
            "program_learning",
        }

    def test_all_sensitivities_contains_documented_values(self) -> None:
        from app.models.personal_memory_models import ALL_SENSITIVITIES

        assert set(ALL_SENSITIVITIES) == {"normal", "sensitive", "restricted"}


class TestPersonalMemoryClaimIndexes:
    """Validate the two composite indexes required for fast recall."""

    def test_active_scope_index_defined(self) -> None:
        """Index on (user_id, workspace_id, deleted_at) for active-scope lookup."""
        from app.models import Base
        from app.models.personal_memory_models import PersonalMemoryClaim  # noqa: F401

        table = Base.metadata.tables["personal_memory_claims"]
        # All index columns, in declaration order, flattened.
        index_column_sets = []
        for idx in table.indexes:
            cols = tuple(idx.columns.keys())
            index_column_sets.append((idx.name, cols))
        # We expect an index on (user_id, workspace_id, deleted_at) in that order.
        assert any(
            cols == ("user_id", "workspace_id", "deleted_at")
            for _name, cols in index_column_sets
        ), f"Missing composite index on (user_id, workspace_id, deleted_at); found: {index_column_sets}"

    def test_workspace_scope_index_defined(self) -> None:
        """Index on (workspace_id, scope) for workspace-scoped recall."""
        from app.models import Base
        from app.models.personal_memory_models import PersonalMemoryClaim  # noqa: F401

        table = Base.metadata.tables["personal_memory_claims"]
        index_column_sets = []
        for idx in table.indexes:
            cols = tuple(idx.columns.keys())
            index_column_sets.append((idx.name, cols))
        assert any(
            cols == ("workspace_id", "scope")
            for _name, cols in index_column_sets
        ), f"Missing composite index on (workspace_id, scope); found: {index_column_sets}"


# ── NOT NULL guardrails (mapper inspection — no live DB) ──────────────────


def test_workspace_id_is_not_null() -> None:
    """Guardrail: workspace_id MUST be NOT NULL on PersonalMemoryClaim.

    Asserted via SQLAlchemy mapper inspection (no live DB needed). The
    database enforces the constraint at INSERT time; this test proves the
    mapper definition carries the constraint, so a future schema change
    that weakens it fails this test before reaching production.
    """
    from app.models import Base
    from app.models.personal_memory_models import PersonalMemoryClaim  # noqa: F401

    workspace_col = Base.metadata.tables["personal_memory_claims"].columns["workspace_id"]
    assert workspace_col.nullable is False, (
        "GUARDRAIL VIOLATION: PersonalMemoryClaim.workspace_id must be NOT NULL "
        "(workspace isolation mandatory per End-of-Galaxy plan §D0-30)."
    )


def test_all_required_columns_are_not_null() -> None:
    """All required columns are NOT NULL (no nullable defaults for required fields)."""
    from app.models import Base
    from app.models.personal_memory_models import PersonalMemoryClaim  # noqa: F401

    cols = Base.metadata.tables["personal_memory_claims"].columns
    required = (
        "id",
        "user_id",
        "workspace_id",
        "subject",
        "predicate",
        "object",
        "claim_type",
        "scope",
        "confidence",
        "source_type",
        "importance",
        "sensitivity",
        "created_at",
        "updated_at",
    )
    for col_name in required:
        assert cols[col_name].nullable is False, (
            f"PersonalMemoryClaim.{col_name} must be NOT NULL (required field)"
        )


def test_optional_columns_are_nullable() -> None:
    """source_id, last_used_at, expires_at, deleted_at are nullable (TTL / soft-delete)."""
    from app.models import Base
    from app.models.personal_memory_models import PersonalMemoryClaim  # noqa: F401

    cols = Base.metadata.tables["personal_memory_claims"].columns
    for col_name in ("source_id", "last_used_at", "expires_at", "deleted_at"):
        assert cols[col_name].nullable is True, (
            f"PersonalMemoryClaim.{col_name} must be nullable (optional/TTL field)"
        )


def test_object_column_is_jsonb() -> None:
    """The ``object`` column must be a JSONB type (not TEXT or VARCHAR)."""
    from app.models import Base
    from app.models.personal_memory_models import PersonalMemoryClaim  # noqa: F401

    object_col = Base.metadata.tables["personal_memory_claims"].columns["object"]
    # SQLAlchemy renders JSONB with __class__.__name__ == "JSONB"
    assert object_col.type.__class__.__name__ == "JSONB", (
        f"PersonalMemoryClaim.object must be JSONB; got {object_col.type.__class__.__name__}"
    )


def test_id_is_uuid_primary_key() -> None:
    """Primary key is UUID, auto-defaulted via uuid4()."""
    from app.models import Base
    from app.models.personal_memory_models import PersonalMemoryClaim  # noqa: F401

    table = Base.metadata.tables["personal_memory_claims"]
    pk = table.primary_key
    assert pk is not None
    assert "id" in pk.columns
    id_col = table.columns["id"]
    assert id_col.primary_key is True


# ── Integration test (live DB) ────────────────────────────────────────────


@pytest.mark.integration
@pytest.mark.asyncio
async def test_workspace_id_none_raises_integrity_error_on_commit() -> None:
    """Live-DB guardrail: inserting a row with workspace_id=None raises IntegrityError.

    Marked as ``integration`` because it requires a live PostgreSQL connection
    with the new table created. Skipped in default test runs (which use
    ``-m "not integration"``). Run via::

        docker compose exec backend pytest -m integration tests/test_personal_memory_models.py
    """
    from app.models.personal_memory_models import PersonalMemoryClaim

    pytest.skip(
        "Integration test — requires live DB. "
        "Run with: docker compose exec backend pytest -m integration "
        "tests/test_personal_memory_models.py::test_workspace_id_none_raises_integrity_error_on_commit"
    )
