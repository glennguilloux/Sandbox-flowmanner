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


@pytest.fixture(scope="module")
def event_loop():
    """Reuse a single event loop for the whole module."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    yield loop
    loop.close()
