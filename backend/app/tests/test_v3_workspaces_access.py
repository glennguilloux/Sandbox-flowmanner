"""Tests for v3 workspace route authorization (t_b1c13e57).

Pins the INVESTIGATION FINDING that v3 workspace routes are
MEMBERSHIP-SCOPED, not scope-middleware-scoped:

  * delete_workspace requires owner membership (→ 204 for an owner)
  * a non-member gets 404 (never leaks existence)
  * a non-owner member gets 403 on a destructive/owner-only route
  * the WORKSPACES_V3_ENDPOINTS feature flag gates everything (404 when off)

Self-contained: uses the REAL app + a real PostgreSQL connection (mirrors
the real-DB pattern in test_governance_poison_scans.py / test_personal_memory_service.py).
Throwaway User / Workspace / WorkspaceMember / FeatureFlag rows are created in
setup and deleted in teardown. Skips the whole module if no PostgreSQL is
reachable (so collection elsewhere stays green).

No ScopeValidationMiddleware registration is asserted here — by design v3
workspace routes do NOT register with register_scope_requirement (see the
module docstring in app/api/v3/workspaces.py).
"""

import asyncio
import os
import uuid

# 32+ char secrets required by app.config production-secret guard.
# Fake test-only values — gitleaks:allow (not real credentials).
os.environ.update(
    OPENAI_API_KEY="***",  # gitleaks:allow — chat_service builds AsyncOpenAI() at import
    JWT_SECRET_KEY="test-jwt-secret-key-1234567890ab",  # gitleaks:allow
    SECRET_KEY="test-secret-key-1234567890abcdefghij",  # gitleaks:allow
    AES_ENCRYPTION_KEY="test-aes-key-16-char-abcdefghijk",  # gitleaks:allow
    SENTRY_WEBHOOK_SECRET="test-webhook-secret-16char",  # gitleaks:allow
    LANGFUSE_PUBLIC_KEY="x",
    LANGFUSE_SECRET_KEY="x",
    LANGFUSE_ENABLED="false",
    APP_ENV="test",
)

# Override the DB URL to the homelab's reachable Postgres (localhost:5432)
# BEFORE importing app.database / app.main_fastapi — those modules materialize
# the async engine at import time using app.config.settings.DATABASE_URL.
# The default points at the docker service name `postgres`, which does not
# resolve on the homelab host. backend/.env carries the correct password.
from app.config import settings

_ENV_DB_URL = os.environ.get("FLOWMANNER_TEST_DB_URL")
if _ENV_DB_URL:
    settings.DATABASE_URL = _ENV_DB_URL

# Resolved DB URL to use inside fixtures / helpers. settings.DATABASE_URL is
# already overridden above (or left at the docker default if the env var is
# unset and the host can reach `postgres`). Never read str(engine.url) for a
# connection string — asyncpg masks the password as "***".
_DB_URL = settings.DATABASE_URL

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.database import engine
from app.main_fastapi import app
from app.models.user import User
from app.models.workspace_models import Workspace, WorkspaceMember


def _pg_reachable() -> bool:
    try:
        asyncio.run(engine.connect().__aenter__())
        return True
    except Exception:
        return False


# Skip the module if no DB is reachable (so collection elsewhere stays green).
if not _pg_reachable():
    pytest.skip(
        "PostgreSQL unreachable — skipping v3 workspace access tests",
        allow_module_level=True,
    )


# ── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
def owner_user():
    return type(
        "U",
        (),
        {
            "id": 99001,
            "email": "ws-owner@example.com",
            "username": "ws-owner",
            "role": "user",
            "is_admin": False,
            "is_active": True,
        },
    )()


@pytest.fixture
def member_user():
    # A workspace member with a non-owner role (e.g. "member").
    return type(
        "U",
        (),
        {
            "id": 99002,
            "email": "ws-member@example.com",
            "username": "ws-member",
            "role": "user",
            "is_admin": False,
            "is_active": True,
        },
    )()


@pytest.fixture
def nonmember_user():
    return type(
        "U",
        (),
        {
            "id": 99003,
            "email": "ws-nonmember@example.com",
            "username": "ws-nonmember",
            "role": "user",
            "is_admin": False,
            "is_active": True,
        },
    )()


@pytest.fixture
def client():
    # Rebind the engine pool + a local session factory to THIS fixture's
    # loop so requests that open a session don't trip the cross-loop error.
    from sqlalchemy.ext.asyncio import async_sessionmaker

    async def override_get_db():
        await engine.dispose()
        SessionLocal = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
        async with SessionLocal() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _override_user(user):
    async def _ocu():
        return user

    app.dependency_overrides[get_current_user] = _ocu


@pytest.fixture
async def seeded():
    """Create throwaway users, a workspace, memberships, and the feature
    flag. Delete everything on teardown.

    Uses a fresh engine bound to this test's loop (see test_governance_poison_scans.py).
    """
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    db_url = _DB_URL
    test_engine = create_async_engine(db_url, pool_pre_ping=True, future=True)
    SessionLocal = async_sessionmaker(bind=test_engine, class_=AsyncSession, expire_on_commit=False)

    owner_id = 99001
    member_id = 99002
    nonmember_id = 99003
    ws_id = str(uuid.uuid4())
    flag_key = "WORKSPACES_V3_ENDPOINTS"

    async with SessionLocal() as db:
        # Idempotent cleanup: blow away any rows left by a prior (failed) run
        # so re-runs don't trip the users_pkey / unique constraints.
        await db.execute(
            delete(WorkspaceMember).where(WorkspaceMember.user_id.in_([owner_id, member_id, nonmember_id]))
        )
        await db.execute(delete(Workspace).where(Workspace.owner_id.in_([owner_id])))
        await db.execute(delete(User).where(User.id.in_([owner_id, member_id, nonmember_id])))
        await db.commit()

    async with SessionLocal() as db:
        users = [
            User(
                id=owner_id,
                email="ws-owner@example.com",
                username="ws-owner",
                hashed_password="x",
                role="user",
                is_active=True,
            ),
            User(
                id=member_id,
                email="ws-member@example.com",
                username="ws-member",
                hashed_password="x",
                role="user",
                is_active=True,
            ),
            User(
                id=nonmember_id,
                email="ws-nonmember@example.com",
                username="ws-nonmember",
                hashed_password="x",
                role="user",
                is_active=True,
            ),
        ]
        db.add_all(users)
        await db.flush()

        ws = Workspace(
            id=ws_id,
            name="ws-scope-test",
            slug=f"ws-scope-test-{abs(hash(ws_id))}",
            owner_id=owner_id,
        )
        db.add(ws)
        await db.flush()

        members = [
            WorkspaceMember(workspace_id=ws_id, user_id=owner_id, role="owner"),
            WorkspaceMember(workspace_id=ws_id, user_id=member_id, role="member"),
        ]
        db.add_all(members)

        # Ensure the feature flag exists and is ENABLED for these tests.
        res = await db.execute(
            text("SELECT 1 FROM feature_flags WHERE key = :k"),
            {"k": flag_key},
        )
        if res.scalar() is None:
            await db.execute(
                text("INSERT INTO feature_flags (key, name, enabled_globally) " "VALUES (:k, :n, TRUE)"),
                {"k": flag_key, "n": "Workspaces V3 Endpoints"},
            )
        else:
            await db.execute(
                text("UPDATE feature_flags SET enabled_globally = TRUE WHERE key = :k"),
                {"k": flag_key},
            )
        await db.commit()

    yield {"workspace_id": ws_id}

    async with SessionLocal() as db:
        await db.execute(delete(WorkspaceMember).where(WorkspaceMember.workspace_id == ws_id))
        await db.execute(delete(Workspace).where(Workspace.id == ws_id))
        await db.execute(delete(User).where(User.id.in_([owner_id, member_id, nonmember_id])))
        # Leave the flag row in place (other test modules may use it) but
        # reset to off so we don't leak enabled state.
        await db.execute(
            text("UPDATE feature_flags SET enabled_globally = FALSE WHERE key = :k"),
            {"k": flag_key},
        )
        await db.commit()
    await test_engine.dispose()


# ── Tests ───────────────────────────────────────────────────────────────────


def test_delete_workspace_owner_allowed(client, owner_user, seeded):
    _override_user(owner_user)
    resp = client.delete(f"/api/v3/workspaces/{seeded['workspace_id']}")
    # 204 No Content on success.
    assert resp.status_code == 204


def test_delete_workspace_member_forbidden(client, member_user, seeded):
    _override_user(member_user)
    resp = client.delete(f"/api/v3/workspaces/{seeded['workspace_id']}")
    # Non-owner member → 403 (they know the workspace exists).
    assert resp.status_code == 403


def test_delete_workspace_nonmember_404(client, nonmember_user, seeded):
    _override_user(nonmember_user)
    resp = client.delete(f"/api/v3/workspaces/{seeded['workspace_id']}")
    # Non-member → 404, never leaks existence.
    assert resp.status_code == 404


def test_get_workspace_nonmember_404(client, nonmember_user, seeded):
    _override_user(nonmember_user)
    resp = client.get(f"/api/v3/workspaces/{seeded['workspace_id']}")
    assert resp.status_code == 404


def _set_flag(enabled: bool) -> None:
    """Toggle the WORKSPACES_V3_ENDPOINTS flag directly (sync wrapper)."""
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    db_url = _DB_URL
    test_engine = create_async_engine(db_url, pool_pre_ping=True, future=True)
    SessionLocal = async_sessionmaker(bind=test_engine, class_=AsyncSession, expire_on_commit=False)

    async def _run():
        async with SessionLocal() as db:
            await db.execute(
                text("UPDATE feature_flags SET enabled_globally = :v " "WHERE key = 'WORKSPACES_V3_ENDPOINTS'"),
                {"v": enabled},
            )
            await db.commit()

    asyncio.run(_run())
    asyncio.run(test_engine.dispose())


def test_flag_off_returns_404(client, owner_user, seeded):
    # Turn the feature flag off, then any workspace route 404s.
    _set_flag(False)

    _override_user(owner_user)
    resp = client.get(f"/api/v3/workspaces/{seeded['workspace_id']}")
    assert resp.status_code == 404

    # Restore flag for the rest of the suite.
    _set_flag(True)
