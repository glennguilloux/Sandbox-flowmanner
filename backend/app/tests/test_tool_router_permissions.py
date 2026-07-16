"""Unit tests for ToolRouter._permission_ok (SELF-AUDIT-HIGH-04).

Covers the workspace allowlist integration without a live DB by mocking
``app.models.workspace_models.get_workspace_tool_allowlist``.
"""

from __future__ import annotations

import sys
import types
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest


# ── Minimal ToolDefinition stand-in (mirrors langgraph.tool_converter) ──
class _ToolDef:
    def __init__(self, tool_id: str, name: str, requires_approval: bool = False):
        self.tool_id = tool_id
        self.name = name
        self.description = f"desc for {name}"
        self.parameters_schema: dict = {}
        self.category = "general"
        self.is_safe = False
        self.requires_approval = requires_approval

    def to_dict(self) -> dict:
        return {"tool_id": self.tool_id, "name": self.name}


# ── Build a ToolRouter without importing the heavy converter chain ──
def _make_router(**kwargs):
    """Instantiate ToolRouter with a stub registry."""
    # Import lazily so the test does not require the full langgraph stack.
    from app.services.tool_router import ToolRouter

    registry = MagicMock()
    registry.list_tools.return_value = []
    return ToolRouter(registry=registry, **kwargs)


# ── Stub module so `from app.models.workspace_models import ...` resolves ──
@pytest.fixture
def stub_allowlist(monkeypatch):
    """Inject a controllable get_workspace_tool_allowlist into the router module."""
    from app.services import tool_router

    fake = AsyncMock()
    fake_mod = types.ModuleType("app.models.workspace_models")
    fake_mod.get_workspace_tool_allowlist = fake
    # Ensure the parent packages exist in sys.modules
    if "app.models" not in sys.modules:
        sys.modules["app.models"] = types.ModuleType("app.models")
    sys.modules["app.models.workspace_models"] = fake_mod
    monkeypatch.setattr(tool_router, "get_workspace_tool_allowlist", fake, raising=False)
    return fake


def _tool():
    return _ToolDef(tool_id="t_weather", name="weather")


async def test_no_db_session_allows_all(stub_allowlist):
    router = _make_router()
    result = await router._permission_ok(_tool(), uuid.uuid4(), 1, db=None)
    assert result == 1.0
    stub_allowlist.assert_not_called()


async def test_no_allowlist_configured_allows_all(stub_allowlist):
    stub_allowlist.return_value = None  # no rows → all permitted
    router = _make_router()
    result = await router._permission_ok(_tool(), uuid.uuid4(), 1, db=MagicMock())
    assert result == 1.0


async def test_explicit_allowlist_permits_listed_tool(stub_allowlist):
    stub_allowlist.return_value = {"weather", "search"}
    router = _make_router()
    result = await router._permission_ok(_tool(), uuid.uuid4(), 1, db=MagicMock())
    assert result == 1.0


async def test_explicit_allowlist_permits_by_tool_id(stub_allowlist):
    stub_allowlist.return_value = {"t_weather"}  # match on tool_id, not name
    router = _make_router()
    result = await router._permission_ok(_tool(), uuid.uuid4(), 1, db=MagicMock())
    assert result == 1.0


async def test_explicit_allowlist_denies_unlisted_tool(stub_allowlist):
    stub_allowlist.return_value = {"search", "image"}
    router = _make_router()
    result = await router._permission_ok(_tool(), uuid.uuid4(), 1, db=MagicMock())
    assert result == 0.0


async def test_allowlist_lookup_failure_falls_back_to_allow(stub_allowlist):
    stub_allowlist.side_effect = RuntimeError("db down")
    router = _make_router()
    result = await router._permission_ok(_tool(), uuid.uuid4(), 1, db=MagicMock())
    assert result == 1.0


async def test_deny_by_default_flag_with_no_allowlist(stub_allowlist):
    stub_allowlist.return_value = None
    router = _make_router(deny_by_default=True)
    result = await router._permission_ok(_tool(), uuid.uuid4(), 1, db=MagicMock())
    assert result == 0.0


async def test_deny_by_default_flag_with_allowlist_still_permits(stub_allowlist):
    stub_allowlist.return_value = {"weather"}
    router = _make_router(deny_by_default=True)
    result = await router._permission_ok(_tool(), uuid.uuid4(), 1, db=MagicMock())
    assert result == 1.0
