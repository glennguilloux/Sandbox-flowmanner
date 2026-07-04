"""Phase 4: Tenant isolation tests.

Verifies that workspace-scoped queries correctly isolate data between workspaces.
Tests the get_workspace_id dependency and workspace filtering in service layers.

Run inside container:
    docker compose cp backend/tests/test_tenant_isolation.py backend:/app/test_tenant_isolation.py
    docker compose exec backend python /app/test_tenant_isolation.py
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytestmark = pytest.mark.integration

# ── Helpers ──────────────────────────────────────────────────────────────────

_passed = 0
_failed = 0
_errors: list[str] = []


def _assert(condition: bool, msg: str) -> None:
    global _passed, _failed
    if condition:
        _passed += 1
        print(f"  ✅ {msg}")
    else:
        _failed += 1
        _errors.append(msg)
        print(f"  ❌ {msg}")


# ── Mock objects ─────────────────────────────────────────────────────────────


class FakeRow:
    """Simulates a SQLAlchemy Row result."""

    def __init__(self, *args, **kwargs):
        self._values = list(args)
        for k, v in kwargs.items():
            setattr(self, k, v)
            self._values.append(v)

    def __getitem__(self, index):
        return self._values[index]


class FakeScalars:
    def __init__(self, items):
        self._items = items

    def all(self):
        return self._items

    def first(self):
        return self._items[0] if self._items else None

    def one_or_none(self):
        if len(self._items) == 1:
            return self._items[0]
        if len(self._items) == 0:
            return None
        raise ValueError("Multiple results")


class FakeResult:
    def __init__(self, items=None, scalar_val=None, row=None):
        self._items = items or []
        self._scalar_val = scalar_val
        self._row = row

    def scalars(self):
        return FakeScalars(self._items)

    def scalar_one_or_none(self):
        if self._items:
            return self._items[0]
        return self._scalar_val

    def scalar(self):
        return self._scalar_val

    def first(self):
        return self._row

    def all(self):
        return [(i,) for i in self._items]

    def __iter__(self):
        return iter(self.all())


class FakeMission:
    def __init__(self, id=None, user_id=1, workspace_id=None, title="Test", status="pending"):
        self.id = id or str(uuid.uuid4())
        self.user_id = user_id
        self.workspace_id = workspace_id
        self.title = title
        self.status = status
        self.deleted_at = None
        self.created_at = datetime.now(UTC)
        self.started_at = None
        self.completed_at = None
        self.updated_at = None
        self.description = ""
        self.mission_type = None
        self.priority = None
        self.plan = None
        self.results = None
        self.error_message = None
        self.tokens_used = 0
        self.estimated_cost = 0.0
        self.actual_cost = 0.0


class FakeWorkspaceMember:
    def __init__(self, workspace_id, user_id, role="member"):
        self.workspace_id = workspace_id
        self.user_id = user_id
        self.role = role
        self.is_active = True


# ── Test: get_workspace_id dependency ────────────────────────────────────────


async def test_get_workspace_id_from_header():
    """get_workspace_id should resolve from X-Workspace-Id header."""
    from app.api.deps import get_workspace_id

    ws_id = "ws-aaa-111"
    user = MagicMock(id=1)
    request = MagicMock()
    request.headers = {"X-Workspace-Id": ws_id}
    request.query_params = {}

    member = FakeWorkspaceMember(ws_id, user.id)

    db = AsyncMock()
    db.execute = AsyncMock(return_value=FakeResult(items=[member]))

    result = await get_workspace_id(request, user, db)
    _assert(result == ws_id, "get_workspace_id resolves from X-Workspace-Id header")


async def test_get_workspace_id_from_query():
    """get_workspace_id should resolve from workspace_id query param."""
    from app.api.deps import get_workspace_id

    ws_id = "ws-bbb-222"
    user = MagicMock(id=1)
    request = MagicMock()
    request.headers = {}
    request.query_params = {"workspace_id": ws_id}

    member = FakeWorkspaceMember(ws_id, user.id)

    db = AsyncMock()
    db.execute = AsyncMock(return_value=FakeResult(items=[member]))

    result = await get_workspace_id(request, user, db)
    _assert(result == ws_id, "get_workspace_id resolves from workspace_id query param")


async def test_get_workspace_id_fallback_to_primary():
    """get_workspace_id should fall back to user's primary workspace when no explicit workspace."""
    from app.api.deps import get_workspace_id

    user = MagicMock(id=1)
    request = MagicMock()
    request.headers = {}
    request.query_params = {}

    db = AsyncMock()

    # Single call: auto-detect primary workspace
    async def mock_execute(stmt):
        return FakeResult(row=FakeRow(workspace_id="ws-primary-000"))

    db.execute = mock_execute

    result = await get_workspace_id(request, user, db)
    _assert(result == "ws-primary-000", "get_workspace_id falls back to primary workspace")


async def test_get_workspace_id_no_workspaces():
    """get_workspace_id should return None when user has no workspaces."""
    from app.api.deps import get_workspace_id

    user = MagicMock(id=1)
    request = MagicMock()
    request.headers = {}
    request.query_params = {}

    db = AsyncMock()
    db.execute = AsyncMock(return_value=FakeResult(items=[], row=None))

    result = await get_workspace_id(request, user, db)
    _assert(result is None, "get_workspace_id returns None when user has no workspaces")


# ── Test: Mission service workspace filtering ────────────────────────────────


async def test_list_missions_workspace_filter():
    """list_missions should filter by workspace_id when provided."""
    from app.services.mission_service import list_missions

    ws_id = "ws-test-001"
    m1 = FakeMission(workspace_id=ws_id)
    m2 = FakeMission(workspace_id=ws_id)

    call_args = []

    db = AsyncMock()
    original_execute = AsyncMock()

    async def mock_execute(stmt):
        call_args.append(str(stmt))
        # Return count of 2 for count query, then items
        if len(call_args) <= 1:
            return FakeResult(scalar_val=2)
        return FakeResult(items=[m1, m2])

    db.execute = mock_execute

    items, total = await list_missions(db, user_id=1, workspace_id=ws_id)
    _assert(total == 2, "list_missions with workspace_id returns correct count")
    _assert(len(items) == 2, "list_missions with workspace_id returns correct items")


async def test_list_missions_fallback_to_user():
    """list_missions should fall back to user_id filter when no workspace_id."""
    from app.services.mission_service import list_missions

    m1 = FakeMission(user_id=42)

    call_args = []

    db = AsyncMock()

    async def mock_execute(stmt):
        call_args.append(str(stmt))
        if len(call_args) <= 1:
            return FakeResult(scalar_val=1)
        return FakeResult(items=[m1])

    db.execute = mock_execute

    items, total = await list_missions(db, user_id=42, workspace_id=None)
    _assert(total == 1, "list_missions without workspace_id falls back to user_id")


async def test_create_mission_sets_workspace_id():
    """create_mission should set workspace_id on the Mission object."""
    from app.services.mission_service import create_mission

    ws_id = "ws-create-test"
    added_objects = []

    db = AsyncMock()
    db.add = lambda obj: added_objects.append(obj)
    db.flush = AsyncMock()
    db.refresh = AsyncMock()

    mission = await create_mission(db, title="Test", user_id=1, workspace_id=ws_id)

    _assert(len(added_objects) == 1, "create_mission adds one object")
    _assert(added_objects[0].workspace_id == ws_id, "create_mission sets workspace_id")


async def test_create_mission_default_no_workspace():
    """create_mission should default workspace_id to None."""
    from app.services.mission_service import create_mission

    added_objects = []

    db = AsyncMock()
    db.add = lambda obj: added_objects.append(obj)
    db.flush = AsyncMock()
    db.refresh = AsyncMock()

    mission = await create_mission(db, title="Test", user_id=1)

    _assert(
        added_objects[0].workspace_id is None,
        "create_mission defaults workspace_id to None",
    )


# ── Test: Chat service workspace filtering ───────────────────────────────────


async def test_create_chat_thread_sets_workspace_id():
    """create_chat_thread should set workspace_id."""
    from app.services.chat_service import create_chat_thread

    ws_id = "ws-chat-test"
    added_objects = []

    db = AsyncMock()
    db.add = lambda obj: added_objects.append(obj)
    db.flush = AsyncMock()
    db.refresh = AsyncMock()

    result = await create_chat_thread(db, 1, "user", "title", workspace_id=ws_id)

    _assert(added_objects[0].workspace_id == ws_id, "create_chat_thread sets workspace_id")


async def test_list_chat_threads_workspace_filter():
    """list_chat_threads should filter by workspace_id when provided."""
    from app.services.chat_service import list_chat_threads

    ws_id = "ws-chat-list"

    call_args = []

    db = AsyncMock()

    async def mock_execute(stmt):
        call_args.append(str(stmt))
        if len(call_args) <= 1:
            return FakeResult(scalar_val=5)
        return FakeResult(items=[MagicMock() for _ in range(5)])

    db.execute = mock_execute

    items, total = await list_chat_threads(db, 1, workspace_id=ws_id)
    _assert(total == 5, "list_chat_threads with workspace_id returns correct count")


async def test_list_chat_threads_fallback_to_user():
    """list_chat_threads should fall back to user_id when no workspace_id."""
    from app.services.chat_service import list_chat_threads

    call_args = []

    db = AsyncMock()

    async def mock_execute(stmt):
        call_args.append(str(stmt))
        if len(call_args) <= 1:
            return FakeResult(scalar_val=2)
        return FakeResult(items=[MagicMock(), MagicMock()])

    db.execute = mock_execute

    items, total = await list_chat_threads(db, 42, workspace_id=None)
    _assert(total == 2, "list_chat_threads without workspace_id falls back to user_id")


# ── Test: CQRS workspace_id propagation ──────────────────────────────────────


async def test_cqrs_create_mission_passes_workspace_id():
    """MissionCommandHandlers.create_mission should pass workspace_id to service."""
    from app.api._mission_cqrs.commands import MissionCommandHandlers

    ws_id = "ws-cqrs-test"
    added_objects = []

    session = AsyncMock()
    session.add = lambda obj: added_objects.append(obj)
    session.flush = AsyncMock()
    session.refresh = AsyncMock()
    session.commit = AsyncMock()

    # Configure execute to return a proper result mock so resolve_user_tier
    # can iterate its chain (.first(), .scalar_one_or_none(), etc.) without
    # hitting AsyncMock coroutine issues.
    _result = MagicMock()
    _result.first.return_value = None
    _result.scalar_one_or_none.return_value = None
    _result.scalars.return_value.all.return_value = []
    _result.scalar.return_value = 0
    session.execute = AsyncMock(return_value=_result)

    handler = MissionCommandHandlers(session)
    user = MagicMock(id=1)

    payload = MagicMock()
    payload.title = "CQRS Test"
    payload.description = ""
    payload.mission_type = None
    payload.priority = None

    result = await handler.create_mission(user, payload, workspace_id=ws_id)

    mission_obj = added_objects[0]
    _assert(
        mission_obj.workspace_id == ws_id,
        "CQRS create_mission propagates workspace_id to Mission object",
    )


async def test_cqrs_list_missions_passes_workspace_id():
    """MissionQueryHandlers.list_missions should pass workspace_id to service."""
    from app.api._mission_cqrs.queries import MissionQueryHandlers

    ws_id = "ws-cqrs-list"

    session = AsyncMock()

    async def mock_execute(stmt):
        # Return 0 for cache miss and count
        return FakeResult(scalar_val=0, items=[])

    session.execute = mock_execute

    handler = MissionQueryHandlers(session)
    result = await handler.list_missions(1, 1, 20, workspace_id=ws_id)
    _assert(result.total == 0, "CQRS list_missions with workspace_id executes without error")


# ── Test: Chat access workspace isolation ───────────────────────────────────


class FakeChatThread:
    """Simulates a ChatThread ORM object."""

    def __init__(self, id=None, user_id=1, workspace_id=None, title="Test Thread"):
        self.id = id or str(uuid.uuid4())
        self.user_id = user_id
        self.workspace_id = workspace_id
        self.title = title
        self.created_at = datetime.now(UTC)


async def test_require_chat_thread_access_workspace_member():
    """require_chat_thread_access should allow access when user is a workspace member."""
    from fastapi import HTTPException

    from app.services.chat_service import require_chat_thread_access

    ws_id = "ws-chat-access"
    thread = FakeChatThread(workspace_id=ws_id)

    db = AsyncMock()
    call_count = [0]

    async def mock_execute(stmt):
        call_count[0] += 1
        if call_count[0] == 1:
            # get_chat_thread: return the thread
            return FakeResult(items=[thread], scalar_val=thread)
        else:
            # WorkspaceMember check: return a member
            return FakeResult(items=[FakeWorkspaceMember(ws_id, 1)])

    db.execute = mock_execute

    result = await require_chat_thread_access(db, thread.id, user_id=1)
    _assert(result.id == thread.id, "require_chat_thread_access allows workspace member")


async def test_require_chat_thread_access_non_member_denied():
    """require_chat_thread_access should deny access when user is not a workspace member."""
    from fastapi import HTTPException

    from app.services.chat_service import require_chat_thread_access

    ws_id = "ws-chat-denied"
    thread = FakeChatThread(workspace_id=ws_id, user_id=999)

    db = AsyncMock()
    call_count = [0]

    async def mock_execute(stmt):
        call_count[0] += 1
        if call_count[0] == 1:
            return FakeResult(items=[thread], scalar_val=thread)
        else:
            # WorkspaceMember check: no membership found
            return FakeResult(items=[], scalar_val=None)

    db.execute = mock_execute

    try:
        await require_chat_thread_access(db, thread.id, user_id=1)
        _assert(False, "require_chat_thread_access should have raised HTTPException(404)")
    except HTTPException as e:
        _assert(
            e.status_code == 404,
            "require_chat_thread_access denies non-member with 404",
        )


async def test_require_chat_thread_access_fallback_to_user_id():
    """require_chat_thread_access should fall back to user_id when thread has no workspace_id."""
    from app.services.chat_service import require_chat_thread_access

    thread = FakeChatThread(user_id=42, workspace_id=None)

    db = AsyncMock()

    async def mock_execute(stmt):
        return FakeResult(items=[thread], scalar_val=thread)

    db.execute = mock_execute

    result = await require_chat_thread_access(db, thread.id, user_id=42)
    _assert(
        result.id == thread.id,
        "require_chat_thread_access allows owner when no workspace_id",
    )


async def test_require_chat_thread_access_wrong_user_denied():
    """require_chat_thread_access should deny access when user_id doesn't match and no workspace."""
    from fastapi import HTTPException

    from app.services.chat_service import require_chat_thread_access

    thread = FakeChatThread(user_id=42, workspace_id=None)

    db = AsyncMock()

    async def mock_execute(stmt):
        return FakeResult(items=[thread], scalar_val=thread)

    db.execute = mock_execute

    try:
        await require_chat_thread_access(db, thread.id, user_id=999)
        _assert(False, "require_chat_thread_access should have raised HTTPException(404)")
    except HTTPException as e:
        _assert(
            e.status_code == 404,
            "require_chat_thread_access denies wrong user with 404",
        )


async def test_require_chat_thread_access_missing_thread():
    """require_chat_thread_access should 404 when thread doesn't exist."""
    from fastapi import HTTPException

    from app.services.chat_service import require_chat_thread_access

    db = AsyncMock()

    async def mock_execute(stmt):
        return FakeResult(items=[], scalar_val=None)

    db.execute = mock_execute

    try:
        await require_chat_thread_access(db, "nonexistent-id", user_id=1)
        _assert(False, "require_chat_thread_access should have raised HTTPException(404)")
    except HTTPException as e:
        _assert(
            e.status_code == 404,
            "require_chat_thread_access returns 404 for missing thread",
        )


# ── Test: Active missions workspace filtering ───────────────────────────────


async def test_list_active_workspace_filter():
    """list_active should filter by workspace_id when provided."""
    from app.api._mission_cqrs.queries import MissionQueryHandlers

    ws_id = "ws-active-test"
    m1 = FakeMission(workspace_id=ws_id, status="running")

    session = AsyncMock()

    async def mock_execute(stmt):
        stmt_str = str(stmt)
        # When workspace_id is provided, the filter should reference workspace_id
        if "workspace_id" in stmt_str or ws_id in stmt_str:
            return FakeResult(items=[m1], scalar_val=1)
        return FakeResult(items=[], scalar_val=0)

    session.execute = mock_execute

    handler = MissionQueryHandlers(session)
    # Patch cache to return None (cache miss)
    with (
        patch(
            "app.api._mission_cqrs.queries.cache_active",
            new_callable=AsyncMock,
            return_value=None,
        ),
        patch("app.api._mission_cqrs.queries.cache_set_active", new_callable=AsyncMock),
    ):
        result = await handler.list_active(user_id=1, workspace_id=ws_id)
    _assert(len(result) == 1, "list_active with workspace_id returns correct results")


async def test_list_active_fallback_to_user():
    """list_active should fall back to user_id when no workspace_id."""
    from app.api._mission_cqrs.queries import MissionQueryHandlers

    m1 = FakeMission(user_id=42, status="running")

    session = AsyncMock()

    async def mock_execute(stmt):
        return FakeResult(items=[m1], scalar_val=1)

    session.execute = mock_execute

    handler = MissionQueryHandlers(session)
    with (
        patch(
            "app.api._mission_cqrs.queries.cache_active",
            new_callable=AsyncMock,
            return_value=None,
        ),
        patch("app.api._mission_cqrs.queries.cache_set_active", new_callable=AsyncMock),
    ):
        result = await handler.list_active(user_id=42, workspace_id=None)
    _assert(len(result) == 1, "list_active without workspace_id falls back to user_id")


async def test_active_missions_workspace_filter():
    """active_missions should filter by workspace_id when provided."""
    from app.api._mission_cqrs.queries import MissionQueryHandlers

    ws_id = "ws-active-missions"
    m1 = FakeMission(workspace_id=ws_id, status="running")

    session = AsyncMock()
    call_count = [0]

    async def mock_execute(stmt):
        call_count[0] += 1
        if call_count[0] == 1:
            # Mission query
            return FakeResult(items=[m1])
        # Task stats query — return empty (no tasks)
        return FakeResult(items=[])

    session.execute = mock_execute

    handler = MissionQueryHandlers(session)
    with (
        patch(
            "app.api._mission_cqrs.queries.cache_active",
            new_callable=AsyncMock,
            return_value=None,
        ),
        patch("app.api._mission_cqrs.queries.cache_set_active", new_callable=AsyncMock),
    ):
        result = await handler.active_missions(user_id=1, user_role="pro", is_pro=True, workspace_id=ws_id)
    _assert(result.total == 1, "active_missions with workspace_id returns correct results")


async def test_active_missions_fallback_to_user():
    """active_missions should fall back to user_id when no workspace_id."""
    from app.api._mission_cqrs.queries import MissionQueryHandlers

    m1 = FakeMission(user_id=42, status="running")

    session = AsyncMock()
    call_count = [0]

    async def mock_execute(stmt):
        call_count[0] += 1
        if call_count[0] == 1:
            # Mission query
            return FakeResult(items=[m1])
        # Task stats query — return empty (no tasks)
        return FakeResult(items=[])

    session.execute = mock_execute

    handler = MissionQueryHandlers(session)
    with (
        patch(
            "app.api._mission_cqrs.queries.cache_active",
            new_callable=AsyncMock,
            return_value=None,
        ),
        patch("app.api._mission_cqrs.queries.cache_set_active", new_callable=AsyncMock),
    ):
        result = await handler.active_missions(user_id=42, user_role="pro", is_pro=True, workspace_id=None)
    _assert(result.total == 1, "active_missions without workspace_id falls back to user_id")


async def test_active_missions_requires_pro():
    """active_missions should reject non-pro users."""
    from app.api._mission_cqrs.queries import MissionQueryHandlers
    from app.services.mission_errors import MissionForbiddenError

    session = AsyncMock()
    handler = MissionQueryHandlers(session)

    try:
        await handler.active_missions(user_id=1, user_role="member", is_pro=False)
        _assert(False, "active_missions should have raised MissionForbiddenError")
    except MissionForbiddenError:
        _assert(True, "active_missions rejects non-pro users")


# ── Test: Roles.py bug fix ──────────────────────────────────────────────────


async def test_roles_assign_uses_wid_not_tid():
    """roles.py assign/unassign should reference `wid`, not `tid`."""
    import ast
    import inspect

    from app.api.v1 import roles as roles_module

    source = inspect.getsource(roles_module)
    tree = ast.parse(source)

    # Walk the AST looking for Name nodes with id='tid'
    tid_references = [node for node in ast.walk(tree) if isinstance(node, ast.Name) and node.id == "tid"]

    _assert(
        len(tid_references) == 0,
        f"roles.py has no references to undefined `tid` variable (found {len(tid_references)})",
    )


# ── Test: Permissions integration ───────────────────────────────────────────


async def test_permission_service_respects_workspace():
    """PermissionService.check should return False for workspace with no membership."""
    from app.services.permission_service import PermissionService

    db = AsyncMock()

    # User has no membership in workspace
    async def mock_execute(stmt):
        return FakeResult(items=[])

    db.execute = mock_execute

    result = await PermissionService.check(
        db, user_id=1, workspace_id="ws-nonexistent", permission_key="missions.create"
    )
    _assert(
        result is False,
        "PermissionService returns False when user has no workspace membership",
    )


# ── Run all tests ────────────────────────────────────────────────────────────


async def main():
    global _passed, _failed, _errors

    print("\n🧪 Phase 4 — Tenant Isolation Tests")
    print("=" * 60)

    tests = [
        (
            "get_workspace_id dependency",
            [
                test_get_workspace_id_from_header,
                test_get_workspace_id_from_query,
                test_get_workspace_id_fallback_to_primary,
                test_get_workspace_id_no_workspaces,
            ],
        ),
        (
            "Mission service workspace filtering",
            [
                test_list_missions_workspace_filter,
                test_list_missions_fallback_to_user,
                test_create_mission_sets_workspace_id,
                test_create_mission_default_no_workspace,
            ],
        ),
        (
            "Chat access workspace isolation",
            [
                test_require_chat_thread_access_workspace_member,
                test_require_chat_thread_access_non_member_denied,
                test_require_chat_thread_access_fallback_to_user_id,
                test_require_chat_thread_access_wrong_user_denied,
                test_require_chat_thread_access_missing_thread,
            ],
        ),
        (
            "Active missions workspace filtering",
            [
                test_list_active_workspace_filter,
                test_list_active_fallback_to_user,
                test_active_missions_workspace_filter,
                test_active_missions_fallback_to_user,
                test_active_missions_requires_pro,
            ],
        ),
        (
            "Chat service workspace filtering",
            [
                test_create_chat_thread_sets_workspace_id,
                test_list_chat_threads_workspace_filter,
                test_list_chat_threads_fallback_to_user,
            ],
        ),
        (
            "CQRS workspace propagation",
            [
                test_cqrs_create_mission_passes_workspace_id,
                test_cqrs_list_missions_passes_workspace_id,
            ],
        ),
        (
            "Roles.py bug fix",
            [
                test_roles_assign_uses_wid_not_tid,
            ],
        ),
        (
            "Permission service integration",
            [
                test_permission_service_respects_workspace,
            ],
        ),
    ]

    for section_name, test_fns in tests:
        print(f"\n── {section_name} ──")
        for fn in test_fns:
            try:
                await fn()
            except Exception as e:
                _failed += 1
                _errors.append(f"{fn.__name__}: {type(e).__name__}: {e}")
                print(f"  ❌ {fn.__name__}: {type(e).__name__}: {e}")

    print(f"\n{'=' * 60}")
    print(f"Results: {_passed} passed, {_failed} failed out of {_passed + _failed}")
    if _errors:
        print(f"\nFailures:")
        for e in _errors:
            print(f"  • {e}")
    else:
        print("\n🎉 ALL TESTS PASSED")

    return _failed == 0


if __name__ == "__main__":
    success = asyncio.run(main())
    raise SystemExit(0 if success else 1)
