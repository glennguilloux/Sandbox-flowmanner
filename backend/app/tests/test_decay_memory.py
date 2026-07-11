"""Epic 3.3 acceptance tests — the retrieval-lifecycle decay job.

Verifies the periodic ``decay_memory_entries`` task:
  * soft-archive fires for claims/entries not recalled within the TTL;
  * importance decays by recency (``imp * (1 - rate * days)``);
  * *immortal* (restricted-sensitivity) claims are NEVER archived/decayed;
  * expired *sensitive* claims are hard-deleted and ONLY those;
  * MemoryEntry gets the same soft-archive + decay (no constraint/sensitive rules).

The task SQL in the plan referenced ``scope='constraint'`` / ``scope='sensitive'``
values that do NOT exist on the merged ``PersonalMemoryClaim`` schema
(``scope ∈ {personal, workspace, program, private}``). This test pins the
REAL mapping (see decay_memory.py / config):
  - immortal  -> sensitivity == 'restricted'
  - hard-delete -> claim_type == 'sensitive' AND expires_at < now()

HERMETIC DB: this test does NOT touch the dev `flowmanner` DB (which holds
real claims). It targets the isolated `flowmanner_phase_b_smoke` database,
creating its own tables from ``Base.metadata``. Point it elsewhere with the
``FLOWMANNER_DECAY_TEST_DB`` env var if needed.

Run from the worktree's ``backend/`` dir:
    /opt/flowmanner/backend/.venv/bin/python -m pytest \\
        app/tests/test_decay_memory.py -v
"""

from __future__ import annotations

import os
import sys
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import select, text

# Make ``app`` importable from the worktree's backend dir (the copy under
# test), derived from this file's location rather than a hardcoded path so
# the test runs against the right checkout.
os.environ.setdefault("OPENAI_API_KEY", "test-decay-job")
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.models import Base
from app.models.memory_models import MemoryEntry
from app.models.personal_memory_models import PersonalMemoryClaim
from app.models.user import User
from app.models.workspace_models import Workspace
from app.tasks.decay_memory import decay_importance, run_decay_job

# Isolated target DB — never the dev DB with real claims.
# A per-test unique database name is used (see the `engine` fixture) so that
# back-to-back runs never inherit leftover schema from a prior test or from
# another test module that shares the module-scoped event loop.
TEST_DB_BASE = os.getenv(
    "FLOWMANNER_DECAY_TEST_DB_BASE",
    "postgresql+asyncpg://flowmanner:REDACTED_DB_PASSWORD" "@localhost:5432/flowmanner_phase_b_smoke",
)


@pytest.fixture
async def engine():
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    # Unique DB per test → no cross-test or cross-module schema residue.
    db_name = f"decay_{uuid.uuid4().hex[:12]}"
    test_db_url = TEST_DB_BASE.rsplit("/", 1)[0] + "/" + db_name
    admin = create_async_engine(TEST_DB_BASE.rsplit("/", 1)[0] + "/postgres", future=True)
    # CREATE/DROP DATABASE must run autocommit (not inside a transaction block).
    async with admin.connect() as conn:
        await conn.execution_options(isolation_level="AUTOCOMMIT")
        await conn.execute(text(f'CREATE DATABASE "{db_name}"'))
    await admin.dispose()

    eng = create_async_engine(test_db_url, future=True)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    Session = async_sessionmaker(bind=eng, expire_on_commit=False)
    yield eng, Session

    await eng.dispose()
    admin = create_async_engine(TEST_DB_BASE.rsplit("/", 1)[0] + "/postgres", future=True)
    async with admin.connect() as conn:
        await conn.execution_options(isolation_level="AUTOCOMMIT")
        await conn.execute(text(f'DROP DATABASE "{db_name}" WITH (FORCE)'))
    await admin.dispose()


def _uid() -> int:
    return 70_000_000 + (uuid.uuid4().int % 10_000_000)


def _wsid() -> str:
    return f"ws-decay-{uuid.uuid4().hex[:12]}"


async def _seed_users_workspace(session, user_id: int, workspace_id: str) -> None:
    user = User(email=f"decay-user-{user_id}@example.com", hashed_password="x", role="user")
    user.id = user_id
    ws = Workspace(id=workspace_id, name=workspace_id, slug=workspace_id, owner_id=user_id)
    session.add(user)
    session.add(ws)
    await session.commit()


def _make_claim(
    *,
    user_id: int,
    workspace_id: str,
    claim_type: str = "fact",
    scope: str = "personal",
    sensitivity: str = "normal",
    importance: float = 0.8,
    last_used_at: datetime | None = None,
    created_at: datetime | None = None,
    expires_at: datetime | None = None,
) -> PersonalMemoryClaim:
    claim = PersonalMemoryClaim(
        user_id=user_id,
        workspace_id=workspace_id,
        subject="s",
        predicate="p",
        object={"value": "v"},
        claim_type=claim_type,
        scope=scope,
        source_type="conversation",
        sensitivity=sensitivity,
        importance=importance,
        last_used_at=last_used_at,
        expires_at=expires_at,
    )
    if created_at is not None:
        claim.created_at = created_at
    return claim


def _make_entry(
    *,
    namespace: str = "test",
    importance: float = 0.8,
    last_used_at: datetime | None = None,
    created_at: datetime | None = None,
) -> MemoryEntry:
    entry = MemoryEntry(
        namespace=namespace,
        memory_type="episodic",
        content="decay test entry",
        importance=importance,
        last_used_at=last_used_at,
    )
    if created_at is not None:
        entry.created_at = created_at
    return entry


# ── Pure-function unit tests (no DB) ────────────────────────────────────────


class TestDecayImportancePure:
    def test_no_decay_for_zero_days(self):
        assert decay_importance(0.8, 0.0) == 0.8

    def test_linear_decay(self):
        # 0.8 * (1 - 0.01 * 10) = 0.8 * 0.9 = 0.72
        assert decay_importance(0.8, 10.0, decay_rate=0.01) == pytest.approx(0.72)

    def test_floor_at_min_importance(self):
        # factor goes negative; floored to min_importance (0.0 default)
        assert decay_importance(0.8, 1000.0, decay_rate=0.01, min_importance=0.1) == 0.1

    def test_immutable_when_factor_negative_floored_to_zero(self):
        assert decay_importance(0.5, 1000.0, decay_rate=0.01) == 0.0


# ── Integration tests against the isolated smoke DB ─────────────────────────


async def _count_claims(session, **filters):
    stmt = select(PersonalMemoryClaim)
    for k, v in filters.items():
        stmt = stmt.where(getattr(PersonalMemoryClaim, k) == v)
    return len((await session.execute(stmt)).scalars().all())


class TestDecayTaskIntegration:
    async def test_soft_archive_old_claim_and_immortal_survives(self, engine):
        eng, Session = engine
        now = datetime.now(UTC)
        old = now - timedelta(days=200)
        recent = now - timedelta(days=5)
        uid = _uid()
        ws = _wsid()

        async with Session() as db:
            await _seed_users_workspace(db, uid, ws)
            db.add(_make_claim(user_id=uid, workspace_id=ws, last_used_at=old, importance=0.9))
            db.add(_make_claim(user_id=uid, workspace_id=ws, last_used_at=recent, importance=0.9))
            # Immortal (restricted) claim, also ancient — must NOT be archived.
            immortal_claim = _make_claim(
                user_id=uid,
                workspace_id=ws,
                last_used_at=old,
                sensitivity="restricted",
                importance=0.9,
            )
            db.add(immortal_claim)
            await db.commit()
            immortal_id = immortal_claim.id

        summary = await run_decay_job(open_session=Session)

        async with Session() as db:
            archived = (
                (await db.execute(select(PersonalMemoryClaim).where(PersonalMemoryClaim.deleted_at.isnot(None))))
                .scalars()
                .all()
            )
            immortal = (
                await db.execute(select(PersonalMemoryClaim).where(PersonalMemoryClaim.id == immortal_id))
            ).scalar_one()
        assert summary["claims_soft_archived"] == 1
        assert len(archived) == 1
        # The one archived row must NOT be the immortal (restricted) claim.
        assert archived[0].id != immortal_id
        # Restricted-sensitivity claim is never archived.
        assert immortal.deleted_at is None

    async def test_importance_decay_applied(self, engine):
        eng, Session = engine
        now = datetime.now(UTC)
        used_10d_ago = now - timedelta(days=10)
        uid = _uid()
        ws = _wsid()

        async with Session() as db:
            await _seed_users_workspace(db, uid, ws)
            c = _make_claim(user_id=uid, workspace_id=ws, last_used_at=used_10d_ago, importance=1.0)
            db.add(c)
            await db.commit()
            cid = c.id

        await run_decay_job(open_session=Session)

        async with Session() as db:
            reread = (await db.execute(select(PersonalMemoryClaim).where(PersonalMemoryClaim.id == cid))).scalar_one()
        # 1.0 * (1 - 0.01 * 10) = 0.9
        assert reread.importance == pytest.approx(0.9)
        assert reread.deleted_at is None

    async def test_immortal_claim_not_decayed(self, engine):
        eng, Session = engine
        now = datetime.now(UTC)
        used_100d_ago = now - timedelta(days=100)
        uid = _uid()
        ws = _wsid()

        async with Session() as db:
            await _seed_users_workspace(db, uid, ws)
            c = _make_claim(
                user_id=uid,
                workspace_id=ws,
                last_used_at=used_100d_ago,
                sensitivity="restricted",
                importance=0.7,
            )
            db.add(c)
            await db.commit()
            cid = c.id

        await run_decay_job(open_session=Session)

        async with Session() as db:
            reread = (await db.execute(select(PersonalMemoryClaim).where(PersonalMemoryClaim.id == cid))).scalar_one()
        # Immortal: importance untouched AND not archived.
        assert reread.importance == pytest.approx(0.7)
        assert reread.deleted_at is None

    async def test_hard_delete_expired_sensitive_only(self, engine):
        eng, Session = engine
        now = datetime.now(UTC)
        expired = now - timedelta(days=5)
        uid = _uid()
        ws = _wsid()

        async with Session() as db:
            await _seed_users_workspace(db, uid, ws)
            # Expired sensitive -> deleted.
            db.add(
                _make_claim(
                    user_id=uid,
                    workspace_id=ws,
                    claim_type="sensitive",
                    expires_at=expired,
                    importance=0.5,
                )
            )
            # Not-yet-expired sensitive -> kept.
            db.add(
                _make_claim(
                    user_id=uid,
                    workspace_id=ws,
                    claim_type="sensitive",
                    expires_at=now + timedelta(days=5),
                    importance=0.5,
                )
            )
            # Expired but normal claim_type -> kept (only 'sensitive' is deleted).
            db.add(
                _make_claim(
                    user_id=uid,
                    workspace_id=ws,
                    claim_type="fact",
                    expires_at=expired,
                    importance=0.5,
                )
            )
            await db.commit()

        summary = await run_decay_job(open_session=Session)

        async with Session() as db:
            remaining = (await db.execute(select(PersonalMemoryClaim))).scalars().all()
            types = {r.claim_type for r in remaining}
        assert summary["claims_hard_deleted_expired_sensitive"] == 1
        # The expired sensitive is gone; the other two survive.
        assert types == {"sensitive", "fact"}
        assert len(remaining) == 2

    async def test_memory_entry_soft_archive_and_decay(self, engine):
        eng, Session = engine
        now = datetime.now(UTC)
        old = now - timedelta(days=200)
        used_10d = now - timedelta(days=10)
        uid = _uid()
        ws = _wsid()

        async with Session() as db:
            await _seed_users_workspace(db, uid, ws)
            old_entry = _make_entry(last_used_at=old, importance=0.8)
            old_entry.user_id = uid
            old_entry.workspace_id = ws
            recent_entry = _make_entry(last_used_at=used_10d, importance=1.0)
            recent_entry.user_id = uid
            recent_entry.workspace_id = ws
            db.add(old_entry)
            db.add(recent_entry)
            await db.commit()
            recent_id = recent_entry.id

        summary = await run_decay_job(open_session=Session)

        async with Session() as db:
            archived = (await db.execute(select(MemoryEntry).where(MemoryEntry.deleted_at.isnot(None)))).scalars().all()
            recent = (await db.execute(select(MemoryEntry).where(MemoryEntry.id == recent_id))).scalar_one()
        assert summary["entries_soft_archived"] == 1
        assert len(archived) == 1
        # Recent entry decayed: 1.0 * (1 - 0.01 * 10) = 0.9, not archived.
        assert recent.deleted_at is None
        assert recent.importance == pytest.approx(0.9)
