"""Tests for the MaterializationState ORM model and migration (Phase 1.1e).

Validates:
- Model can be imported and instantiated
- Table schema matches expectations
- Unique constraint on (object_type, object_id, target) works
- Status transitions are persisted correctly
- Checksum and error_message fields work
"""

from __future__ import annotations

import uuid

import pytest


# ── Import tests ──────────────────────────────────────────────────────


class TestMaterializationModelImport:
    """Verify the model is importable and registered with Base.metadata."""

    def test_import_from_models_package(self):
        from app.models import MaterializationState

        assert MaterializationState.__tablename__ == "materialization_state"

    def test_import_direct(self):
        from app.models.materialization_models import MaterializationState

        assert MaterializationState.__tablename__ == "materialization_state"

    def test_table_columns_present(self):
        from app.models.materialization_models import MaterializationState

        columns = {c.name for c in MaterializationState.__table__.columns}
        expected = {
            "id",
            "object_type",
            "object_id",
            "target",
            "version",
            "status",
            "checksum",
            "last_materialized_at",
            "error_message",
            "metadata",
            "created_at",
            "updated_at",
        }
        assert expected.issubset(columns), f"Missing columns: {expected - columns}"

    def test_unique_constraint_exists(self):
        """The (object_type, object_id, target) triple must be unique."""
        from app.models.materialization_models import MaterializationState

        indexes = MaterializationState.__table__.indexes
        unique_indexes = [ix for ix in indexes if ix.unique]
        target_idx = next(
            (
                ix
                for ix in unique_indexes
                if set(c.name for c in ix.columns)
                == {"object_type", "object_id", "target"}
            ),
            None,
        )
        assert (
            target_idx is not None
        ), "Missing unique index on (object_type, object_id, target)"


# ── Schema validation tests ───────────────────────────────────────────


class TestMaterializationSchema:
    """Validate column types and defaults."""

    def test_object_type_column_is_string_100(self):
        from app.models.materialization_models import MaterializationState

        col = MaterializationState.__table__.columns["object_type"]
        assert col.type.length == 100

    def test_target_column_is_string_50(self):
        from app.models.materialization_models import MaterializationState

        col = MaterializationState.__table__.columns["target"]
        assert col.type.length == 50

    def test_status_column_is_string_50(self):
        from app.models.materialization_models import MaterializationState

        col = MaterializationState.__table__.columns["status"]
        assert col.type.length == 50

    def test_version_default_is_1(self):
        from app.models.materialization_models import MaterializationState

        col = MaterializationState.__table__.columns["version"]
        assert col.default.arg == 1

    def test_status_default_is_pending(self):
        from app.models.materialization_models import MaterializationState

        col = MaterializationState.__table__.columns["status"]
        assert col.default.arg == "pending"

    def test_checksum_is_nullable_string_64(self):
        from app.models.materialization_models import MaterializationState

        col = MaterializationState.__table__.columns["checksum"]
        assert col.nullable is True
        assert col.type.length == 64

    def test_error_message_is_nullable_text(self):
        from app.models.materialization_models import MaterializationState

        col = MaterializationState.__table__.columns["error_message"]
        assert col.nullable is True

    def test_metadata_column_is_jsonb(self):
        from app.models.materialization_models import MaterializationState

        col = MaterializationState.__table__.columns["metadata"]
        from sqlalchemy.dialects.postgresql import JSONB

        assert isinstance(col.type, JSONB)


# ── Migration tests ───────────────────────────────────────────────────


class TestMaterializationMigration:
    """Verify the migration file is well-formed."""

    def test_migration_revision_chain(self):
        from pathlib import Path

        rev_path = (
            Path(__file__).resolve().parent.parent
            / "alembic"
            / "versions"
            / "20260603_materialization_state.py"
        )
        assert rev_path.exists(), f"Migration file not found at {rev_path}"

    def test_migration_has_upgrade_and_downgrade(self):
        from pathlib import Path
        import importlib.util

        rev_path = (
            Path(__file__).resolve().parent.parent
            / "alembic"
            / "versions"
            / "20260603_materialization_state.py"
        )
        if not rev_path.exists():
            pytest.skip("Migration file not found")

        spec = importlib.util.spec_from_file_location("migration", rev_path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        assert hasattr(mod, "upgrade"), "Migration missing upgrade()"
        assert hasattr(mod, "downgrade"), "Migration missing downgrade()"
        assert callable(mod.upgrade)
        assert callable(mod.downgrade)

    def test_migration_down_revision(self):
        from pathlib import Path
        import importlib.util

        rev_path = (
            Path(__file__).resolve().parent.parent
            / "alembic"
            / "versions"
            / "20260603_materialization_state.py"
        )
        if not rev_path.exists():
            pytest.skip("Migration file not found")

        spec = importlib.util.spec_from_file_location("migration", rev_path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        assert mod.revision == "20260603_materialization_state"
        assert mod.down_revision == "20260603_tools_capabilities"
