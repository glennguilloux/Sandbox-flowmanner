"""Unit tests for scripts/seed_marketplace.py.

Verifies the idempotent reconcile contract without a live Postgres. The
script reads two real sources at runtime:
  - built-in MissionTemplate rows (mocked via AsyncSessionLocal),
  - the in-repo ``app/agent_definitions/**/*.md`` persona files (real FS).
So the persona count is derived from the actual tree (215 at time of
writing). These tests assert the reconcile logic against that reality.
"""

from __future__ import annotations

import asyncio
import contextlib
from pathlib import Path
from types import SimpleNamespace

import pytest

import app.database as app_db
import scripts.seed_marketplace as sm

PERSONA_COUNT = len(list(Path("app/agent_definitions").rglob("*.md")))


def test_parse_frontmatter_basic():
    text = "---\nname: Foo Bar\ncolor: blue\ndescription: does things\n---\n# Body\ntext"
    meta, body = sm._parse_frontmatter(text)
    assert meta["name"] == "Foo Bar"
    assert meta["color"] == "blue"
    assert body.startswith("# Body")


def test_parse_frontmatter_no_fm():
    meta, body = sm._parse_frontmatter("just text, no frontmatter")
    assert meta == {}
    assert body == "just text, no frontmatter"


def test_item_id_scheme_deterministic():
    assert sm._item_id_template("My Template") == "seed:template:My Template"
    assert sm._item_id_persona("support", "bob") == "seed:persona:support/bob"
    assert sm._item_id_template("My Template") == sm._item_id_template("My Template")


class _Row:
    def __init__(self, **kw):
        self._d = dict(kw)
        for k, v in kw.items():
            setattr(self, k, v)

    def __repr__(self):
        return f"_Row({self._d})"


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return list(self._rows)

    def first(self):
        return self._rows[0] if self._rows else None

    def fetchone(self):
        return None


class _FakeSession:
    """Minimal async session double recording add/delete/commit."""

    def __init__(self, templates=None, existing_seed=None):
        self._templates = templates or []
        self._seed = list(existing_seed or [])
        self.added = []
        self.deleted = []
        self.committed = 0

    async def execute(self, stmt):
        sql = str(stmt.compile(compile_kwargs={"literal_binds": True})).lower()
        if "mission_templates" in sql:
            return _FakeResult(self._templates)
        if "like" in sql and "seed:%" in sql:
            return _FakeResult(self._seed)
        if "marketplace_listings" in sql:
            for r in self._seed:
                if getattr(r, "artifact_id", None) and f"'{r.artifact_id.lower()}'" in sql:
                    return _FakeResult([r])
            return _FakeResult([])
        return _FakeResult([])

    async def scalar(self, stmt=None):
        sql = str(stmt.compile(compile_kwargs={"literal_binds": True})).lower() if stmt is not None else ""
        if "like" in sql and "seed:%" in sql:
            return _FakeResult(self._seed)
        if "marketplace_listings" in sql:
            for r in self._seed:
                if getattr(r, "artifact_id", None) and f"'{r.artifact_id.lower()}'" in sql:
                    return r
            return None
        return None

    def add(self, obj):
        self.added.append(obj)

    async def delete(self, obj):
        self.deleted.append(obj)

    async def commit(self):
        self.committed += 1


def _patch_session(monkeypatch, sess):
    @contextlib.asynccontextmanager
    async def cm():
        yield sess

    monkeypatch.setattr(app_db, "AsyncSessionLocal", cm)


def test_seed_inserts_all_builtins_and_personas(monkeypatch):
    tpl = SimpleNamespace(id="t1", name="Starter Mission", description="d", category="general")
    sess = _FakeSession(templates=[tpl])
    _patch_session(monkeypatch, sess)

    result = asyncio.run(sm.seed_marketplace())
    # 1 built-in template + every in-repo persona markdown file.
    assert result["inserted"] == 1 + PERSONA_COUNT
    assert result["updated"] == 0
    assert result["deleted"] == 0
    assert result["templates"] == 1
    assert sess.committed == 1


def test_seed_reconciles_existing_and_removes_gone(monkeypatch):
    tpl = SimpleNamespace(id="t1", name="Starter Mission", description="d", category="general")
    # A seed row whose source no longer exists in the real tree (ghost).
    old_seed = [
        _Row(artifact_id="seed:template:Starter Mission", name="OLD", description="x", category_id="general", status="published", is_published=True),
        _Row(artifact_id="seed:persona:zzz_ghost/nonexistent", name="Gone", description="x", category_id="general", status="published", is_published=True),
    ]
    sess = _FakeSession(templates=[tpl], existing_seed=old_seed)
    _patch_session(monkeypatch, sess)

    result = asyncio.run(sm.seed_marketplace())
    # Template row already existed -> updated (not inserted).
    assert result["inserted"] == PERSONA_COUNT
    assert result["updated"] == 1
    # The ghost persona source is gone -> deleted.
    assert result["deleted"] == 1
    deleted_ids = {r.artifact_id for r in sess.deleted}
    assert "seed:persona:zzz_ghost/nonexistent" in deleted_ids
    assert sess.committed == 1
