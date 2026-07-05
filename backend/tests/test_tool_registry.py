"""Phase 1 tests — tool registry, scope filtering, discovery endpoint.

Covers:
- ToolMetadata new fields have correct defaults
- ToolRegistry loads and filters tools
- _user_has_scopes logic
- _get_chat_openai_tools allowlist
- _execute_tool_call scope denial path
- GET /api/v2/tools/discover endpoint (if test client available)
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.tools.base import (
    BaseTool,
    ToolMetadata,
    ToolRegistry,
    ToolResult,
    get_tool_registry,
)

# ── Fixtures ───────────────────────────────────────────────────────────


class _DummyTool(BaseTool):
    """Minimal tool for testing."""

    def __init__(self, tool_id: str = "test_tool", **meta_overrides):
        defaults = {
            "tool_id": tool_id,
            "name": tool_id,
            "description": f"Test tool: {tool_id}",
            "category": "test",
            "tags": ["test"],
        }
        defaults.update(meta_overrides)
        metadata = ToolMetadata(**defaults)
        super().__init__(metadata=metadata)

    async def execute(self, input_data: dict) -> ToolResult:
        return ToolResult.success_result(self.tool_id, {"echo": input_data})


@pytest.fixture
def fresh_registry():
    """Return a fresh ToolRegistry (not the global singleton)."""
    return ToolRegistry()


# ── ToolMetadata ───────────────────────────────────────────────────────


class TestToolMetadataNewFields:
    """Verify the 3 new fields on ToolMetadata have correct defaults."""

    def test_required_scopes_default_empty(self):
        m = ToolMetadata(tool_id="x", name="x", description="x")
        assert m.required_scopes == []

    def test_requires_sandbox_default_false(self):
        m = ToolMetadata(tool_id="x", name="x", description="x")
        assert m.requires_sandbox is False

    def test_rate_limit_key_default_none(self):
        m = ToolMetadata(tool_id="x", name="x", description="x")
        assert m.rate_limit_key is None

    def test_existing_rate_limit_preserved(self):
        m = ToolMetadata(tool_id="x", name="x", description="x", rate_limit=100)
        assert m.rate_limit == 100

    def test_new_fields_can_be_set(self):
        m = ToolMetadata(
            tool_id="x",
            name="x",
            description="x",
            required_scopes=["admin", "tools:write"],
            requires_sandbox=True,
            rate_limit_key="browser",
        )
        assert m.required_scopes == ["admin", "tools:write"]
        assert m.requires_sandbox is True
        assert m.rate_limit_key == "browser"

    def test_existing_fields_unaffected(self):
        m = ToolMetadata(
            tool_id="x",
            name="x",
            description="x",
            requires_auth=True,
            rate_limit=50,
            timeout_seconds=60,
        )
        assert m.requires_auth is True
        assert m.rate_limit == 50
        assert m.timeout_seconds == 60


# ── ToolRegistry ───────────────────────────────────────────────────────


class TestToolRegistry:
    def test_register_and_get(self, fresh_registry):
        tool = _DummyTool("alpha")
        fresh_registry.register(tool)
        assert fresh_registry.get("alpha") is tool

    def test_list_all(self, fresh_registry):
        fresh_registry.register(_DummyTool("a"))
        fresh_registry.register(_DummyTool("b"))
        assert len(fresh_registry.list_all()) == 2

    def test_list_by_category(self, fresh_registry):
        fresh_registry.register(_DummyTool("a", category="sandbox"))
        fresh_registry.register(_DummyTool("b", category="search"))
        fresh_registry.register(_DummyTool("c", category="sandbox"))
        sandbox_tools = fresh_registry.list_all(category="sandbox")
        assert len(sandbox_tools) == 2
        assert all(t.category == "sandbox" for t in sandbox_tools)

    def test_by_tag(self, fresh_registry):
        fresh_registry.register(_DummyTool("a", tags=["safe", "read"]))
        fresh_registry.register(_DummyTool("b", tags=["safe"]))
        fresh_registry.register(_DummyTool("c", tags=["write"]))
        safe = fresh_registry.by_tag("safe")
        assert len(safe) == 2

    def test_search(self, fresh_registry):
        fresh_registry.register(_DummyTool("web_search", description="Search the web"))
        fresh_registry.register(_DummyTool("file_read", description="Read a file"))
        results = fresh_registry.search("web")
        assert len(results) == 1
        assert results[0].tool_id == "web_search"

    def test_unregister(self, fresh_registry):
        fresh_registry.register(_DummyTool("x"))
        assert fresh_registry.unregister("x") is True
        assert fresh_registry.get("x") is None
        assert fresh_registry.unregister("nonexistent") is False


# ── Scope filtering ────────────────────────────────────────────────────


class TestScopeFiltering:
    """Simulate the discover endpoint's scope filtering logic."""

    def test_no_scopes_always_passes(self):
        """Tools with empty required_scopes are public."""
        from app.api.v2.tools import _user_has_scopes

        user = MagicMock()
        user.is_superuser = False
        user.role = "user"
        user.scopes = []
        tool = _DummyTool("public_tool")
        assert _user_has_scopes(user, tool.metadata.required_scopes) is True

    def test_superuser_bypasses_scopes(self):
        from app.api.v2.tools import _user_has_scopes

        user = MagicMock()
        user.is_superuser = True
        assert _user_has_scopes(user, ["admin", "tools:write"]) is True

    def test_admin_role_bypasses_scopes(self):
        from app.api.v2.tools import _user_has_scopes

        user = MagicMock()
        user.is_superuser = False
        user.role = "admin"
        assert _user_has_scopes(user, ["anything"]) is True

    def test_user_with_matching_scopes(self):
        from app.api.v2.tools import _user_has_scopes

        user = MagicMock()
        user.is_superuser = False
        user.role = "user"
        user.scopes = ["tools:read", "tools:write"]
        assert _user_has_scopes(user, ["tools:read"]) is True
        assert _user_has_scopes(user, ["tools:read", "tools:write"]) is True

    def test_user_missing_scopes_denied(self):
        from app.api.v2.tools import _user_has_scopes

        user = MagicMock()
        user.is_superuser = False
        user.role = "user"
        user.scopes = ["tools:read"]
        assert _user_has_scopes(user, ["tools:read", "tools:write"]) is False


# ── _get_chat_openai_tools allowlist ───────────────────────────────────


class TestChatToolAllowlist:
    def test_allowlist_includes_expected_tools(self):
        """Verify the allowlist docstring mentions the Phase 1 tools."""
        from app.services.chat_service import _get_chat_openai_tools

        source = __import__("inspect").getsource(_get_chat_openai_tools)
        assert "web_search_enhanced" in source
        assert "rag_search" in source
        assert "memory_recall" in source
        assert "sandboxd_ids" in source

    def test_returns_none_when_no_tools_registered(self):
        """If registry is empty, returns None."""
        from app.services.chat_service import _get_chat_openai_tools

        with patch("app.services.chat_service.settings") as mock_settings:
            mock_settings.SANDBOXD_ENABLED = True
            with patch("app.tools.base.get_tool_registry") as mock_registry:
                mock_registry.return_value.list_all.return_value = []
                result = _get_chat_openai_tools()
                assert result is None


# ── _execute_tool_call scope denial ────────────────────────────────────


class TestExecuteToolCallScopeDenial:
    @pytest.mark.asyncio
    async def test_tool_with_scopes_denied_in_chat(self):
        """Tools with required_scopes are denied in chat context (Phase 1)."""
        from app.services.chat_service import _execute_tool_call

        tool = _DummyTool("restricted_tool", required_scopes=["admin"])
        registry = MagicMock()
        registry.get.return_value = tool

        with patch("app.tools.base.get_tool_registry", return_value=registry):
            result_json = await _execute_tool_call("restricted_tool", "{}", user_id=42)
            result = json.loads(result_json)
            assert "error" in result
            assert "capability denied" in result["error"]
            assert "restricted_tool" in result["error"]

    @pytest.mark.asyncio
    async def test_tool_without_scopes_passes(self):
        """Tools with empty required_scopes execute normally."""
        from app.services.chat_service import _execute_tool_call

        tool = _DummyTool("open_tool")
        registry = MagicMock()
        registry.get.return_value = tool

        with patch("app.tools.base.get_tool_registry", return_value=registry):
            result_json = await _execute_tool_call("open_tool", "{}", user_id=42)
            result = json.loads(result_json)
            assert "error" not in result
            assert result == {"echo": {}}

    @pytest.mark.asyncio
    async def test_unknown_tool_returns_error(self):
        from app.services.chat_service import _execute_tool_call

        registry = MagicMock()
        registry.get.return_value = None

        with patch("app.tools.base.get_tool_registry", return_value=registry):
            result_json = await _execute_tool_call("nonexistent", "{}")
            result = json.loads(result_json)
            assert "Unknown tool" in result["error"]

    @pytest.mark.asyncio
    async def test_invalid_json_returns_error(self):
        from app.services.chat_service import _execute_tool_call

        tool = _DummyTool("t")
        registry = MagicMock()
        registry.get.return_value = tool

        with patch("app.tools.base.get_tool_registry", return_value=registry):
            result_json = await _execute_tool_call("t", "not-json{{")
            result = json.loads(result_json)
            assert "Invalid JSON" in result["error"]


# ── Discovery endpoint (unit-level) ────────────────────────────────────


class TestDiscoveryEndpoint:
    def test_tool_metadata_serialization(self):
        """Verify tool metadata fields serialize correctly for the discover endpoint."""
        tool = _DummyTool(
            "my_tool",
            description="A test tool",
            category="test",
            tags=["alpha", "beta"],
            required_scopes=["tools:read"],
            requires_sandbox=True,
            rate_limit_key="test_group",
            timeout_seconds=45,
        )
        # Simulate what the discover endpoint builds
        entry = {
            "tool_id": tool.tool_id,
            "name": tool.name,
            "description": tool.description,
            "category": tool.category,
            "input_schema": tool.metadata.input_schema,
            "output_schema": tool.metadata.output_schema,
            "requires_auth": tool.metadata.requires_auth,
            "required_scopes": tool.metadata.required_scopes,
            "requires_sandbox": tool.metadata.requires_sandbox,
            "rate_limit_key": tool.metadata.rate_limit_key,
            "tags": tool.tags,
            "timeout_seconds": tool.metadata.timeout_seconds,
        }
        assert entry["required_scopes"] == ["tools:read"]
        assert entry["requires_sandbox"] is True
        assert entry["rate_limit_key"] == "test_group"
        assert entry["timeout_seconds"] == 45
        assert entry["requires_auth"] is True  # backwards compat


# ── Phase 2: _execute_tool_call scope resolution ──────────────────────


class TestExecuteToolCallScopeResolution:
    """Phase 2: verify _execute_tool_call uses cached user scopes correctly.

    The function now accepts ``_user_scopes`` and ``_user_role`` params.
    Three branches:
    1. Admin/owner role → bypass scope check entirely
    2. Cached scopes provided → check each required scope against the set
    3. No cached scopes → deny as defense-in-depth
    """

    @pytest.mark.asyncio
    async def test_admin_role_bypasses_scope_check(self):
        """Admin role should pass even with required_scopes and empty cached scopes."""
        from app.services.chat_service import _execute_tool_call

        tool = _DummyTool("restricted", required_scopes=["tools:admin"])
        registry = MagicMock()
        registry.get.return_value = tool

        with patch("app.tools.base.get_tool_registry", return_value=registry):
            result_json = await _execute_tool_call(
                "restricted",
                "{}",
                user_id=1,
                _user_scopes=set(),
                _user_role="admin",
            )
            result = json.loads(result_json)
            assert "error" not in result
            assert result == {"echo": {}}

    @pytest.mark.asyncio
    async def test_owner_role_bypasses_scope_check(self):
        """Owner role should pass even with required_scopes."""
        from app.services.chat_service import _execute_tool_call

        tool = _DummyTool("restricted", required_scopes=["tools:admin", "billing:write"])
        registry = MagicMock()
        registry.get.return_value = tool

        with patch("app.tools.base.get_tool_registry", return_value=registry):
            result_json = await _execute_tool_call(
                "restricted",
                "{}",
                user_id=1,
                _user_scopes=set(),
                _user_role="owner",
            )
            result = json.loads(result_json)
            assert "error" not in result
            assert result == {"echo": {}}

    @pytest.mark.asyncio
    async def test_user_with_matching_scopes_passes(self):
        """User with all required scopes should execute the tool."""
        from app.services.chat_service import _execute_tool_call

        tool = _DummyTool("scoped_tool", required_scopes=["tools:read"])
        registry = MagicMock()
        registry.get.return_value = tool

        with patch("app.tools.base.get_tool_registry", return_value=registry):
            result_json = await _execute_tool_call(
                "scoped_tool",
                "{}",
                user_id=42,
                _user_scopes={"tools:read", "tools:write"},
                _user_role="user",
            )
            result = json.loads(result_json)
            assert "error" not in result
            assert result == {"echo": {}}

    @pytest.mark.asyncio
    async def test_user_with_multiple_required_scopes_all_present(self):
        """User must hold ALL required scopes, not just some."""
        from app.services.chat_service import _execute_tool_call

        tool = _DummyTool("multi_scope", required_scopes=["tools:read", "tools:write"])
        registry = MagicMock()
        registry.get.return_value = tool

        with patch("app.tools.base.get_tool_registry", return_value=registry):
            result_json = await _execute_tool_call(
                "multi_scope",
                "{}",
                user_id=42,
                _user_scopes={"tools:read", "tools:write", "other"},
                _user_role="user",
            )
            result = json.loads(result_json)
            assert "error" not in result

    @pytest.mark.asyncio
    async def test_user_missing_scopes_denied_with_detail(self):
        """User missing some scopes gets denied with the missing scopes listed."""
        from app.services.chat_service import _execute_tool_call

        tool = _DummyTool("restricted", required_scopes=["tools:read", "tools:write", "admin"])
        registry = MagicMock()
        registry.get.return_value = tool

        with patch("app.tools.base.get_tool_registry", return_value=registry):
            result_json = await _execute_tool_call(
                "restricted",
                "{}",
                user_id=42,
                _user_scopes={"tools:read"},
                _user_role="user",
            )
            result = json.loads(result_json)
            assert "error" in result
            assert "capability denied" in result["error"]
            assert "missing" in result["error"]
            assert "tools:write" in result["error"]
            assert "admin" in result["error"]

    @pytest.mark.asyncio
    async def test_no_cached_scopes_denied_defense_in_depth(self):
        """When _user_scopes is None, deny tools with required_scopes."""
        from app.services.chat_service import _execute_tool_call

        tool = _DummyTool("restricted", required_scopes=["tools:admin"])
        registry = MagicMock()
        registry.get.return_value = tool

        with patch("app.tools.base.get_tool_registry", return_value=registry):
            result_json = await _execute_tool_call(
                "restricted",
                "{}",
                user_id=42,
                # _user_scopes not passed — defaults to None
            )
            result = json.loads(result_json)
            assert "error" in result
            assert "capability denied" in result["error"]
            assert "restricted" in result["error"]

    @pytest.mark.asyncio
    async def test_no_user_id_skips_scope_check(self):
        """When user_id is None, scope check is skipped entirely."""
        from app.services.chat_service import _execute_tool_call

        tool = _DummyTool("restricted", required_scopes=["tools:admin"])
        registry = MagicMock()
        registry.get.return_value = tool

        with patch("app.tools.base.get_tool_registry", return_value=registry):
            result_json = await _execute_tool_call(
                "restricted",
                "{}",
                user_id=None,
                _user_scopes=set(),
                _user_role="user",
            )
            result = json.loads(result_json)
            assert "error" not in result
            assert result == {"echo": {}}

    @pytest.mark.asyncio
    async def test_tool_without_scopes_passes_regardless(self):
        """Tools with empty required_scopes always pass, even with restricted user."""
        from app.services.chat_service import _execute_tool_call

        tool = _DummyTool("open_tool")  # no required_scopes
        registry = MagicMock()
        registry.get.return_value = tool

        with patch("app.tools.base.get_tool_registry", return_value=registry):
            result_json = await _execute_tool_call(
                "open_tool",
                "{}",
                user_id=42,
                _user_scopes=set(),
                _user_role="user",
            )
            result = json.loads(result_json)
            assert "error" not in result
            assert result == {"echo": {}}

    @pytest.mark.asyncio
    async def test_unknown_role_with_scopes_passes(self):
        """A non-admin role with correct scopes should still pass."""
        from app.services.chat_service import _execute_tool_call

        tool = _DummyTool("scoped", required_scopes=["tools:read"])
        registry = MagicMock()
        registry.get.return_value = tool

        with patch("app.tools.base.get_tool_registry", return_value=registry):
            result_json = await _execute_tool_call(
                "scoped",
                "{}",
                user_id=99,
                _user_scopes={"tools:read"},
                _user_role="editor",
            )
            result = json.loads(result_json)
            assert "error" not in result

    @pytest.mark.asyncio
    async def test_admin_with_none_scopes_still_passes(self):
        """Admin role bypasses even when _user_scopes is None (no DB lookup)."""
        from app.services.chat_service import _execute_tool_call

        tool = _DummyTool("restricted", required_scopes=["tools:admin"])
        registry = MagicMock()
        registry.get.return_value = tool

        with patch("app.tools.base.get_tool_registry", return_value=registry):
            result_json = await _execute_tool_call(
                "restricted",
                "{}",
                user_id=1,
                _user_role="admin",
                # _user_scopes not passed — defaults to None
            )
            result = json.loads(result_json)
            assert "error" not in result
            assert result == {"echo": {}}

    @pytest.mark.asyncio
    async def test_owner_with_none_scopes_still_passes(self):
        """Owner role bypasses even when _user_scopes is None."""
        from app.services.chat_service import _execute_tool_call

        tool = _DummyTool("restricted", required_scopes=["tools:admin"])
        registry = MagicMock()
        registry.get.return_value = tool

        with patch("app.tools.base.get_tool_registry", return_value=registry):
            result_json = await _execute_tool_call(
                "restricted",
                "{}",
                user_id=2,
                _user_role="owner",
            )
            result = json.loads(result_json)
            assert "error" not in result
            assert result == {"echo": {}}

    @pytest.mark.asyncio
    async def test_tool_execution_error_propagates(self):
        """If tool.execute() raises, the error is caught and returned as JSON."""
        from app.services.chat_service import _execute_tool_call

        tool = _DummyTool("failing")
        tool.execute = AsyncMock(side_effect=RuntimeError("boom"))
        registry = MagicMock()
        registry.get.return_value = tool

        with patch("app.tools.base.get_tool_registry", return_value=registry):
            result_json = await _execute_tool_call(
                "failing",
                "{}",
                user_id=1,
                _user_scopes=set(),
                _user_role="admin",
            )
            result = json.loads(result_json)
            assert "error" in result
            assert "boom" in result["error"]

    @pytest.mark.asyncio
    async def test_tool_failed_result_returns_error(self):
        """If tool.execute() returns a failed ToolResult, the error is returned."""
        from app.services.chat_service import _execute_tool_call

        tool = _DummyTool("fail_result")
        tool.execute = AsyncMock(return_value=ToolResult.error_result("fail_result", "permission denied"))
        registry = MagicMock()
        registry.get.return_value = tool

        with patch("app.tools.base.get_tool_registry", return_value=registry):
            result_json = await _execute_tool_call(
                "fail_result",
                "{}",
                user_id=1,
                _user_scopes=set(),
                _user_role="admin",
            )
            result = json.loads(result_json)
            assert result == {"error": "permission denied"}
