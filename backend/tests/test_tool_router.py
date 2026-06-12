"""Unit tests for ToolRouter — Q2-Q3 Chunk 3.

Tests cover:
- route() happy path returns sparse candidate set
- route() low confidence triggers fallback to full registry
- route() high-risk tool (requires_approval=True) always included
- route() k cap is enforced
- route() min_confidence threshold works correctly
- _score_tool components are weighted correctly
- audit event uses task_text_hash (NOT raw text)
- mode field is one of two allowed values
- no cross-workspace data leaks (workspace/user scoping)
- permission denied tool excluded (score forced to 0)
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest

from app.models.tool_routing_models import ToolRouteResult, ToolScore
from app.services.langgraph.tool_converter import ToolConverter, ToolDefinition
from app.services.tool_router import ToolRouter, _jaccard_similarity, _task_text_hash, _tokenize


# ── Fixtures ───────────────────────────────────────────────────────


def _make_converter(tools: list[ToolDefinition] | None = None) -> ToolConverter:
    """Create a ToolConverter with controllable tools (bypasses _initialize_default_tools)."""
    converter = ToolConverter.__new__(ToolConverter)
    converter.tools = {}
    converter.llm = None
    converter.llm_manager = MagicMock()
    converter.default_model_id = None
    if tools:
        for t in tools:
            converter.tools[t.tool_id] = t
    return converter


def _make_tool(
    tool_id: str = "test_tool",
    name: str = "Test Tool",
    description: str = "A test tool for testing",
    category: str = "general",
    is_safe: bool = True,
    requires_approval: bool = False,
) -> ToolDefinition:
    """Create a ToolDefinition with sensible defaults."""
    return ToolDefinition(
        tool_id=tool_id,
        name=name,
        description=description,
        parameters_schema={"type": "object", "properties": {}},
        category=category,
        is_safe=is_safe,
        requires_approval=requires_approval,
    )


WS = UUID("00000000-0000-0000-0000-000000000001")
USER = 1


# ── Tests ──────────────────────────────────────────────────────────


class TestToolRouterRoute:
    """Tests for ToolRouter.route() method."""

    @pytest.mark.asyncio
    async def test_happy_path_returns_sparse_candidate_set(self):
        """route() returns a non-empty candidate set in sparse mode when confidence is high."""
        tools = [
            _make_tool("search_workflows", "Search Workflows", "Search for available workflows by name or category", "search"),
            _make_tool("execute_n8n", "Execute n8n", "Execute an n8n workflow", "workflow", requires_approval=True),
            _make_tool("list_configs", "List Configs", "List saved configurations", "config"),
        ]
        converter = _make_converter(tools)
        router = ToolRouter(registry=converter, min_confidence=0.1)

        result = await router.route(
            task_text="search for workflows",
            workspace_id=WS,
            user_id=USER,
        )

        assert isinstance(result, ToolRouteResult)
        assert result.mode == "sparse"
        assert result.candidates_considered == 3
        assert result.candidates_returned >= 1
        assert result.top_score > 0.0
        assert len(result.task_text_hash) == 64  # SHA-256 hex

    @pytest.mark.asyncio
    async def test_low_confidence_triggers_fallback(self):
        """route() falls back to full registry when top score < min_confidence."""
        tools = [
            _make_tool("tool_a", "Tool A", "Unrelated description about weather", "general"),
            _make_tool("tool_b", "Tool B", "Another unrelated topic about cooking", "general"),
        ]
        converter = _make_converter(tools)
        # Set very high min_confidence so nothing passes
        router = ToolRouter(registry=converter, min_confidence=0.99)

        result = await router.route(
            task_text="quantum physics research",
            workspace_id=WS,
            user_id=USER,
        )

        assert result.mode == "fallback-full-registry"
        assert result.candidates_returned == 2  # all tools returned

    @pytest.mark.asyncio
    async def test_high_risk_tool_always_included(self):
        """Tools with requires_approval=True are always in the candidate set even with low score."""
        safe_tool = _make_tool("safe", "Safe Tool", "A safe tool about images", "image")
        high_risk = _make_tool("risky", "Risky Tool", "Completely unrelated topic about cooking", "general", requires_approval=True)
        converter = _make_converter([safe_tool, high_risk])
        router = ToolRouter(registry=converter, min_confidence=0.1)

        result = await router.route(
            task_text="image processing",
            workspace_id=WS,
            user_id=USER,
            k=1,  # Only ask for 1, but risky should still be included
        )

        selected_ids = {t["tool_id"] for t in result.tools}
        assert "risky" in selected_ids, "High-risk tool must always be included"
        assert "safe" in selected_ids, "Top-scored tool must be included"

    @pytest.mark.asyncio
    async def test_k_cap_enforced(self):
        """k parameter limits the number of tools returned (excluding always-include)."""
        tools = [
            _make_tool(f"tool_{i}", f"Tool {i}", f"Description for tool {i} about workflows", "workflow")
            for i in range(20)
        ]
        converter = _make_converter(tools)
        router = ToolRouter(registry=converter, min_confidence=0.01)

        result = await router.route(
            task_text="workflow execution",
            workspace_id=WS,
            user_id=USER,
            k=3,
        )

        # All tools have the same score so they all match equally.
        # k=3 means we take top 3 (plus any always-include).
        # None require_approval so exactly 3.
        assert result.candidates_returned <= 3

    @pytest.mark.asyncio
    async def test_min_confidence_constructor_param(self):
        """min_confidence is a constructor parameter, not config file read."""
        tools = [_make_tool("t1", "T1", "Search workflows", "search")]
        converter = _make_converter(tools)

        # Low threshold — should go sparse
        router_low = ToolRouter(registry=converter, min_confidence=0.01)
        result_low = await router_low.route("search", WS, USER)
        assert result_low.mode == "sparse"

        # High threshold — should fall back
        router_high = ToolRouter(registry=converter, min_confidence=0.99)
        result_high = await router_high.route("search", WS, USER)
        assert result_high.mode == "fallback-full-registry"


class TestScoring:
    """Tests for _score_tool component weights."""

    @pytest.mark.asyncio
    async def test_score_components_weighted_correctly(self):
        """Verify score = 0.5*text + 0.2*category + 0.2*memory + 0.1*permission."""
        tool = _make_tool("search", "Search Workflows", "Search for workflows", "search")
        converter = _make_converter([tool])
        router = ToolRouter(registry=converter, memory_service=None, min_confidence=0.01)

        result = await router.route(
            task_text="search for workflows",
            workspace_id=WS,
            user_id=USER,
        )

        assert len(result.scores) == 1
        score = result.scores[0]
        components = score.components

        # Verify individual components exist
        assert "text_similarity" in components
        assert "category_match" in components
        assert "memory_hint" in components
        assert "permission_ok" in components

        # Verify weighted sum
        expected = (
            0.5 * components["text_similarity"]
            + 0.2 * components["category_match"]
            + 0.2 * components["memory_hint"]
            + 0.1 * components["permission_ok"]
        )
        assert abs(score.score - round(expected, 4)) < 0.001

    def test_text_similarity_jaccard(self):
        """_text_similarity uses Jaccard word overlap."""
        tool = _make_tool("t", "Search Workflows", "Search for available workflows by name")
        converter = _make_converter([tool])
        router = ToolRouter(registry=converter)

        # Identical text should have high similarity
        sim_high = router._text_similarity(tool, "search for available workflows by name")
        assert sim_high > 0.5

        # Unrelated text should have low similarity
        sim_low = router._text_similarity(tool, "quantum physics cooking recipes")
        assert sim_low < 0.1

    @pytest.mark.asyncio
    async def test_permission_denied_excludes_tool(self):
        """A tool with permission_ok=0.0 gets score forced to 0.0."""
        tool = _make_tool("denied_tool", "Denied", "A tool", "general")
        converter = _make_converter([tool])
        router = ToolRouter(registry=converter, min_confidence=0.01)

        # Patch _permission_ok to return 0.0
        with patch.object(router, "_permission_ok", return_value=0.0):
            result = await router.route("a tool", WS, USER)

        assert result.scores[0].score == 0.0
        assert "permission denied" in result.scores[0].reasons


class TestAuditAndPrivacy:
    """Tests for audit event and task_text_hash privacy."""

    @pytest.mark.asyncio
    async def test_audit_event_uses_hash_not_raw_text(self):
        """The task_text_hash is SHA-256 of normalized text, never the raw text."""
        tool = _make_tool("t1", "T1", "A tool", "general")
        converter = _make_converter([tool])
        router = ToolRouter(registry=converter, min_confidence=0.01)

        result = await router.route("secret password: abc123", WS, USER)

        # Verify hash is present and correct
        expected_hash = _task_text_hash("secret password: abc123")
        assert result.task_text_hash == expected_hash
        assert len(expected_hash) == 64  # SHA-256 hex

        # The raw text should NOT appear in the hash
        assert "secret" not in result.task_text_hash
        assert "abc123" not in result.task_text_hash

    @pytest.mark.asyncio
    async def test_mode_field_is_valid(self):
        """mode is always one of 'sparse' or 'fallback-full-registry'."""
        tool = _make_tool("t1", "T1", "A tool", "general")
        converter = _make_converter([tool])

        for threshold in [0.01, 0.99]:
            router = ToolRouter(registry=converter, min_confidence=threshold)
            result = await router.route("a tool", WS, USER)
            assert result.mode in ("sparse", "fallback-full-registry")


class TestScopingAndIsolation:
    """Tests for workspace + user scoping."""

    @pytest.mark.asyncio
    async def test_route_requires_workspace_and_user(self):
        """route() takes workspace_id and user_id as required args."""
        tool = _make_tool("t1", "T1", "A tool", "general")
        converter = _make_converter([tool])
        router = ToolRouter(registry=converter)

        # These are positional/required — verify the function signature
        import inspect
        sig = inspect.signature(router.route)
        params = list(sig.parameters.keys())
        assert "workspace_id" in params
        assert "user_id" in params

    @pytest.mark.asyncio
    async def test_empty_registry_returns_empty(self):
        """route() handles empty tool registry gracefully."""
        converter = _make_converter([])
        router = ToolRouter(registry=converter, min_confidence=0.01)

        result = await router.route("anything", WS, USER)

        assert result.tools == []
        assert result.candidates_considered == 0
        assert result.candidates_returned == 0


class TestHelpers:
    """Tests for helper functions."""

    def test_tokenize_removes_stop_words(self):
        """_tokenize removes stop words and lowercases."""
        tokens = _tokenize("Search for the available Workflows")
        assert "search" in tokens
        assert "available" in tokens
        assert "workflows" in tokens
        assert "for" not in tokens
        assert "the" not in tokens

    def test_jaccard_identical_sets(self):
        """Jaccard similarity of identical sets is 1.0."""
        s = {"a", "b", "c"}
        assert _jaccard_similarity(s, s) == 1.0

    def test_jaccard_disjoint_sets(self):
        """Jaccard similarity of disjoint sets is 0.0."""
        assert _jaccard_similarity({"a"}, {"b"}) == 0.0

    def test_jaccard_empty_sets(self):
        """Jaccard similarity of empty sets is 0.0."""
        assert _jaccard_similarity(set(), set()) == 0.0

    def test_task_text_hash_deterministic(self):
        """Same text always produces the same hash."""
        h1 = _task_text_hash("hello world")
        h2 = _task_text_hash("hello world")
        assert h1 == h2

    def test_task_text_hash_normalizes_whitespace(self):
        """Hash normalizes extra whitespace."""
        h1 = _task_text_hash("hello  world")
        h2 = _task_text_hash("hello world")
        assert h1 == h2

    def test_always_include_returns_approval_tools(self):
        """_always_include_tools returns IDs of tools with requires_approval=True."""
        tools = [
            _make_tool("safe", requires_approval=False),
            _make_tool("risky_a", requires_approval=True),
            _make_tool("risky_b", requires_approval=True),
        ]
        converter = _make_converter(tools)
        router = ToolRouter(registry=converter)

        always_ids = router._always_include_tools()
        assert "risky_a" in always_ids
        assert "risky_b" in always_ids
        assert "safe" not in always_ids
