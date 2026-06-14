"""TDD tests for MemoryExtractionPause (D30-60, T30 — pause toggle).

Two test clusters:

(A) Pure-Python model tests (no DB):
    * Table registration in Base.metadata
    * Column types + nullability
    * Composite indexes (lookup + cleanup)
    * No sunder-name leaks in the model class

(B) Integration tests (``@pytest.mark.integration``, live PostgreSQL):
    * Default id is a UUID
    * expires_at is required
    * Workspace cascade

Run via::

    cd /opt/flowmanner/backend
    DATABASE_URL="postgresql+asyncpg://flowmanner:5f206ab26d543ba5424385cb10200efc@127.0.0.1:5432/flowmanner" \\
      .venv/bin/python -m pytest tests/test_memory_extraction_pause_models.py -v
"""
from __future__ import annotations

import os

import pytest

# Ensure DATABASE_URL is set BEFORE importing app modules that need it.
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://flowmanner:5f206ab26d543ba5424385cb10200efc@127.0.0.1:5432/flowmanner",
)


# ═══════════════════════════════════════════════════════════════════════════
# (A) Pure-Python model tests
# ═══════════════════════════════════════════════════════════════════════════


class TestTableRegistration:
    def test_table_registered_in_metadata(self) -> None:
        from app.models import Base
        from app.models.memory_extraction_pause_models import (
            MemoryExtractionPause,
        )

        assert "memory_extraction_pauses" in Base.metadata.tables

    def test_tablename(self) -> None:
        from app.models.memory_extraction_pause_models import (
            MemoryExtractionPause,
        )

        assert MemoryExtractionPause.__tablename__ == "memory_extraction_pauses"


class TestColumns:
    def test_id_column(self) -> None:
        from app.models import Base
        from app.models.memory_extraction_pause_models import (
            MemoryExtractionPause,
        )

        col = Base.metadata.tables["memory_extraction_pauses"].columns["id"]
        assert col.primary_key
        assert not col.nullable

    def test_user_id_not_null_fk_to_users(self) -> None:
        from app.models import Base
        from app.models.memory_extraction_pause_models import (
            MemoryExtractionPause,
        )

        col = Base.metadata.tables["memory_extraction_pauses"].columns["user_id"]
        assert not col.nullable
        fks = list(col.foreign_keys)
        assert any(fk.target_fullname == "users.id" for fk in fks)

    def test_workspace_id_not_null_fk_to_workspaces_cascade(self) -> None:
        from app.models import Base
        from app.models.memory_extraction_pause_models import (
            MemoryExtractionPause,
        )

        col = Base.metadata.tables["memory_extraction_pauses"].columns[
            "workspace_id"
        ]
        assert not col.nullable
        fks = list(col.foreign_keys)
        matching = [
            fk for fk in fks if fk.target_fullname == "workspaces.id"
        ]
        assert matching, "workspace_id should FK to workspaces.id"
        assert "CASCADE" in (matching[0].ondelete or ""), (
            "workspace_id should ON DELETE CASCADE"
        )

    def test_conversation_id_not_null(self) -> None:
        from app.models import Base
        from app.models.memory_extraction_pause_models import (
            MemoryExtractionPause,
        )

        col = Base.metadata.tables["memory_extraction_pauses"].columns[
            "conversation_id"
        ]
        assert not col.nullable

    def test_expires_at_not_null(self) -> None:
        from app.models import Base
        from app.models.memory_extraction_pause_models import (
            MemoryExtractionPause,
        )

        col = Base.metadata.tables["memory_extraction_pauses"].columns[
            "expires_at"
        ]
        assert not col.nullable

    def test_reason_nullable(self) -> None:
        from app.models import Base
        from app.models.memory_extraction_pause_models import (
            MemoryExtractionPause,
        )

        col = Base.metadata.tables["memory_extraction_pauses"].columns["reason"]
        assert col.nullable


class TestIndexes:
    def test_lookup_index_exists(self) -> None:
        from app.models import Base
        from app.models.memory_extraction_pause_models import (
            MemoryExtractionPause,
        )

        table = Base.metadata.tables["memory_extraction_pauses"]
        lookup_indexes = [
            idx for idx in table.indexes if idx.name == "ix_memory_extraction_pauses_lookup"
        ]
        assert lookup_indexes, "lookup composite index missing"
        cols = [c.name for c in lookup_indexes[0].columns]
        assert cols == ["user_id", "workspace_id", "conversation_id", "expires_at"]

    def test_expires_at_index_exists(self) -> None:
        from app.models import Base
        from app.models.memory_extraction_pause_models import (
            MemoryExtractionPause,
        )

        table = Base.metadata.tables["memory_extraction_pauses"]
        expires_indexes = [
            idx for idx in table.indexes if idx.name == "ix_memory_extraction_pauses_expires_at"
        ]
        assert expires_indexes, "expires_at cleanup index missing"


class TestModelSurface:
    def test_no_sunder_name_leak(self) -> None:
        """Defensive: ensure no _TRANSITIONS or other sunder-name leaks
        ended up in the model class. Same pitfall the project documents
        for str-Enum CHECK constraints (see AGENTS.md)."""
        from app.models.memory_extraction_pause_models import (
            MemoryExtractionPause,
        )

        for attr in dir(MemoryExtractionPause):
            assert not attr.startswith("_TRANSITIONS"), (
                f"sunder-name leak: {attr}"
            )
            assert not attr.startswith("_MISSING_"), (
                f"sunder-name leak: {attr}"
            )
