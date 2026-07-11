"""Integration test — v3 workspace admin routes emit a tenant-scoped audit trail.

Verifies task t_67464ab3: ``create_workspace`` / ``update_workspace`` /
``delete_workspace`` (app/api/v3/workspaces.py) must each emit one
``audit_logs`` row carrying the ``workspace_id`` in ``action_details``.

The audit emission is fire-and-forget (``background_task_manager.spawn``), so
we flush it with ``background_task_manager.drain(timeout=5.0)`` before asserting
— the same pattern used by test_scope_isolation.py.

This is a real-DB integration test against the live PostgreSQL. It seeds a
dedicated user + workspace (unique ids every run) and enables the
``WORKSPACES_V3_ENDPOINTS`` flag, then calls the route coroutines directly
(they only read ``user.id`` and ``db``), commits, drains, and reads the audit
row back from a fresh session.

Run:
    /opt/flowmanner/backend/.venv/bin/python -m pytest app/tests/test_ws_audit.py -v
"""

from __future__ import annotations

import json

# Make ``app`` importable. Resolve the backend root relative to this file so the
# test exercises the worktree/branch it lives in (not a sibling checkout).
import sys
import uuid
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from sqlalchemy import select, text

from app.api.v3 import workspaces as ws_routes
from app.database import fresh_session
from app.models.legacy_models import AuditLog
from app.models.phase4_models import FeatureFlag
from app.models.user import User
from app.models.workspace_models import Workspace, WorkspaceMember
from app.schemas.workspace_v3 import (
    WorkspaceCreateRequest,
    WorkspaceUpdateRequest,
)
from app.services.background_task_manager import background_task_manager

V3_FLAG = "WORKSPACES_V3_ENDPOINTS"


def _uid() -> int:
    """A fresh, globally-unique int user id (avoids PK collisions across re-runs)."""
    return 910_000_000 + (uuid.uuid4().int % 80_000_000)


def _wsid() -> str:
    # Full 32-char hex — high entropy so re-runs never collide.
    return f"ws-{uuid.uuid4().hex}"


async def _ensure_v3_flag(db) -> None:
    flag = (await db.execute(select(FeatureFlag).where(FeatureFlag.key == V3_FLAG))).scalar_one_or_none()
    if flag is None:
        flag = FeatureFlag(
            key=V3_FLAG,
            name="Workspaces v3 endpoints",
            enabled_globally=True,
        )
        db.add(flag)
    else:
        flag.enabled_globally = True
    await db.commit()


async def _seed_user_and_workspace(db, user_id: int, workspace_id: str) -> User:
    user = User(
        email=f"wsaudit-{user_id}@example.com",
        hashed_password="x",
        role="user",
    )
    user.id = user_id
    db.add(user)
    ws = Workspace(
        id=workspace_id,
        name=f"wsaudit-{workspace_id}",
        slug=f"wsaudit-{workspace_id}-{uuid.uuid4().hex[:6]}",
        owner_id=user_id,
    )
    db.add(ws)
    db.add(WorkspaceMember(workspace_id=workspace_id, user_id=user_id, role="owner"))
    await db.commit()
    return user


async def _last_audit_row(action: str, user_id: int, workspace_id: str):
    async with fresh_session() as db:
        rows = (
            (
                await db.execute(
                    select(AuditLog)
                    .where(AuditLog.action == action)
                    .where(AuditLog.user_id == user_id)
                    .order_by(AuditLog.timestamp.desc())
                )
            )
            .scalars()
            .all()
        )
    for row in rows:
        details = json.loads(row.action_details or "{}")
        if details.get("workspace_id") == workspace_id:
            return row, details
    return None, None


@pytest.mark.asyncio(loop_scope="module")
async def test_create_workspace_emits_audit():
    """create_workspace must write an audit_logs row with workspace.create + workspace_id."""
    uid = _uid()
    async with fresh_session() as db:
        await _ensure_v3_flag(db)
        # create_workspace mints its own workspace id, so we only need a user.
        user = User(
            email=f"wsaudit-{uid}@example.com",
            hashed_password="x",
            role="user",
        )
        user.id = uid
        db.add(user)
        await db.commit()

        resp = await ws_routes.create_workspace(
            payload=WorkspaceCreateRequest(name="audit-create", slug=f"audit-create-{uuid.uuid4().hex[:6]}"),
            user=user,
            db=db,
        )
        await db.commit()
        created_ws_id = resp["data"]["id"]

    await background_task_manager.drain(timeout=5.0)

    row, details = await _last_audit_row("workspace.create", uid, created_ws_id)
    assert row is not None, "no audit_logs row written for workspace.create"
    assert details is not None
    assert details["workspace_id"] == created_ws_id
    assert details["name"] == "audit-create"


@pytest.mark.asyncio(loop_scope="module")
async def test_update_workspace_emits_audit():
    """update_workspace must write an audit_logs row with workspace.update + workspace_id."""
    uid = _uid()
    ws_id = _wsid()
    async with fresh_session() as db:
        await _ensure_v3_flag(db)
        user = await _seed_user_and_workspace(db, uid, ws_id)

        await ws_routes.update_workspace(
            workspace_id=ws_id,
            payload=WorkspaceUpdateRequest(name="audit-updated"),
            user=user,
            db=db,
        )
        await db.commit()

    await background_task_manager.drain(timeout=5.0)

    row, details = await _last_audit_row("workspace.update", uid, ws_id)
    assert row is not None, "no audit_logs row written for workspace.update"
    assert details is not None
    assert details["workspace_id"] == ws_id
    assert details["name"] == "audit-updated"


@pytest.mark.asyncio(loop_scope="module")
async def test_delete_workspace_emits_audit():
    """delete_workspace must write an audit_logs row with workspace.delete + workspace_id,
    recording the workspace that was removed (emitted before the F1 purge)."""
    uid = _uid()
    ws_id = _wsid()
    async with fresh_session() as db:
        await _ensure_v3_flag(db)
        user = await _seed_user_and_workspace(db, uid, ws_id)

        await ws_routes.delete_workspace(
            workspace_id=ws_id,
            user=user,
            db=db,
        )
        await db.commit()

    await background_task_manager.drain(timeout=5.0)

    row, details = await _last_audit_row("workspace.delete", uid, ws_id)
    assert row is not None, "no audit_logs row written for workspace.delete"
    assert details is not None
    assert details["workspace_id"] == ws_id
    assert details["name"] == f"wsaudit-{ws_id}"
