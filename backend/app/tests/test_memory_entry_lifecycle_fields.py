"""Epic 3.2 acceptance tests — last_used_at on MemoryEntry.

Proves the decay/usage-tracking column added in Epic 3.2 is wired onto the
``MemoryEntry`` model correctly and that the Alembic migration chains on the
current head. No live DB required — all assertions operate on SQLAlchemy
metadata / instance construction (mirrors test_community_models.py style).

Run from YOUR worktree's ``backend/`` dir (so ``import app`` resolves to the
worktree copy under test):

    /opt/flowmanner/backend/.venv/bin/python -m pytest \\
        app/tests/test_memory_entry_lifecycle_fields.py -v
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import DateTime

from alembic.config import Config
from alembic.script import ScriptDirectory
from app.models.memory_models import MemoryEntry


class TestMemoryEntryLastUsedColumn:
    """The last_used_at column must exist, be nullable TIMESTAMPTZ, default NULL."""

    def test_last_used_at_column_exists(self):
        cols = set(MemoryEntry.__table__.columns.keys())
        assert "last_used_at" in cols, "MemoryEntry missing last_used_at column"

    def test_last_used_at_is_nullable_timestamptz(self):
        col = MemoryEntry.__table__.columns["last_used_at"]
        assert col.nullable is True, "last_used_at must be nullable (existing rows have no usage yet)"
        assert isinstance(col.type, DateTime), "last_used_at must be DateTime"
        assert col.type.timezone is True, "last_used_at must be timezone-aware (TIMESTAMPTZ)"

    def test_last_used_at_positioned_after_importance(self):
        names = list(MemoryEntry.__table__.columns.keys())
        assert (
            names.index("importance") < names.index("last_used_at") < names.index("supersedes_id")
        ), "last_used_at must sit between importance and supersedes_id"

    def test_last_used_at_defaults_null(self):
        entry = MemoryEntry(
            content="epic 3.2 lifecycle probe",
            namespace="test",
            memory_type="episodic",
        )
        assert entry.last_used_at is None, "last_used_at should default to NULL"

    def test_last_used_at_can_be_set(self):
        now = datetime.now(timezone.utc)
        entry = MemoryEntry(
            content="epic 3.2 lifecycle probe",
            namespace="test",
            memory_type="episodic",
            last_used_at=now,
        )
        assert entry.last_used_at == now
        assert entry.last_used_at.tzinfo is not None, "stored value must stay timezone-aware"


class TestMigrationChainsOnHead:
    """The migration must chain directly on the GOV-1.6 drop-event head."""

    def test_down_revision_is_gov16_head(self):
        cfg = Config("alembic.ini")
        script = ScriptDirectory.from_config(cfg)

        new_rev = script.get_revision("20260709_e32_memory_entry_last_used")
        assert new_rev is not None, "new migration revision not registered"
        # The new migration must chain directly on the GOV-1.6 drop-event rev.
        assert (
            new_rev.down_revision == "20260709_gov16_drop_event_type"
        ), f"down_revision should be gov16 head, got {new_rev.down_revision}"
        # gov16 (the former head) must no longer be a head now that this
        # migration sits on top of it.
        heads = script.get_heads()
        assert "20260709_gov16_drop_event_type" not in heads, "gov16 should be superseded as a head"

    def test_single_head_after_adding_migration(self):
        cfg = Config("alembic.ini")
        script = ScriptDirectory.from_config(cfg)
        # After this migration lands, exactly one head must exist (no branch).
        assert len(script.get_heads()) == 1, f"multiple heads: {script.get_heads()}"
