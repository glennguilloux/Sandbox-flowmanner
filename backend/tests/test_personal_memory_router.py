"""TDD tests for T23: v2 /personal_memory router (Memory Inspector API).

Plan reference: D0-30, T23 — five endpoints on /api/v2/personal_memory.

The router is a thin envelope-wrapping layer over ``PersonalMemoryService``
— every assertion here is HTTP-level (status code, envelope shape,
payload keys). The service layer is exercised by
``tests/test_personal_memory_service.py``; this file only asserts the
HTTP contract.

Test strategy
-------------
* Real PostgreSQL via ``DATABASE_URL`` (project convention).
* ``TestClient`` against the real FastAPI ``app`` (no lifespan so we
  don't boot the LLM stack, redis mocks already exist in
  ``tests/conftest.py``).
* ``get_current_user`` and ``get_workspace_id`` are overridden per-test
  so we don't need a real JWT.
* All write paths commit to the real DB; cleanup deletes by ``user_id``
  after each test.

The SECURITY GUARDRAIL test (case 15) is the load-bearing isolation
check — it proves the (user_id, workspace_id) tuple is enforced at the
API boundary, not just in the service layer.

Run from ``/opt/flowmanner/backend``::

    DATABASE_URL="postgresql+asyncpg://flowmanner:5f206ab26d543ba5424385cb10200efc@127.0.0.1:5432/flowmanner" \\
      .venv/bin/python -m pytest tests/test_personal_memory_router.py -v --timeout=15

Cases
-----
1.  POST /recall — valid query returns items + total envelope
2.  POST /recall — empty result returns total=0
3.  POST /recall — bad min_confidence=2.0 returns 422 (Pydantic validation)
4.  GET  /inspector — paginated list returns items + total
5.  GET  /inspector — scope filter narrows results
6.  GET  /inspector — claim_type filter narrows results
7.  PATCH /claims/{id} — updates editable fields, returns updated claim
8.  PATCH /claims/{id} — unknown id returns 404 PERSONAL_MEMORY_CLAIM_NOT_FOUND
9.  PATCH /claims/{id} — forbidden field (e.g. user_id) is rejected
10. DELETE /claims/{id} — hard deletes, returns 204
11. DELETE /claims/{id} — unknown id returns 404 envelope (not raw 404)
12. POST /forget — soft deletes (sets deleted_at), returns claim
13. POST /forget — hard=true actually removes the row
14. POST /forget — unknown id returns 404
15. SECURITY GUARDRAIL — claim in workspace A is INVISIBLE to user in
    workspace B (cross-workspace isolation enforced via the API)
"""

from __future__ import annotations

import os
import uuid
from typing import Any

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

# Ensure DATABASE_URL is set BEFORE importing app modules.
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://flowmanner:5f206ab26d543ba5424385cb10200efc@127.0.0.1:5432/flowmanner",
)

# Late imports so env var is honored.
from app.api.deps import get_current_user, get_db, get_workspace_id  # noqa: E402
from app.main_fastapi import app  # noqa: E402
from app.models.personal_memory_models import PersonalMemoryClaim  # noqa: E402
from app.models.user import User  # noqa: E402
from app.models.workspace_models import Workspace  # noqa: E402


# ═══════════════════════════════════════════════════════════════════════════
# get_db override — bypass the app's .env DATABASE_URL (which points at
# the docker hostname `workflow-postgres` from inside the host) and use
# our test engine pointed at 127.0.0.1. This is the standard pattern
# for TestClient + live-DB tests in this project (see flowmanner-dev
# skill: "DB hostname: .env has DATABASE_URL=...@postgres:...; from
# the host venv, postgres is NOT resolvable").
# ═══════════════════════════════════════════════════════════════════════════


async def _override_get_db():
    """Yield a session from the test engine (127.0.0.1)."""
    async with TestSessionLocal() as session:
        try:
            yield session
        finally:
            # session.close() is handled by the context manager; no
            # commit/rollback here — the service layer is the
            # transaction boundary (per services/AGENTS.md rule 3).
            pass

pytestmark = pytest.mark.integration

# ═══════════════════════════════════════════════════════════════════════════
# Engine + session factory (session-scoped)
# ═══════════════════════════════════════════════════════════════════════════

_TEST_DATABASE_URL = os.environ["DATABASE_URL"]
# Some .env files use the docker hostname `postgres`; for tests on the
# host we need `127.0.0.1`. Only swap if it's still the bare docker hostname.
if "@postgres:" in _TEST_DATABASE_URL:
    _TEST_DATABASE_URL = _TEST_DATABASE_URL.replace("@postgres:", "@127.0.0.1:")
_test_engine = create_async_engine(
    _TEST_DATABASE_URL, echo=False, poolclass=NullPool
)
TestSessionLocal = async_sessionmaker(
    _test_engine, class_=AsyncSession, expire_on_commit=False
)


@pytest_asyncio.fixture(scope="session", autouse=True)
async def _manage_engine():
    """Dispose test engine after the suite finishes."""
    yield
    await _test_engine.dispose()


@pytest_asyncio.fixture(scope="session", autouse=True)
async def _skip_if_no_db():
    """Skip the entire module if PostgreSQL is unreachable."""
    async with TestSessionLocal() as s:
        try:
            await s.execute(text("SELECT 1"))
        except Exception as exc:
            pytest.skip(f"Database not reachable: {exc}")


# ═══════════════════════════════════════════════════════════════════════════
# Test-data factories
# ═══════════════════════════════════════════════════════════════════════════


def _new_id() -> int:
    """Unique user ID (unlikely to collide with real users)."""
    return uuid.uuid4().int % 900_000_000 + 100_000


def _new_workspace_id() -> str:
    # Workspace.id is VARCHAR(36); the prefix below + 21 hex chars = 35.
    return f"ws-pm-router-{uuid.uuid4().hex[:21]}"


async def _make_user(
    session: AsyncSession, *, suffix: str = "owner"
) -> User:
    user_id = _new_id()
    user = User(
        id=user_id,
        email=f"pm-router-{user_id}-{suffix}@test.flowmanner.example",
        username=f"pm_router_{user_id}_{suffix}",
        full_name=f"PM Router Test {user_id} {suffix}",
        hashed_password="test-hash-not-real",
        is_active=True,
        is_admin=False,
        role="free",
    )
    session.add(user)
    await session.flush()
    return user


async def _make_workspace(
    session: AsyncSession, *, owner_id: int
) -> Workspace:
    ws = Workspace(
        id=_new_workspace_id(),
        name=f"test-ws-{uuid.uuid4().hex[:8]}",
        slug=f"test-ws-{uuid.uuid4().hex[:12]}",
        owner_id=owner_id,
        plan="free",
        is_active=True,
    )
    session.add(ws)
    await session.flush()
    return ws


async def _make_claim(
    session: AsyncSession,
    *,
    user_id: int,
    workspace_id: str,
    subject: str,
    predicate: str = "prefers",
    obj: dict[str, Any] | None = None,
    claim_type: str = "preference",
    scope: str = "personal",
    source_type: str = "user_explicit",
    confidence: float = 0.5,
    importance: float = 0.5,
    sensitivity: str = "normal",
) -> PersonalMemoryClaim:
    claim = PersonalMemoryClaim(
        user_id=user_id,
        workspace_id=workspace_id,
        subject=subject,
        predicate=predicate,
        object=obj if obj is not None else {"value": subject},
        claim_type=claim_type,
        scope=scope,
        source_type=source_type,
        sensitivity=sensitivity,
        confidence=confidence,
        importance=importance,
    )
    session.add(claim)
    await session.flush()
    return claim


# ═══════════════════════════════════════════════════════════════════════════
# Per-test fixture: one user + one workspace + TestClient with overrides
# ═══════════════════════════════════════════════════════════════════════════


@pytest_asyncio.fixture
async def ctx():
    """Yield (user, workspace, claim_factory, client) for one test.

    The TestClient is created against the real FastAPI app with
    ``get_current_user`` and ``get_workspace_id`` overridden so the
    request runs as the freshly-created test user in the test
    workspace. Cleanup deletes all rows owned by the test user.
    """
    session = TestSessionLocal()
    try:
        owner = await _make_user(session)
        ws = await _make_workspace(session, owner_id=owner.id)
        await session.commit()

        # Override deps for this test.
        current_user_override = _current_user_factory(owner)
        workspace_id_override = _workspace_id_factory(ws.id)

        app.dependency_overrides[get_current_user] = current_user_override
        app.dependency_overrides[get_workspace_id] = workspace_id_override
        app.dependency_overrides[get_db] = _override_get_db

        # Build the client AFTER overrides are set; the test_client
        # wrapper handles async-app bridging internally.
        with TestClient(app) as client:
            try:
                yield {
                    "user": owner,
                    "workspace": ws,
                    "session": session,
                    "client": client,
                }
            finally:
                # Cleanup overrides + per-test rows.
                app.dependency_overrides.pop(get_current_user, None)
                app.dependency_overrides.pop(get_workspace_id, None)
                app.dependency_overrides.pop(get_db, None)
    finally:
        try:
            await session.close()
        except Exception:
            pass
        # Best-effort cleanup of persisted rows.
        try:
            async with TestSessionLocal() as cleanup:
                await cleanup.execute(
                    text(
                        "DELETE FROM personal_memory_claims "
                        "WHERE user_id = :uid"
                    ),
                    {"uid": owner.id},
                )
                await cleanup.execute(
                    text(
                        "DELETE FROM workspaces WHERE owner_id = :uid"
                    ),
                    {"uid": owner.id},
                )
                await cleanup.execute(
                    text("DELETE FROM users WHERE id = :uid"),
                    {"uid": owner.id},
                )
                await cleanup.commit()
        except Exception:
            pass


def _current_user_factory(user: User):
    """Build a get_current_user override that returns the given user."""

    async def _override():
        return user

    return _override


def _workspace_id_factory(workspace_id: str):
    """Build a get_workspace_id override that returns the given workspace."""

    async def _override():
        return workspace_id

    return _override


def _swap_user_override(user: User) -> None:
    """Swap get_current_user to return ``user`` for the next request.

    Used by the SECURITY GUARDRAIL test to switch identities mid-test.
    """
    app.dependency_overrides[get_current_user] = _current_user_factory(user)


def _swap_workspace_override(workspace_id: str) -> None:
    app.dependency_overrides[get_workspace_id] = _workspace_id_factory(
        workspace_id
    )


# ═══════════════════════════════════════════════════════════════════════════
# 1. POST /recall — success
# ═══════════════════════════════════════════════════════════════════════════


async def test_recall_returns_matching_claims(ctx) -> None:
    """A query that matches a stored subject returns items + total."""
    client = ctx["client"]
    session = ctx["session"]
    user = ctx["user"]
    ws = ctx["workspace"]

    await _make_claim(
        session,
        user_id=user.id,
        workspace_id=ws.id,
        subject="Python",
        predicate="prefers",
        obj={"value": "Python"},
    )
    await _make_claim(
        session,
        user_id=user.id,
        workspace_id=ws.id,
        subject="Coffee",
        predicate="likes",
        obj={"value": "espresso"},
    )
    await session.commit()

    resp = client.post(
        "/api/v2/personal_memory/recall",
        json={"query": "Python", "top_k": 10},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    # Envelope shape.
    assert "data" in body
    assert "meta" in body
    assert body["error"] is None
    # Payload.
    assert body["data"]["total"] == 1
    assert len(body["data"]["items"]) == 1
    item = body["data"]["items"][0]
    # Flat shape: claim fields are at the top level of the item.
    assert item["subject"] == "Python"
    assert item["claim_type"] == "preference"
    assert item["workspace_id"] == ws.id
    # similarity is present (None for T19 substring match).
    assert "similarity" in item
    assert item["similarity"] is None


# ═══════════════════════════════════════════════════════════════════════════
# 2. POST /recall — empty
# ═══════════════════════════════════════════════════════════════════════════


async def test_recall_empty_result(ctx) -> None:
    """A query that matches nothing returns total=0 and items=[]."""
    client = ctx["client"]
    resp = client.post(
        "/api/v2/personal_memory/recall",
        json={"query": "NoSuchSubjectEverExists"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["data"]["total"] == 0
    assert body["data"]["items"] == []


# ═══════════════════════════════════════════════════════════════════════════
# 3. POST /recall — validation error (min_confidence > 1.0)
# ═══════════════════════════════════════════════════════════════════════════


async def test_recall_validation_error(ctx) -> None:
    """min_confidence=2.0 violates Pydantic Field(le=1.0) → 422."""
    client = ctx["client"]
    resp = client.post(
        "/api/v2/personal_memory/recall",
        json={"query": "x", "min_confidence": 2.0},
    )
    # FastAPI's default validation error: 422 (handled by middleware
    # → VALIDATION_ERROR envelope). Pydantic rejects before the route
    # ever runs.
    assert resp.status_code == 422, resp.text
    body = resp.json()
    assert body["data"] is None
    assert body["error"] is not None
    assert body["error"]["code"] in {
        "VALIDATION_ERROR",
        "PERSONAL_MEMORY_VALIDATION_ERROR",
    }


# ═══════════════════════════════════════════════════════════════════════════
# 4. GET /inspector — paginated list
# ═══════════════════════════════════════════════════════════════════════════


async def test_inspector_paginated(ctx) -> None:
    """GET /inspector returns the paginated envelope with items + total."""
    client = ctx["client"]
    session = ctx["session"]
    user = ctx["user"]
    ws = ctx["workspace"]

    for i in range(5):
        await _make_claim(
            session,
            user_id=user.id,
            workspace_id=ws.id,
            subject=f"subject-{i}",
        )
    await session.commit()

    resp = client.get(
        "/api/v2/personal_memory/inspector",
        params={"page": 1, "per_page": 10},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["error"] is None
    data = body["data"]
    assert data["total"] == 5
    assert data["page"] == 1
    assert data["per_page"] == 10
    # paginated() helper computes pages = ceil(total/per_page).
    assert data["pages"] == 1
    assert len(data["items"]) == 5


# ═══════════════════════════════════════════════════════════════════════════
# 5. GET /inspector — scope filter
# ═══════════════════════════════════════════════════════════════════════════


async def test_inspector_scope_filter(ctx) -> None:
    """scope=workspace narrows the listing to workspace-scoped claims."""
    client = ctx["client"]
    session = ctx["session"]
    user = ctx["user"]
    ws = ctx["workspace"]

    await _make_claim(
        session,
        user_id=user.id,
        workspace_id=ws.id,
        subject="personal-thing",
        scope="personal",
    )
    await _make_claim(
        session,
        user_id=user.id,
        workspace_id=ws.id,
        subject="workspace-thing",
        scope="workspace",
    )
    await session.commit()

    resp = client.get(
        "/api/v2/personal_memory/inspector",
        params={"scope": "workspace"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["data"]["total"] == 1
    assert body["data"]["items"][0]["subject"] == "workspace-thing"
    assert body["data"]["items"][0]["scope"] == "workspace"


# ═══════════════════════════════════════════════════════════════════════════
# 6. GET /inspector — claim_type filter
# ═══════════════════════════════════════════════════════════════════════════


async def test_inspector_claim_type_filter(ctx) -> None:
    """claim_type=preference narrows the listing to preference claims."""
    client = ctx["client"]
    session = ctx["session"]
    user = ctx["user"]
    ws = ctx["workspace"]

    await _make_claim(
        session,
        user_id=user.id,
        workspace_id=ws.id,
        subject="a-pref",
        claim_type="preference",
    )
    await _make_claim(
        session,
        user_id=user.id,
        workspace_id=ws.id,
        subject="a-fact",
        claim_type="fact",
    )
    await session.commit()

    resp = client.get(
        "/api/v2/personal_memory/inspector",
        params={"claim_type": "preference"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["data"]["total"] == 1
    assert body["data"]["items"][0]["claim_type"] == "preference"


# ═══════════════════════════════════════════════════════════════════════════
# 7. PATCH /claims/{id} — update
# ═══════════════════════════════════════════════════════════════════════════


async def test_patch_claim_updates_editable_fields(ctx) -> None:
    """PATCH with editable fields returns the updated claim."""
    client = ctx["client"]
    session = ctx["session"]
    user = ctx["user"]
    ws = ctx["workspace"]

    claim = await _make_claim(
        session,
        user_id=user.id,
        workspace_id=ws.id,
        subject="old-subject",
    )
    await session.commit()

    resp = client.patch(
        f"/api/v2/personal_memory/claims/{claim.id}",
        json={"subject": "new-subject", "confidence": 0.9},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["error"] is None
    data = body["data"]
    assert data["subject"] == "new-subject"
    assert data["confidence"] == 0.9


# ═══════════════════════════════════════════════════════════════════════════
# 8. PATCH /claims/{id} — 404 not found
# ═══════════════════════════════════════════════════════════════════════════


async def test_patch_claim_not_found(ctx) -> None:
    """Unknown claim id returns 404 with PERSONAL_MEMORY_CLAIM_NOT_FOUND."""
    client = ctx["client"]
    unknown = uuid.uuid4()
    resp = client.patch(
        f"/api/v2/personal_memory/claims/{unknown}",
        json={"subject": "new"},
    )
    assert resp.status_code == 404, resp.text
    body = resp.json()
    assert body["data"] is None
    assert body["error"] is not None
    assert body["error"]["code"] == "PERSONAL_MEMORY_CLAIM_NOT_FOUND"


# ═══════════════════════════════════════════════════════════════════════════
# 9. PATCH /claims/{id} — forbidden field rejected
# ═══════════════════════════════════════════════════════════════════════════


async def test_patch_claim_forbidden_field_rejected(ctx) -> None:
    """PATCH with user_id (an immutable field) is rejected by 422."""
    client = ctx["client"]
    session = ctx["session"]
    user = ctx["user"]
    ws = ctx["workspace"]

    claim = await _make_claim(
        session,
        user_id=user.id,
        workspace_id=ws.id,
        subject="x",
    )
    await session.commit()

    resp = client.patch(
        f"/api/v2/personal_memory/claims/{claim.id}",
        json={"user_id": 9999, "subject": "y"},
    )
    # Pydantic extra="forbid" → 422.
    assert resp.status_code == 422, resp.text
    body = resp.json()
    assert body["data"] is None
    assert body["error"] is not None


# ═══════════════════════════════════════════════════════════════════════════
# 10. DELETE /claims/{id} — 204
# ═══════════════════════════════════════════════════════════════════════════


async def test_delete_claim_hard_forget(ctx) -> None:
    """DELETE /claims/{id} removes the row and returns 204."""
    client = ctx["client"]
    session = ctx["session"]
    user = ctx["user"]
    ws = ctx["workspace"]

    claim = await _make_claim(
        session,
        user_id=user.id,
        workspace_id=ws.id,
        subject="x",
    )
    claim_id = claim.id
    await session.commit()

    resp = client.delete(
        f"/api/v2/personal_memory/claims/{claim_id}"
    )
    assert resp.status_code == 204, resp.text

    # Verify the row is gone.
    async with TestSessionLocal() as verify:
        result = await verify.execute(
            text(
                "SELECT id FROM personal_memory_claims WHERE id = :id"
            ),
            {"id": str(claim_id)},
        )
        assert result.scalar_one_or_none() is None


# ═══════════════════════════════════════════════════════════════════════════
# 11. DELETE /claims/{id} — 404
# ═══════════════════════════════════════════════════════════════════════════


async def test_delete_claim_not_found(ctx) -> None:
    """DELETE on an unknown id returns a 404 envelope (NOT raw 404)."""
    client = ctx["client"]
    unknown = uuid.uuid4()
    resp = client.delete(
        f"/api/v2/personal_memory/claims/{unknown}"
    )
    assert resp.status_code == 404, resp.text
    body = resp.json()
    # The v2 envelope shape — error envelope, not FastAPI's {"detail": ...}.
    assert body["data"] is None
    assert body["error"] is not None
    assert body["error"]["code"] == "PERSONAL_MEMORY_CLAIM_NOT_FOUND"
    assert "meta" in body


# ═══════════════════════════════════════════════════════════════════════════
# 12. POST /forget — soft delete
# ═══════════════════════════════════════════════════════════════════════════


async def test_forget_soft(ctx) -> None:
    """POST /forget with hard=False sets deleted_at and returns the claim."""
    client = ctx["client"]
    session = ctx["session"]
    user = ctx["user"]
    ws = ctx["workspace"]

    claim = await _make_claim(
        session,
        user_id=user.id,
        workspace_id=ws.id,
        subject="x",
    )
    await session.commit()

    resp = client.post(
        "/api/v2/personal_memory/forget",
        json={"claim_id": str(claim.id), "hard": False},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["error"] is None
    data = body["data"]
    # Row is still there but with deleted_at populated.
    assert data["deleted_at"] is not None
    assert data["id"] == str(claim.id)

    # Verify in DB.
    async with TestSessionLocal() as verify:
        result = await verify.execute(
            text(
                "SELECT deleted_at FROM personal_memory_claims "
                "WHERE id = :id"
            ),
            {"id": str(claim.id)},
        )
        row = result.scalar_one_or_none()
        assert row is not None  # soft: still in the table


# ═══════════════════════════════════════════════════════════════════════════
# 13. POST /forget — hard delete
# ═══════════════════════════════════════════════════════════════════════════


async def test_forget_hard(ctx) -> None:
    """POST /forget with hard=True removes the row entirely."""
    client = ctx["client"]
    session = ctx["session"]
    user = ctx["user"]
    ws = ctx["workspace"]

    claim = await _make_claim(
        session,
        user_id=user.id,
        workspace_id=ws.id,
        subject="x",
    )
    claim_id = claim.id
    await session.commit()

    resp = client.post(
        "/api/v2/personal_memory/forget",
        json={"claim_id": str(claim_id), "hard": True},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["error"] is None

    # Verify the row is gone.
    async with TestSessionLocal() as verify:
        result = await verify.execute(
            text(
                "SELECT id FROM personal_memory_claims WHERE id = :id"
            ),
            {"id": str(claim_id)},
        )
        assert result.scalar_one_or_none() is None


# ═══════════════════════════════════════════════════════════════════════════
# 14. POST /forget — 404
# ═══════════════════════════════════════════════════════════════════════════


async def test_forget_not_found(ctx) -> None:
    """POST /forget with an unknown claim_id returns 404 envelope."""
    client = ctx["client"]
    unknown = uuid.uuid4()
    resp = client.post(
        "/api/v2/personal_memory/forget",
        json={"claim_id": str(unknown), "hard": False},
    )
    assert resp.status_code == 404, resp.text
    body = resp.json()
    assert body["data"] is None
    assert body["error"] is not None
    assert body["error"]["code"] == "PERSONAL_MEMORY_CLAIM_NOT_FOUND"


# ═══════════════════════════════════════════════════════════════════════════
# 15. SECURITY GUARDRAIL — cross-workspace isolation via API
# ═══════════════════════════════════════════════════════════════════════════


async def test_cross_workspace_isolation_enforced_via_api() -> None:
    """A claim in workspace A is INVISIBLE to a user in workspace B.

    The (user_id, workspace_id) predicate is the project-wide isolation
    guardrail. This test asserts the guardrail is enforced at the API
    boundary, not just in the service layer — by switching the request
    identity mid-test from a user in ws-A to a user in ws-B and
    confirming the ws-A claim is unreachable.
    """
    # Two sessions so we can stage two users + two workspaces.
    session_a = TestSessionLocal()
    session_b = TestSessionLocal()
    try:
        user_a = await _make_user(session_a, suffix="alice")
        ws_a = await _make_workspace(session_a, owner_id=user_a.id)
        user_b = await _make_user(session_b, suffix="bob")
        ws_b = await _make_workspace(session_b, owner_id=user_b.id)
        await session_a.commit()
        await session_b.commit()

        # Alice's claim — a *fact* only she should be able to see.
        await _make_claim(
            session_a,
            user_id=user_a.id,
            workspace_id=ws_a.id,
            subject="alice-secret",
            predicate="knows",
            obj={"value": "the cake is a lie"},
            scope="personal",
        )
        await session_a.commit()

        # ── Phase 1: Alice sees her own claim. ──────────────────────
        app.dependency_overrides[get_current_user] = _current_user_factory(
            user_a
        )
        app.dependency_overrides[get_workspace_id] = _workspace_id_factory(
            ws_a.id
        )
        app.dependency_overrides[get_db] = _override_get_db

        with TestClient(app) as client:
            try:
                resp = client.get(
                    "/api/v2/personal_memory/inspector",
                    params={"page": 1, "per_page": 50},
                )
                assert resp.status_code == 200, resp.text
                alice_body = resp.json()
                assert alice_body["data"]["total"] == 1
                assert (
                    alice_body["data"]["items"][0]["subject"] == "alice-secret"
                )

                # ── Phase 2: Swap to Bob. Bob is in ws_b, NOT a member
                # of ws_a. He must NOT see Alice's claim. ──────────────
                _swap_user_override(user_b)
                _swap_workspace_override(ws_b.id)

                resp = client.get(
                    "/api/v2/personal_memory/inspector",
                    params={"page": 1, "per_page": 50},
                )
                assert resp.status_code == 200, resp.text
                bob_body = resp.json()
                bob_subjects = [
                    item["subject"] for item in bob_body["data"]["items"]
                ]
                # ★ The guardrail: Alice's claim must not appear in Bob's
                #   listing under any circumstances.
                assert "alice-secret" not in bob_subjects
                assert bob_body["data"]["total"] == 0

                # ── Phase 3: Bob cannot PATCH/DELETE/recall Alice's
                # claim by guessing the id. Each must surface 404
                # PERSONAL_MEMORY_CLAIM_NOT_FOUND (leak-avoidance). ───
                alice_claim_id = alice_body["data"]["items"][0]["id"]

                # PATCH
                resp = client.patch(
                    f"/api/v2/personal_memory/claims/{alice_claim_id}",
                    json={"subject": "hacked"},
                )
                assert resp.status_code == 404, resp.text
                assert resp.json()["error"]["code"] == (
                    "PERSONAL_MEMORY_CLAIM_NOT_FOUND"
                )

                # DELETE
                resp = client.delete(
                    f"/api/v2/personal_memory/claims/{alice_claim_id}"
                )
                assert resp.status_code == 404, resp.text
                assert resp.json()["error"]["code"] == (
                    "PERSONAL_MEMORY_CLAIM_NOT_FOUND"
                )

                # POST /forget
                resp = client.post(
                    "/api/v2/personal_memory/forget",
                    json={"claim_id": str(alice_claim_id), "hard": False},
                )
                assert resp.status_code == 404, resp.text
                assert resp.json()["error"]["code"] == (
                    "PERSONAL_MEMORY_CLAIM_NOT_FOUND"
                )
            finally:
                app.dependency_overrides.pop(get_current_user, None)
                app.dependency_overrides.pop(get_workspace_id, None)
                app.dependency_overrides.pop(get_db, None)

    finally:
        # Clear overrides first, then cleanup rows.
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(get_workspace_id, None)
        for s, uid in (
            (session_a, user_a.id),
            (session_b, user_b.id),
        ):
            try:
                await s.close()
            except Exception:
                pass
        try:
            async with TestSessionLocal() as cleanup:
                await cleanup.execute(
                    text(
                        "DELETE FROM personal_memory_claims "
                        "WHERE user_id IN (:a, :b)"
                    ),
                    {"a": user_a.id, "b": user_b.id},
                )
                await cleanup.execute(
                    text(
                        "DELETE FROM workspaces "
                        "WHERE owner_id IN (:a, :b)"
                    ),
                    {"a": user_a.id, "b": user_b.id},
                )
                await cleanup.execute(
                    text(
                        "DELETE FROM users WHERE id IN (:a, :b)"
                    ),
                    {"a": user_a.id, "b": user_b.id},
                )
                await cleanup.commit()
        except Exception:
            pass
