"""Per-directory conftest.

Forces a single, module-scoped event loop for the async tests in
``app/tests/``.  This matters for real-DB integration tests
(e.g. ``test_personal_memory_service.py``) that open sessions on the
module-global SQLAlchemy ``engine``: pytest-asyncio's default
function-scoped loop would tear the engine's pooled connections down
between tests ("attached to a different loop"), breaking cross-test
real-DB access.  A module-scoped loop lets the engine bind once.

Tests that use AsyncMock (the large majority here) are unaffected by
the loop scope.
"""

import asyncio

import pytest
import pytest_asyncio


@pytest.fixture(scope="module")
def event_loop():
    """Reuse a single event loop for the whole module."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="module", autouse=True, loop_scope="module")
async def _rebind_global_engine():
    """Rebind the module-global engine's pool to THIS module's event loop.

    ``app.database.engine`` (and its ``AsyncSessionLocal``) is a process-global
    created at import time.  With a module-scoped ``event_loop`` fixture, each
    real-DB test module runs on its OWN loop, but they all share that one
    global engine.  The first module to touch it binds the asyncpg connection
    pool to its (soon-to-close) loop; a later module then fails with
    "got Future ... attached to a different loop" on the first commit.

    Disposing the pool at the start (and end) of every module forces the
    engine to open fresh connections on the current module's loop.  Modules
    that never touch the DB (pure AsyncMock tests) dispose an empty pool — a
    cheap no-op.
    """
    from app.database import engine

    await engine.dispose()
    yield
    await engine.dispose()


import sys
from unittest.mock import AsyncMock, MagicMock

from fastapi.testclient import TestClient

from app.api.deps import get_current_user
from app.database import get_db
from app.main_fastapi import app


@pytest.fixture
def mock_db_session():
    """Awaited-style mock session matching the auth tests' assumptions.

    The auth routes call the DB as::

        result = await db.execute(select(...))
        user = result.scalar_one_or_none()

    i.e. ``db.execute`` is *awaited* (so it must be an ``AsyncMock``)
    but ``.scalar_one_or_none()`` is called **synchronously** on the
    result.  The tests configure the result chain with::

        mock_db_session.execute.return_value.scalar_one_or_none.return_value = ...

    so the mock must resolve that chain synchronously.  Using
    ``MagicMock(spec=AsyncSession)`` would turn *both* ``execute`` and
    the result's ``scalar_one_or_none`` into ``AsyncMock`` (the spec
    propagates to children), making the sync ``.scalar_one_or_none()``
    return a coroutine instead of the configured value — which is exactly
    the bug that produced ``'coroutine' object has no attribute
    'hashed_password'``.  So we use a plain ``MagicMock`` with
    ``execute`` pinned to an ``AsyncMock`` and its *return value* pinned to
    a plain ``MagicMock`` (sync result), which satisfies both halves.
    """
    mock = MagicMock()
    mock.execute = AsyncMock()
    mock.execute.return_value = MagicMock()
    return mock


@pytest.fixture
def test_client(mock_db_session):
    """FastAPI TestClient with ``get_db`` overridden to the mock session.

    The 7 auth API tests patch the auth-service functions they exercise
    (``check_rate_limit``, ``create_access_token``, ``create_user``,
    ``verify_password``, ``revoke_refresh_token`` …) directly in
    ``app.api.v1.auth``, so the only live dependency reaching the DB is
    ``get_db`` — overridden here to yield ``mock_db_session``.

    Auth-bypass for authenticated endpoints is handled by the tests
    themselves (they set ``app.dependency_overrides[get_current_user]``
    inline), so we intentionally do NOT override ``get_current_user`` here.
    """
    # Preserve any overrides already set, restore them on teardown.
    saved = dict(app.dependency_overrides)

    async def _override_get_db():
        yield mock_db_session

    app.dependency_overrides[get_db] = _override_get_db

    client = TestClient(app)
    try:
        yield client
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(saved)
