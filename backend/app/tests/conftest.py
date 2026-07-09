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
