"""Tests for Epic 4.1b — standing-constraint enforcement at tool dispatch.

Exercises ``app.services.pre_tool_constraints.PreToolConstraints``:

* Pure unit tests (no DB): ``resolve_user_id`` coercion, fail-open on a
  broken session, and verdict shape.
* DB-backed integration tests: a seeded ``constraint`` claim blocks /
  escalates a matching tool call, and an unrelated tool is allowed.
  These run against the real PostgreSQL (10.0.4.10) like the other
  memory tests — they seed their own user/workspace/claim and never
  roll back, so each uses a unique id.

Run:
    docker compose exec backend pytest app/tests/test_pre_tool_constraints.py -v
"""

from __future__ import annotations

import sys
import uuid
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio

sys.path.insert(0, "/opt/flowmanner/backend")

from app.database import fresh_session
from app.models.personal_memory_models import PersonalMemoryClaim
from app.models.user import User
from app.models.workspace_models import Workspace
from app.services.personal_memory_service import PersonalMemoryService
from app.services.pre_tool_constraints import (
    ALLOW,
    BLOCK,
    ESCALATE,
    ConstraintVerdict,
    PreToolConstraints,
)


def _uid() -> int:
    return 70_000_000 + (uuid.uuid4().int % 10_000_000)


def _wsid() -> str:
    return f"ws-{uuid.uuid4().hex[:12]}"


async def _seed_user_ws(db, user_id: int, workspace_id: str) -> None:
    """Insert a user (explicit int id) then a workspace owned by it.

    The explicit id matters: the constraint claims we add afterwards
    reference ``user_id``/``workspace_id`` as FKs, so the parents must
    exist with those exact keys before the child rows are flushed.
    """
    user = User(
        email=f"pc-{user_id}@{workspace_id}.example.com",
        hashed_password="x",
        role="user",
    )
    user.id = user_id
    db.add(user)
    await db.flush()
    ws = Workspace(
        id=workspace_id,
        name=workspace_id,
        slug=workspace_id,
        owner_id=user_id,
    )
    db.add(ws)
    await db.flush()


def _mk_constraint(
    user_id: int,
    workspace_id: str,
    *,
    subject: str,
    target_tools: list[str],
    action: str,
    reason: str = "",
) -> PersonalMemoryClaim:
    return PersonalMemoryClaim(
        user_id=user_id,
        workspace_id=workspace_id,
        subject=subject,
        predicate="prohibits",
        object={"target_tools": target_tools, "action": action, "reason": reason},
        claim_type="constraint",
        scope="workspace",
        source_type="user_explicit",
        confidence=0.95,
        importance=0.9,
        sensitivity="normal",
    )


# ── Pure unit tests (no DB) ────────────────────────────────────────────────


class TestResolveUserId:
    def test_int_passthrough(self):
        assert PreToolConstraints.resolve_user_id(42) == 42

    def test_numeric_string_coerced(self):
        assert PreToolConstraints.resolve_user_id("123") == 123

    def test_uuid_string_returns_none(self):
        # Substrate Workflow.user_id is a UUID string — not coercible to the
        # int user_id the memory table uses, so we key on workspace only.
        assert PreToolConstraints.resolve_user_id(str(uuid.uuid4())) is None

    def test_none_returns_none(self):
        assert PreToolConstraints.resolve_user_id(None) is None


class TestFailOpen:
    @pytest.mark.asyncio(loop_scope="module")
    async def test_db_error_returns_allow(self):
        """A broken session must NEVER brick tool dispatch."""
        broken = AsyncMock()
        broken.execute.side_effect = RuntimeError("db down")
        svc = PreToolConstraints(broken)
        verdict = await svc.evaluate("code_executor", user_id=1, workspace_id="ws-x")
        assert verdict.decision == ALLOW
        assert not verdict.blocked
        assert not verdict.requires_approval

    @pytest.mark.asyncio(loop_scope="module")
    async def test_empty_workspace_returns_allow(self):
        svc = PreToolConstraints(AsyncMock())
        verdict = await svc.evaluate("code_executor", user_id=1, workspace_id="")
        assert verdict.decision == ALLOW


class TestVerdictShape:
    def test_block_is_blocked_not_escalate(self):
        v = ConstraintVerdict(BLOCK, "x", triggered_claim_id="c1")
        assert v.blocked
        assert not v.requires_approval

    def test_escalate_is_escalate_not_block(self):
        v = ConstraintVerdict(ESCALATE, "x", triggered_claim_id="c1")
        assert v.requires_approval
        assert not v.blocked


# ── DB-backed integration tests ─────────────────────────────────────────────


@pytest.mark.asyncio(loop_scope="module")
async def test_block_constraint_stops_matching_tool():
    user_id = _uid()
    ws = _wsid()
    async with fresh_session() as db:
        await _seed_user_ws(db, user_id, ws)
        db.add(
            _mk_constraint(
                user_id,
                ws,
                subject="never rm -rf on prod",
                target_tools=["code_executor"],
                action="block",
                reason="prod data loss",
            )
        )
        await db.commit()

    async with fresh_session() as db:
        svc = PreToolConstraints(db)
        verdict = await svc.evaluate("code_executor", user_id=user_id, workspace_id=ws)
        assert verdict.decision == BLOCK
        assert verdict.blocked
        assert verdict.constraint_subject == "never rm -rf on prod"


@pytest.mark.asyncio(loop_scope="module")
async def test_escalate_constraint_requires_approval():
    user_id = _uid()
    ws = _wsid()
    async with fresh_session() as db:
        await _seed_user_ws(db, user_id, ws)
        db.add(
            _mk_constraint(
                user_id,
                ws,
                subject="require approval before drop table",
                target_tools=["code_executor"],
                action="escalate",
            )
        )
        await db.commit()

    async with fresh_session() as db:
        svc = PreToolConstraints(db)
        verdict = await svc.evaluate("code_executor", user_id=user_id, workspace_id=ws)
        assert verdict.decision == ESCALATE
        assert verdict.requires_approval


@pytest.mark.asyncio(loop_scope="module")
async def test_unrelated_tool_allowed():
    user_id = _uid()
    ws = _wsid()
    async with fresh_session() as db:
        await _seed_user_ws(db, user_id, ws)
        db.add(
            _mk_constraint(
                user_id,
                ws,
                subject="never run rm -rf on prod",
                target_tools=["shell"],
                action="block",
            )
        )
        await db.commit()

    async with fresh_session() as db:
        svc = PreToolConstraints(db)
        verdict = await svc.evaluate("web_search", user_id=user_id, workspace_id=ws)
        assert verdict.decision == ALLOW


@pytest.mark.asyncio(loop_scope="module")
async def test_constraint_claim_type_roundtrips_through_service():
    """The new ``constraint`` claim type must pass the service's enum
    validation (4.1a) and land in the DB."""
    user_id = _uid()
    ws = _wsid()
    async with fresh_session() as db:
        await _seed_user_ws(db, user_id, ws)
        await db.commit()

    async with fresh_session() as db:
        svc = PersonalMemoryService(db)
        claim = await svc.create(
            user_id=user_id,
            workspace_id=ws,
            subject="never use deprecated API v1",
            predicate="prohibits",
            object={"target_tools": ["legacy_api"], "action": "escalate"},
            claim_type="constraint",
            scope="workspace",
            source_type="user_explicit",
        )
        assert claim.claim_type == "constraint"
        # And it must now be enforceable.
        svc2 = PreToolConstraints(db)
        verdict = await svc2.evaluate("legacy_api", user_id=user_id, workspace_id=ws)
        assert verdict.requires_approval
