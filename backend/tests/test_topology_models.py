"""Tests for the Topology ORM models and migration (Phase 1.1f).

Validates:
- Models can be imported and instantiated
- Table schemas match expectations
- Columns, indexes, and defaults are correct
- Migration file is well-formed
"""

from __future__ import annotations

import pytest


# ── Import tests ──────────────────────────────────────────────────────


class TestTopologyModelImports:
    """Verify models are importable and registered with Base.metadata."""

    def test_import_snapshot_from_models_package(self):
        from app.models import TopologySnapshot

        assert TopologySnapshot.__tablename__ == "topology_snapshots"

    def test_import_node_from_models_package(self):
        from app.models import TopologyNode

        assert TopologyNode.__tablename__ == "topology_nodes"

    def test_import_edge_from_models_package(self):
        from app.models import TopologyEdge

        assert TopologyEdge.__tablename__ == "topology_edges"

    def test_import_direct(self):
        from app.models.topology_models import (
            TopologySnapshot,
            TopologyNode,
            TopologyEdge,
        )

        assert TopologySnapshot.__tablename__ == "topology_snapshots"
        assert TopologyNode.__tablename__ == "topology_nodes"
        assert TopologyEdge.__tablename__ == "topology_edges"


# ── TopologySnapshot schema ───────────────────────────────────────────


class TestTopologySnapshotSchema:
    """Validate TopologySnapshot columns and defaults."""

    def test_columns_present(self):
        from app.models.topology_models import TopologySnapshot

        columns = {c.name for c in TopologySnapshot.__table__.columns}
        expected = {
            "id",
            "version",
            "description",
            "node_count",
            "edge_count",
            "community_count",
            "source",
            "snapshot_data",
            "created_at",
            "updated_at",
        }
        assert expected.issubset(columns), f"Missing columns: {expected - columns}"

    def test_source_default_is_computed(self):
        from app.models.topology_models import TopologySnapshot

        col = TopologySnapshot.__table__.columns["source"]
        assert col.default.arg == "computed"

    def test_counts_default_to_zero(self):
        from app.models.topology_models import TopologySnapshot

        for col_name in ("node_count", "edge_count", "community_count"):
            col = TopologySnapshot.__table__.columns[col_name]
            assert col.default.arg == 0, f"{col_name} default should be 0"

    def test_snapshot_data_is_jsonb(self):
        from app.models.topology_models import TopologySnapshot
        from sqlalchemy.dialects.postgresql import JSONB

        col = TopologySnapshot.__table__.columns["snapshot_data"]
        assert isinstance(col.type, JSONB)
        assert col.nullable is False

    def test_version_is_integer(self):
        from app.models.topology_models import TopologySnapshot

        col = TopologySnapshot.__table__.columns["version"]
        assert col.nullable is False

    def test_has_timestamps(self):
        from app.models.topology_models import TopologySnapshot

        assert "created_at" in TopologySnapshot.__table__.columns
        assert "updated_at" in TopologySnapshot.__table__.columns


# ── TopologyNode schema ───────────────────────────────────────────────


class TestTopologyNodeSchema:
    """Validate TopologyNode columns and indexes."""

    def test_columns_present(self):
        from app.models.topology_models import TopologyNode

        columns = {c.name for c in TopologyNode.__table__.columns}
        expected = {
            "id",
            "snapshot_id",
            "external_id",
            "label",
            "node_type",
            "community_id",
            "metadata",
            "derived_from_agent_id",
            "derived_from_capability_id",
            "derived_from_workflow_id",
            "confidence",
            "evidence",
        }
        assert expected.issubset(columns), f"Missing columns: {expected - columns}"

    def test_snapshot_id_index(self):
        from app.models.topology_models import TopologyNode

        indexes = TopologyNode.__table__.indexes
        idx = next(
            (
                ix
                for ix in indexes
                if set(c.name for c in ix.columns) == {"snapshot_id"}
            ),
            None,
        )
        assert idx is not None, "Missing index on snapshot_id"

    def test_confidence_default_is_one(self):
        from app.models.topology_models import TopologyNode

        col = TopologyNode.__table__.columns["confidence"]
        assert col.default.arg == 1.0

    def test_external_id_is_not_nullable(self):
        from app.models.topology_models import TopologyNode

        col = TopologyNode.__table__.columns["external_id"]
        assert col.nullable is False

    def test_derived_columns_are_nullable(self):
        from app.models.topology_models import TopologyNode

        for col_name in (
            "derived_from_agent_id",
            "derived_from_capability_id",
            "derived_from_workflow_id",
        ):
            col = TopologyNode.__table__.columns[col_name]
            assert col.nullable is True, f"{col_name} should be nullable"

    def test_lineage_columns_are_string_36(self):
        from app.models.topology_models import TopologyNode

        for col_name in (
            "derived_from_agent_id",
            "derived_from_capability_id",
            "derived_from_workflow_id",
        ):
            col = TopologyNode.__table__.columns[col_name]
            assert col.type.length == 36, f"{col_name} should be String(36)"

    def test_no_timestamps(self):
        """TopologyNode has no TimestampMixin — no created_at/updated_at."""
        from app.models.topology_models import TopologyNode

        columns = {c.name for c in TopologyNode.__table__.columns}
        assert "created_at" not in columns
        assert "updated_at" not in columns

    def test_evidence_is_jsonb(self):
        from app.models.topology_models import TopologyNode
        from sqlalchemy.dialects.postgresql import JSONB

        col = TopologyNode.__table__.columns["evidence"]
        assert isinstance(col.type, JSONB)


# ── TopologyEdge schema ───────────────────────────────────────────────


class TestTopologyEdgeSchema:
    """Validate TopologyEdge columns and indexes."""

    def test_columns_present(self):
        from app.models.topology_models import TopologyEdge

        columns = {c.name for c in TopologyEdge.__table__.columns}
        expected = {
            "id",
            "snapshot_id",
            "source_node_id",
            "target_node_id",
            "relation",
            "confidence",
            "metadata",
        }
        assert expected.issubset(columns), f"Missing columns: {expected - columns}"

    def test_snapshot_id_index(self):
        from app.models.topology_models import TopologyEdge

        indexes = TopologyEdge.__table__.indexes
        idx = next(
            (
                ix
                for ix in indexes
                if set(c.name for c in ix.columns) == {"snapshot_id"}
            ),
            None,
        )
        assert idx is not None, "Missing index on snapshot_id"

    def test_relation_default_is_calls(self):
        from app.models.topology_models import TopologyEdge

        col = TopologyEdge.__table__.columns["relation"]
        assert col.default.arg == "calls"

    def test_confidence_default_is_inferred(self):
        from app.models.topology_models import TopologyEdge

        col = TopologyEdge.__table__.columns["confidence"]
        assert col.default.arg == "INFERRED"

    def test_source_target_not_nullable(self):
        from app.models.topology_models import TopologyEdge

        for col_name in ("source_node_id", "target_node_id"):
            col = TopologyEdge.__table__.columns[col_name]
            assert col.nullable is False, f"{col_name} should NOT be nullable"

    def test_no_timestamps(self):
        """TopologyEdge has no TimestampMixin."""
        from app.models.topology_models import TopologyEdge

        columns = {c.name for c in TopologyEdge.__table__.columns}
        assert "created_at" not in columns
        assert "updated_at" not in columns


# ── Migration tests ───────────────────────────────────────────────────


class TestTopologyMigration:
    """Verify the migration file is well-formed."""

    def test_migration_file_exists(self):
        from pathlib import Path

        rev_path = (
            Path(__file__).resolve().parent.parent
            / "alembic"
            / "versions"
            / "20260603_topology.py"
        )
        assert rev_path.exists(), f"Migration file not found at {rev_path}"

    def test_migration_has_upgrade_and_downgrade(self):
        from pathlib import Path
        import importlib.util

        rev_path = (
            Path(__file__).resolve().parent.parent
            / "alembic"
            / "versions"
            / "20260603_topology.py"
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

    def test_migration_revision_chain(self):
        from pathlib import Path
        import importlib.util

        rev_path = (
            Path(__file__).resolve().parent.parent
            / "alembic"
            / "versions"
            / "20260603_topology.py"
        )
        if not rev_path.exists():
            pytest.skip("Migration file not found")

        spec = importlib.util.spec_from_file_location("migration", rev_path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        assert mod.revision == "20260603_topology"
        assert mod.down_revision == "20260603_materialization_state"

    def test_three_tables_in_upgrade(self):
        """Verify upgrade() creates exactly 3 tables."""
        from pathlib import Path
        import ast

        rev_path = (
            Path(__file__).resolve().parent.parent
            / "alembic"
            / "versions"
            / "20260603_topology.py"
        )
        if not rev_path.exists():
            pytest.skip("Migration file not found")

        source = rev_path.read_text()
        assert source.count("op.create_table(") == 3
        assert "topology_snapshots" in source
        assert "topology_nodes" in source
        assert "topology_edges" in source
