"""Tests for PromptSynthesizer — mock retrieval + LLM."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.rag.prompt_synthesizer import (
    GeneratedPrompt,
    PromptSynthesizer,
)
from app.services.rag.retrieval_service import RetrievedChunk


@pytest.fixture
def mock_retrieval_service():
    rs = MagicMock()
    rs.retrieve = AsyncMock()
    return rs


@pytest.fixture
def mock_llm_router():
    router = MagicMock()
    router.route_request = AsyncMock()
    return router


def make_chunk(
    idx: int,
    text: str = "a chunk of text",
    book_title: str = "Test Book",
    topics: list[str] | None = None,
    score: float = 0.9,
) -> RetrievedChunk:
    return RetrievedChunk(
        id=str(idx),
        book_title=book_title,
        text=text,
        topics=topics or ["role_definition"],
        relevance_score=0.8,
        chunk_index=idx,
        score=score,
    )


class TestPromptSynthesizer:
    """Unit tests for PromptSynthesizer.synthesize()."""

    @pytest.fixture
    def synthesizer(self, mock_retrieval_service, mock_llm_router):
        return PromptSynthesizer(
            retrieval_service=mock_retrieval_service,
            llm_router=mock_llm_router,
        )

    @pytest.mark.asyncio
    async def test_empty_retrieval_returns_error_prompt(
        self, synthesizer, mock_retrieval_service
    ):
        """When no chunks found, returns GeneratedPrompt with empty system_prompt and error rationale."""
        mock_retrieval_service.retrieve.return_value = []
        result = await synthesizer.synthesize(user_id=1, goal="build a chatbot")
        assert isinstance(result, GeneratedPrompt)
        assert result.system_prompt == ""
        assert "error" in result.rationale
        assert "No relevant book notes" in result.rationale["error"][0]

    @pytest.mark.asyncio
    async def test_successful_synthesis_returns_parsed_prompt(
        self, synthesizer, mock_retrieval_service, mock_llm_router
    ):
        """Full pipeline returns a parsed GeneratedPrompt from LLM response."""
        mock_retrieval_service.retrieve.return_value = [
            make_chunk(1, "You are a helpful assistant.", topics=["role_definition"]),
        ]

        llm_response = (
            "## System Prompt\n"
            "You are a customer support agent.\n"
            "\n"
            "## Rationale\n"
            "- role_definition: used the assistance framing from Test Book\n"
            "\n"
            "## Configuration\n"
            "- Recommended model: gpt-4o\n"
            "- Temperature: 0.5\n"
        )
        mock_llm_router.route_request.return_value = {
            "response": llm_response,
            "usage": {"prompt_tokens": 50, "completion_tokens": 30},
        }

        result = await synthesizer.synthesize(
            user_id=1,
            goal="customer support bot",
            role_description="You handle tickets",
            topics=["role_definition"],
        )

        assert result.system_prompt == "You are a customer support agent."
        assert "general" in result.rationale
        assert any("role_definition" in item for item in result.rationale["general"])
        assert result.recommended_model == "gpt-4o"
        assert result.temperature == 0.5
        assert result.usage == {"prompt_tokens": 50, "completion_tokens": 30}

    @pytest.mark.asyncio
    async def test_synthesis_without_role_description(
        self, synthesizer, mock_retrieval_service, mock_llm_router
    ):
        """role_description is optional and doesn't break the pipeline."""
        mock_retrieval_service.retrieve.return_value = [
            make_chunk(1, "Always be concise.", topics=["constraints"]),
        ]
        mock_llm_router.route_request.return_value = {
            "response": "## System Prompt\nBe concise.\n\n## Rationale\n\n## Configuration\n- Recommended model: deepseek/deepseek-v4-flash\n- Temperature: 0.7\n"
        }
        result = await synthesizer.synthesize(user_id=1, goal="be concise")
        assert result.system_prompt == "Be concise."

    @pytest.mark.asyncio
    async def test_single_book_passed_to_retrieval(
        self, synthesizer, mock_retrieval_service, mock_llm_router
    ):
        """When a single book is specified, it's forwarded as book_title to retrieval."""
        mock_retrieval_service.retrieve.return_value = []
        mock_llm_router.route_request.return_value = {
            "response": "## System Prompt\n\n## Rationale\n\n## Configuration\n- Recommended model: deepseek/deepseek-v4-flash\n- Temperature: 0.7\n"
        }
        await synthesizer.synthesize(user_id=1, goal="test", books=["My Prompt Book"])
        mock_retrieval_service.retrieve.assert_called_once()
        _kwargs = mock_retrieval_service.retrieve.call_args.kwargs
        assert _kwargs["book_title"] == "My Prompt Book"

    @pytest.mark.asyncio
    async def test_multiple_books_does_not_pass_title(
        self, synthesizer, mock_retrieval_service, mock_llm_router
    ):
        """When multiple books are specified, book_title is None (search all)."""
        mock_retrieval_service.retrieve.return_value = []
        mock_llm_router.route_request.return_value = {
            "response": "## System Prompt\n\n## Rationale\n\n## Configuration\n- Recommended model: deepseek/deepseek-v4-flash\n- Temperature: 0.7\n"
        }
        await synthesizer.synthesize(user_id=1, goal="test", books=["Book A", "Book B"])
        _kwargs = mock_retrieval_service.retrieve.call_args.kwargs
        assert _kwargs["book_title"] is None

    @pytest.mark.asyncio
    async def test_usage_dict_carried_through(
        self, synthesizer, mock_retrieval_service, mock_llm_router
    ):
        """LLM usage stats are included in the output."""
        mock_retrieval_service.retrieve.return_value = [
            make_chunk(1, "test", topics=["role_definition"]),
        ]
        mock_llm_router.route_request.return_value = {
            "response": "## System Prompt\nHi\n\n## Rationale\n\n## Configuration\n- Recommended model: deepseek/deepseek-v4-flash\n- Temperature: 0.7\n",
            "usage": {
                "prompt_tokens": 100,
                "completion_tokens": 50,
                "total_tokens": 150,
            },
        }
        result = await synthesizer.synthesize(user_id=1, goal="test")
        assert result.usage == {
            "prompt_tokens": 100,
            "completion_tokens": 50,
            "total_tokens": 150,
        }


class TestGroupChunksByTopic:
    """Direct tests for _group_chunks_by_topic()."""

    def test_empty_chunks(self):
        svc = PromptSynthesizer(MagicMock(), MagicMock())
        result = svc._group_chunks_by_topic([])
        assert result == "No relevant excerpts found."

    def test_single_chunk_single_topic(self):
        svc = PromptSynthesizer(MagicMock(), MagicMock())
        chunks = [make_chunk(1, "You are a bot.", topics=["role_definition"])]
        result = svc._group_chunks_by_topic(chunks)
        assert "Role Definition" in result
        assert "You are a bot." in result
        assert "Test Book" in result

    def test_chunks_with_multiple_topics_appear_once(self):
        """A chunk with two topics appears under both topic sections."""
        svc = PromptSynthesizer(MagicMock(), MagicMock())
        chunks = [
            make_chunk(1, "Do not be rude.", topics=["constraints", "evaluation"]),
        ]
        result = svc._group_chunks_by_topic(chunks)
        assert "Constraints" in result
        assert "Evaluation" in result
        assert "Do not be rude." in result

    def test_topic_order_follows_section_order(self):
        """Topics appear in _SECTION_ORDER, not arbitrary."""
        svc = PromptSynthesizer(MagicMock(), MagicMock())
        chunks = [
            make_chunk(1, "Eval text.", topics=["evaluation"]),
            make_chunk(2, "Role text.", topics=["role_definition"]),
            make_chunk(3, "Output text.", topics=["output_format"]),
        ]
        result = svc._group_chunks_by_topic(chunks)
        # Role should come before output before evaluation
        role_idx = result.index("Role Definition")
        output_idx = result.index("Output Format")
        eval_idx = result.index("Evaluation")
        assert role_idx < output_idx < eval_idx


class TestParseResponse:
    """Direct tests for _parse_response()."""

    def test_full_response_parsed(self):
        content = (
            "## System Prompt\n"
            "You are a helpful AI.\n"
            "\n"
            "## Rationale\n"
            "- role_definition: from Test Book\n"
            "- constraints: from Other Book\n"
            "\n"
            "## Configuration\n"
            "- Recommended model: claude-sonnet-4\n"
            "- Temperature: 0.3\n"
        )
        result = PromptSynthesizer._parse_response(content)
        assert result.system_prompt == "You are a helpful AI."
        assert "general" in result.rationale
        assert any("role_definition" in item for item in result.rationale["general"])
        assert any("constraints" in item for item in result.rationale["general"])
        assert result.recommended_model == "claude-sonnet-4"
        assert result.temperature == 0.3

    def test_no_system_prompt_section(self):
        content = "Some random text without sections"
        result = PromptSynthesizer._parse_response(content)
        assert result.system_prompt == ""
        assert result.recommended_model == "deepseek/deepseek-v4-flash"
        assert result.temperature == 0.7

    def test_malformed_temperature_falls_back(self):
        content = (
            "## System Prompt\nHi\n\n"
            "## Rationale\n\n"
            "## Configuration\n- Temperature: not-a-number\n"
        )
        result = PromptSynthesizer._parse_response(content)
        assert result.temperature == 0.7

    def test_empty_content(self):
        result = PromptSynthesizer._parse_response("")
        assert result.system_prompt == ""
        assert result.rationale == {}
        assert result.recommended_model == "deepseek/deepseek-v4-flash"
        assert result.temperature == 0.7


class TestBuildSynthesisPrompt:
    """Direct tests for _build_synthesis_prompt()."""

    def test_without_role(self):
        prompt = PromptSynthesizer._build_synthesis_prompt(
            goal="build a chatbot",
            role_description=None,
            grouped_chunks="### Role Definition\n- Be helpful",
        )
        assert "build a chatbot" in prompt
        assert "Role:" not in prompt or "Role:" not in prompt.split("Goal:")
        # Actually check Role is not in the prompt
        assert "Role:" not in prompt

    def test_with_role(self):
        prompt = PromptSynthesizer._build_synthesis_prompt(
            goal="build a chatbot",
            role_description="customer support",
            grouped_chunks="### Role Definition\n- Be helpful",
        )
        assert "Goal: build a chatbot" in prompt
        assert "Role: customer support" in prompt

    def test_format_instructions_present(self):
        prompt = PromptSynthesizer._build_synthesis_prompt(
            goal="x",
            role_description=None,
            grouped_chunks="content",
        )
        assert "## System Prompt" in prompt
        assert "## Rationale" in prompt
        assert "## Configuration" in prompt
