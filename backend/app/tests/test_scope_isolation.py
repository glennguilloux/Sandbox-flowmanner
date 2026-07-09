"""Scope-isolation tests for personal memory claims (Epic 3.7).

Verifies the (user_id, workspace_id) multi-tenant isolation contract that
``PersonalMemoryService`` guarantees:

1. A claim written in workspace A is invisible to a ``recall`` executed
   against workspace B (cross-workspace isolation).
2. A claim written by user X in workspace A is invisible to a ``recall``
   executed for user Y in the *same* workspace A (cross-user isolation
   within a workspace).
3. ``create()`` rejects a ``None`` workspace_id (the NOT NULL guardrail on
   ``PersonalMemoryClaim.workspace_id`` — enforced by the DB at flush).
4. NEGATIVE CASE / KNOWN GAP: ``MemoryEntry.workspace_id`` is nullable.
   This test DOCUMENTS the gap as an assertion (out of governance scope for
   this epic) and must NOT migrate or fix it.

These are real-DB integration tests against the live PostgreSQL (same
harness as ``test_personal_memory_service.py``). Recall is pure SQL
substring match — no Qdrant/vector integration involved.

Run:
    docker compose exec backend pytest app/tests/test_scope_isolation.py -v
"""

from __future__ import annotations

import sys
import uuid

import pytest
import sqlalchemy.exc as sa

# Make ``app`` importable when tests run outside the backend container.
sys.path.insert(0, "/opt/flowmanner/backend")

from app.models.memory_models import MemoryEntry
from app.services.background_task_manager import BackgroundTaskManager
from app.services.personal_memory_service import (
    PersonalMemoryService,
    _MemoryCorrectionAudit,
)


def _uid() -> int:
    """A fresh, globally-unique int user id (avoids PK collisions across
    re-runs and across tests, since we never roll back the seeded rows).
    """
    return 900_000_000 + (uuid.uuid4().int % 90_000_000)


def _wsid() -> str:
    # Full 32-char hex — high entropy so re-runs against a persistent test
    # DB never collide with previously seeded rows.
    return f"ws-{uuid.uuid4().hex}"


def _make_service(db):
    """Build a service whose audit writes go to a DEDICATED manager so the
    fire-and-forget tasks are scoped to this test's event loop.
    """
    manager = BackgroundTaskManager()
    audit = _MemoryCorrectionAudit(manager=manager)
    return PersonalMemoryService(db, audit=audit), manager


def _make_user(db, user_id: int):
    from app.models.user import User

    user = User(
        email=f"scope-user-{user_id}@example.com",
        hashed_password="x",
        role="user",
    )
    user.id = user_id
    db.add(user)
    return user


def _make_workspace(db, workspace_id: str, owner_id: int):
    from app.models.workspace_models import Workspace

    # Unique slug (mirrors real rows) to avoid ix_workspaces_slug collisions
    # across re-runs.
    ws = Workspace(
        id=workspace_id,
        name=f"ws-{workspace_id}",
        slug=f"ws-{workspace_id}-{uuid.uuid4().hex[:6]}",
        owner_id=owner_id,
    )
    db.add(ws)
    return ws


def _seed(db, user_id: int, workspace_id: str) -> None:
    _make_user(db, user_id)
    _make_workspace(db, workspace_id, user_id)


async def _create_claim(svc, user_id, workspace_id, subject, predicate="is"):
    return await svc.create(
        user_id=user_id,
        workspace_id=workspace_id,
        subject=subject,
        predicate=predicate,
        object={"value": subject},
        claim_type="fact",
        scope="personal",
        source_type="conversation",
    )


@pytest.mark.asyncio(loop_scope="module")
async def test_cross_workspace_isolation():
    """A claim in workspace A must be invisible to recall in workspace B."""
    from app.database import fresh_session

    uid = _uid()
    ws_a = _wsid()
    ws_b = _wsid()
    async with fresh_session() as db:
        # One user shared across two distinct workspaces — the isolation
        # axis here is the workspace, not the user.
        _make_user(db, uid)
        _make_workspace(db, ws_a, uid)
        _make_workspace(db, ws_b, uid)
        await db.commit()

        svc, manager = _make_service(db)
        # Write a claim in workspace A.
        await _create_claim(svc, uid, ws_a, "secret-project-alpha")
        await db.commit()

        # Recall in workspace B must return NOTHING.
        items_b, _ = await svc.recall(user_id=uid, workspace_id=ws_b, query="secret-project-alpha")
        await db.commit()
        assert items_b == [], "cross-workspace leak: workspace B saw a claim written in workspace A"

        # Sanity: the same recall in workspace A DOES see it (proves the
        # data was actually written and recall works).
        items_a, _ = await svc.recall(user_id=uid, workspace_id=ws_a, query="secret-project-alpha")
        await db.commit()
        assert len(items_a) == 1
        assert items_a[0].workspace_id == ws_a

    await manager.drain(timeout=5.0)


@pytest.mark.asyncio(loop_scope="module")
async def test_cross_user_isolation_same_workspace():
    """A claim by user X in workspace A is invisible to user Y in A."""
    from app.database import fresh_session

    uid_x = _uid()
    uid_y = _uid()
    ws_a = _wsid()
    async with fresh_session() as db:
        # One SHARED workspace (ws_a) for both users — the isolation axis
        # here is the user, not the workspace.
        _make_workspace(db, ws_a, uid_x)
        _make_user(db, uid_x)
        _make_user(db, uid_y)
        await db.commit()

        svc, manager = _make_service(db)
        # User X writes a claim in workspace A.
        await _create_claim(svc, uid_x, ws_a, "user-x-private-note")
        await db.commit()

        # User Y in the SAME workspace A must see nothing.
        items_y, _ = await svc.recall(user_id=uid_y, workspace_id=ws_a, query="user-x-private-note")
        await db.commit()
        assert items_y == [], "cross-user leak: user Y saw a claim written by user X in the same workspace"

        # Sanity: user X still sees their own claim.
        items_x, _ = await svc.recall(user_id=uid_x, workspace_id=ws_a, query="user-x-private-note")
        await db.commit()
        assert len(items_x) == 1
        assert items_x[0].user_id == uid_x

    await manager.drain(timeout=5.0)


@pytest.mark.asyncio(loop_scope="module")
async def test_create_enforces_not_null_workspace_id():
    """create() must reject a None workspace_id (NOT NULL guardrail).

    The model column is NOT NULL, so the DB raises an IntegrityError at
    flush(). This is the guardrail that makes the isolation contract
    enforceable — a claim can never be written without a workspace scope.
    """
    from app.database import fresh_session

    uid = _uid()
    ws_a = _wsid()
    async with fresh_session() as db:
        _seed(db, uid, ws_a)
        await db.commit()

        svc, manager = _make_service(db)
        with pytest.raises(sa.IntegrityError):
            await svc.create(
                user_id=uid,
                workspace_id=None,  # type: ignore[arg-type]
                subject="no-workspace",
                predicate="is",
                object={"value": "x"},
                claim_type="fact",
                scope="personal",
                source_type="conversation",
            )
        # The failed write must not have persisted a workspace-less claim.
        await db.rollback()

        # Confirm a properly-scoped claim still writes fine afterwards.
        claim = await _create_claim(svc, uid, ws_a, "properly-scoped")
        await db.commit()
        assert claim.workspace_id == ws_a

    await manager.drain(timeout=5.0)


def test_memory_entry_workspace_id_is_nullable_known_gap():
    """NEGATIVE CASE — documents a known governance gap, does NOT fix it.

    ``MemoryEntry.workspace_id`` is nullable (unlike
    ``PersonalMemoryClaim.workspace_id`` which is NOT NULL). This means
    legacy ``memory_entries`` rows may lack a workspace scope and are NOT
    covered by the (user_id, workspace_id) isolation guarantee.

    This is explicitly out of scope for Epic 3.7 (per the task spec:
    "KNOWN GAP, do NOT fix"). We assert the current (unwanted) state so the
    gap is visible and any future tightening of the model is caught here.
    """
    column = MemoryEntry.__table__.c.workspace_id
    assert column.nullable is True, (
        "KNOWN GAP CHANGED: MemoryEntry.workspace_id is no longer nullable. "
        "If this was an intentional migration, update this test and the "
        "Epic 3.7 spec — otherwise the gap was closed unexpectedly."
    )
