"""Unit tests for PersistentAgentMemoryTool — the first P0 differentiator."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.tools.differentiators import (
    PersistentAgentMemoryTool,
    PersistentAgentMemoryInput,
)
from app.tools.base import ToolResult


class TestPersistentAgentMemoryInput:
    """Input schema validation tests."""

    def test_valid_save_input(self):
        data = {"action": "save", "content": "Hello, world!"}
        validated = PersistentAgentMemoryInput(**data)
        assert validated.action == "save"
        assert validated.content == "Hello, world!"
        assert validated.agent_id == "default"
        assert validated.limit == 10

    def test_valid_recall_input(self):
        data = {"action": "recall", "query": "world"}
        validated = PersistentAgentMemoryInput(**data)
        assert validated.action == "recall"
        assert validated.query == "world"

    def test_valid_list_input(self):
        data = {"action": "list", "agent_id": "agent-42", "limit": 5}
        validated = PersistentAgentMemoryInput(**data)
        assert validated.action == "list"
        assert validated.agent_id == "agent-42"
        assert validated.limit == 5

    def test_missing_action(self):
        with pytest.raises(Exception):
            PersistentAgentMemoryInput()

    def test_invalid_action(self):
        # The Field validates 'action' as any string, but the tool checks valid values
        validated = PersistentAgentMemoryInput(action="invalid")
        assert validated.action == "invalid"  # input layer passes, tool layer rejects

    def test_limit_bounds(self):
        # ge=1, le=100
        with pytest.raises(Exception):
            PersistentAgentMemoryInput(action="list", limit=0)
        with pytest.raises(Exception):
            PersistentAgentMemoryInput(action="list", limit=101)

    def test_extra_fields_ignored(self):
        """Context from API should be silently ignored."""
        data = {"action": "list", "context": {"user_id": "42"}, "extra": "stuff"}
        validated = PersistentAgentMemoryInput(**data)
        assert validated.action == "list"


class TestPersistentAgentMemoryTool:
    """Tool execution tests using mocked database sessions."""

    @pytest.fixture
    def tool(self):
        return PersistentAgentMemoryTool()

    @pytest.fixture
    def mock_session(self):
        session = AsyncMock()
        session.commit = AsyncMock()
        session.add = MagicMock()
        # execute returns a coroutine; when awaited, it yields a mock whose
        # .scalars().all() returns an empty list (overridable per-test)
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        session.execute = AsyncMock(return_value=mock_result)
        return session

    @pytest.mark.asyncio
    async def test_save_success(self, tool, mock_session):
        with patch("app.tools.differentiators.AsyncSessionLocal") as mock_factory:
            mock_factory.return_value.__aenter__.return_value = mock_session
            result = await tool.execute(
                {
                    "action": "save",
                    "content": "Memory alpha",
                    "agent_id": "test-agent",
                    "content_type": "summary",
                }
            )

        assert result.success is True
        assert result.result["action"] == "save"
        assert result.result["content_type"] == "summary"
        assert result.result["agent_id"] == "test-agent"
        assert "id" in result.result
        mock_session.add.assert_called_once()
        mock_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_save_missing_content(self, tool):
        """Save without content should return error."""
        result = await tool.execute({"action": "save"})
        assert result.success is False
        assert "content is required" in result.error

    @pytest.mark.asyncio
    async def test_save_with_user_context(self, tool, mock_session):
        """User_id from API context should be resolved."""
        with patch("app.tools.differentiators.AsyncSessionLocal") as mock_factory:
            mock_factory.return_value.__aenter__.return_value = mock_session
            result = await tool.execute(
                {
                    "action": "save",
                    "content": "From context",
                    "context": {"user_id": "99"},
                }
            )

        assert result.success is True
        mock_session.add.assert_called_once()
        # Verify user_id=99 was passed to AgentMemory
        call_args = mock_session.add.call_args[0][0]
        assert call_args.user_id == 99

    @pytest.mark.asyncio
    async def test_save_with_explicit_user_id(self, tool, mock_session):
        """Explicit user_id should take priority over context."""
        with patch("app.tools.differentiators.AsyncSessionLocal") as mock_factory:
            mock_factory.return_value.__aenter__.return_value = mock_session
            result = await tool.execute(
                {
                    "action": "save",
                    "content": "Explicit user",
                    "user_id": 42,
                    "context": {"user_id": "99"},
                }
            )

        assert result.success is True
        call_args = mock_session.add.call_args[0][0]
        assert call_args.user_id == 42  # explicit overrides context

    @pytest.mark.asyncio
    async def test_recall_success(self, tool, mock_session):
        with patch("app.tools.differentiators.AsyncSessionLocal") as mock_factory:
            mock_factory.return_value.__aenter__.return_value = mock_session
            result = await tool.execute(
                {
                    "action": "recall",
                    "query": "alpha",
                    "agent_id": "test-agent",
                }
            )

        assert result.success is True
        assert result.result["action"] == "recall"
        assert result.result["query"] == "alpha"
        assert isinstance(result.result["results"], list)
        assert result.result["results"] == []
        mock_session.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_recall_fallback_user_id(self, tool, mock_session):
        """Recall with no user_id and no context should query with user_id=0."""
        with patch("app.tools.differentiators.AsyncSessionLocal") as mock_factory:
            mock_factory.return_value.__aenter__.return_value = mock_session
            await tool.execute(
                {
                    "action": "recall",
                    "query": "test",
                    "agent_id": "agent-1",
                }
            )

        # Verify the statement includes user_id == 0 filter
        call_args = mock_session.execute.call_args[0][0]
        where_clause = str(call_args)
        assert "agent_memory.user_id = :user_id_1" in where_clause

    @pytest.mark.asyncio
    async def test_recall_missing_query(self, tool):
        """Recall without query should return error."""
        result = await tool.execute({"action": "recall"})
        assert result.success is False
        assert "query is required" in result.error

    @pytest.mark.asyncio
    async def test_list_success(self, tool, mock_session):
        with patch("app.tools.differentiators.AsyncSessionLocal") as mock_factory:
            mock_factory.return_value.__aenter__.return_value = mock_session
            result = await tool.execute(
                {
                    "action": "list",
                    "agent_id": "test-agent",
                    "limit": 5,
                }
            )

        assert result.success is True
        assert result.result["action"] == "list"
        assert result.result["agent_id"] == "test-agent"
        assert result.result["count"] == 0
        assert isinstance(result.result["results"], list)
        assert result.result["results"] == []
        mock_session.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_unknown_action(self, tool):
        result = await tool.execute({"action": "delete"})
        assert result.success is False
        assert "Unknown action" in result.error

    @pytest.mark.asyncio
    async def test_invalid_user_id(self, tool):
        """Non-integer user_id in context should fail gracefully."""
        result = await tool.execute(
            {
                "action": "list",
                "context": {"user_id": "not-a-number"},
            }
        )
        assert result.success is False
        assert "Invalid user_id" in result.error

    @pytest.mark.asyncio
    async def test_db_error_graceful(self, tool, mock_session):
        """Database errors should be caught and returned as errors."""
        mock_session.commit.side_effect = RuntimeError("DB connection lost")

        with patch("app.tools.differentiators.AsyncSessionLocal") as mock_factory:
            mock_factory.return_value.__aenter__.return_value = mock_session
            result = await tool.execute(
                {
                    "action": "save",
                    "content": "test",
                }
            )

        assert result.success is False
        assert "DB connection lost" in result.error
