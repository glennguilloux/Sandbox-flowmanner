"""Tests for BYOK key injection and model selection in chat_service.py."""

import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch, call

os.environ.setdefault("OPENAI_API_KEY", "sk-test")


class FakeCompletion:
    """Minimal non-streaming completion response."""

    def __init__(self, content: str = "hello", tokens: int = 10):
        self.choices = [MagicMock(message=MagicMock(content=content))]
        self.usage = MagicMock(
            total_tokens=tokens, prompt_tokens=4, completion_tokens=tokens - 4
        )


class FakeChunk:
    def __init__(self, content: str):
        self.choices = [MagicMock(delta=MagicMock(content=content))]


@pytest.fixture()
def mock_db():
    """Async db session that returns a dummy ChatMessage on flush/refresh."""
    db = AsyncMock()
    msg = MagicMock()
    msg.id = 42
    db.flush = AsyncMock()
    db.refresh = AsyncMock()
    db.add = MagicMock()
    # execute returns a scalar result for count queries
    db.execute = AsyncMock(
        return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=msg))
    )
    return db


@pytest.mark.asyncio
async def test_default_key_path(mock_db):
    """send_message_to_llm uses env-var client when no user_api_key provided."""
    fake_response = FakeCompletion(content="world", tokens=8)

    with (
        patch("app.services.chat_service._client") as mock_client,
        patch(
            "app.services.chat_service.create_chat_message", new_callable=AsyncMock
        ) as mock_msg,
    ):
        mock_msg.return_value = MagicMock(id=1)
        mock_client.chat.completions.create = AsyncMock(return_value=fake_response)

        from app.services.chat_service import send_message_to_llm

        result = await send_message_to_llm(
            db=mock_db,
            thread_id=1,
            content="hi",
            user_id=99,
            user_api_key=None,
        )

    assert result["success"] is True
    assert result["content"] == "world"
    # The default shared client must have been used (not a per-request one)
    mock_client.chat.completions.create.assert_called_once()


@pytest.mark.asyncio
async def test_byok_key_injection(mock_db):
    """send_message_to_llm creates a NEW AsyncOpenAI client when user_api_key is supplied."""
    fake_response = FakeCompletion(content="byok response", tokens=12)

    with (
        patch("app.services.chat_service.AsyncOpenAI") as MockAsyncOpenAI,
        patch(
            "app.services.chat_service.create_chat_message", new_callable=AsyncMock
        ) as mock_msg,
    ):
        mock_msg.return_value = MagicMock(id=2)
        per_req_client = MagicMock()
        per_req_client.chat.completions.create = AsyncMock(return_value=fake_response)
        MockAsyncOpenAI.return_value = per_req_client

        from importlib import reload
        import app.services.chat_service as cs

        result = await cs.send_message_to_llm(
            db=mock_db,
            thread_id=1,
            content="test",
            user_id=7,
            user_api_key="sk-user-key-abc",
            model_id="gpt-4o",
        )

    assert result["success"] is True
    assert result["content"] == "byok response"
    # A per-request AsyncOpenAI must have been instantiated with the user key
    MockAsyncOpenAI.assert_called_once()
    init_kwargs = MockAsyncOpenAI.call_args.kwargs
    assert init_kwargs.get("api_key") == "sk-user-key-abc"


@pytest.mark.asyncio
async def test_byok_key_not_stored(mock_db):
    """Verify user_api_key is not persisted — it is only passed to the per-request client."""
    fake_response = FakeCompletion(content="ok", tokens=5)

    with (
        patch("app.services.chat_service.AsyncOpenAI") as MockAsyncOpenAI,
        patch(
            "app.services.chat_service.create_chat_message", new_callable=AsyncMock
        ) as mock_msg,
    ):
        mock_msg.return_value = MagicMock(id=3)
        per_req_client = MagicMock()
        per_req_client.chat.completions.create = AsyncMock(return_value=fake_response)
        MockAsyncOpenAI.return_value = per_req_client

        import app.services.chat_service as cs

        await cs.send_message_to_llm(
            db=mock_db,
            thread_id=1,
            content="store test",
            user_id=5,
            user_api_key="sk-sensitive-key",
        )

    # The module-level _client must NOT have been replaced or mutated
    import app.services.chat_service as cs2

    # _client is still the original env-var-based client, not the per-request one
    assert cs2._client is not per_req_client


@pytest.mark.asyncio
async def test_model_id_overrides_default(mock_db):
    """model_id parameter overrides the default LLM_MODEL_NAME."""
    fake_response = FakeCompletion(content="fine-tuned", tokens=6)

    with (
        patch("app.services.chat_service._client") as mock_client,
        patch(
            "app.services.chat_service.create_chat_message", new_callable=AsyncMock
        ) as mock_msg,
    ):
        mock_msg.return_value = MagicMock(id=4)
        mock_client.chat.completions.create = AsyncMock(return_value=fake_response)

        import app.services.chat_service as cs

        result = await cs.send_message_to_llm(
            db=mock_db,
            thread_id=1,
            content="test model override",
            user_id=1,
            model_id="gpt-3.5-turbo",
        )

    assert result["success"] is True
    # Verify the model passed to the API call was the override
    create_call_kwargs = mock_client.chat.completions.create.call_args.kwargs
    assert create_call_kwargs.get("model") == "gpt-3.5-turbo"


@pytest.mark.asyncio
async def test_stream_message_byok_creates_per_request_client(mock_db):
    """stream_message_to_llm creates a new AsyncOpenAI client when user_api_key is provided."""

    async def fake_stream():
        for char in ["hel", "lo"]:
            yield FakeChunk(char)

    fake_stream_response = MagicMock()
    fake_stream_response.__aiter__ = lambda self: fake_stream().__aiter__()

    with (
        patch("app.services.chat_service.AsyncOpenAI") as MockAsyncOpenAI,
        patch(
            "app.services.chat_service.create_chat_message", new_callable=AsyncMock
        ) as mock_msg,
    ):
        mock_msg.return_value = MagicMock(id=10)
        per_req_client = MagicMock()
        per_req_client.chat.completions.create = AsyncMock(
            return_value=fake_stream_response
        )
        MockAsyncOpenAI.return_value = per_req_client

        import app.services.chat_service as cs

        events = []
        async for event in cs.stream_message_to_llm(
            db=mock_db,
            thread_id=1,
            content="stream me",
            user_id=3,
            user_api_key="sk-proj-stream-key",
            model_id="openai/gpt-4o",
        ):
            events.append(event)

    MockAsyncOpenAI.assert_called_once()
    init_kwargs = MockAsyncOpenAI.call_args.kwargs
    assert init_kwargs.get("api_key") == "sk-proj-stream-key"

    import json

    token_events = [
        json.loads(e) for e in events if json.loads(e).get("type") == "token"
    ]
    assert len(token_events) == 2


@pytest.mark.asyncio
async def test_stream_message_default_path(mock_db):
    """stream_message_to_llm uses env-var _client when no user_api_key provided."""

    async def fake_stream():
        yield FakeChunk("hi")
        yield FakeChunk(" there")

    fake_stream_response = MagicMock()
    fake_stream_response.__aiter__ = lambda self: fake_stream().__aiter__()

    with (
        patch("app.services.chat_service._client") as mock_client,
        patch(
            "app.services.chat_service.create_chat_message", new_callable=AsyncMock
        ) as mock_msg,
    ):
        mock_msg.return_value = MagicMock(id=11)
        mock_client.chat.completions.create = AsyncMock(
            return_value=fake_stream_response
        )

        import app.services.chat_service as cs

        events = []
        async for event in cs.stream_message_to_llm(
            db=mock_db,
            thread_id=2,
            content="default stream",
            user_id=4,
            user_api_key=None,
        ):
            events.append(event)

    mock_client.chat.completions.create.assert_called_once()
    import json

    all_types = [json.loads(e)["type"] for e in events]
    assert "token" in all_types
    assert "complete" in all_types


class TestProviderDetection:
    """Tests for provider detection from API key prefixes."""

    def test_detect_sk_proj_is_openai(self):
        """Keys starting with sk-proj- should be detected as openai, not google."""
        from app.services.chat_service import _detect_provider_from_key

        result = _detect_provider_from_key("sk-proj-Vche123456789ABCDEFGHIJKLMNOP")
        assert result == "openai"

    def test_detect_sk_prefix_is_openai(self):
        """Keys starting with sk- should be detected as openai."""
        from app.services.chat_service import _detect_provider_from_key

        result = _detect_provider_from_key("sk-proj-test-key-12345")
        assert result == "openai"

    def test_detect_aiza_is_google(self):
        """Keys starting with AIza should be detected as google."""
        from app.services.chat_service import _detect_provider_from_key

        result = _detect_provider_from_key("AIzaSyABC123DEF456GHI789JKL012LMN345OPQ678")
        assert result == "google"

    def test_detect_sk_ant_is_anthropic(self):
        """Keys starting with sk-ant- should be detected as anthropic."""
        from app.services.chat_service import _detect_provider_from_key

        result = _detect_provider_from_key("sk-ant-api03AbCdEfGhIjKlMnOpQrStUvWx")
        assert result == "anthropic"

    def test_detect_sk_or_is_openrouter(self):
        """Keys starting with sk-or- should be detected as openrouter."""
        from app.services.chat_service import _detect_provider_from_key

        result = _detect_provider_from_key("sk-or-v1-abcdef123456789")
        assert result == "openrouter"

    def test_detect_sk_ds_is_deepseek(self):
        """Keys starting with sk-ds- should be detected as deepseek."""
        from app.services.chat_service import _detect_provider_from_key

        result = _detect_provider_from_key("sk-ds-abcdef123456789")
        assert result == "deepseek"

    def test_detect_unknown_key_returns_none(self):
        """Unknown key formats should return None (allowed for any provider)."""
        from app.services.chat_service import _detect_provider_from_key

        result = _detect_provider_from_key("vendor-custom-key-12345")
        assert result is None

    def test_detect_empty_key_returns_none(self):
        """Empty key should return None."""
        from app.services.chat_service import _detect_provider_from_key

        result = _detect_provider_from_key("")
        assert result is None

    def test_detect_none_key_returns_none(self):
        """None key should return None."""
        from app.services.chat_service import _detect_provider_from_key

        result = _detect_provider_from_key(None)
        assert result is None


class TestProviderMismatchValidation:
    """Tests for BYOK key vs model provider validation."""

    def test_openai_key_with_openai_model_valid(self):
        """OpenAI key should work with openai/* models."""
        from app.services.chat_service import _validate_byok_key_matches_model

        result = _validate_byok_key_matches_model("sk-proj-test-key", "openai/gpt-4o")
        assert result is None

    def test_openai_key_with_openai_compatible_model_valid(self):
        """OpenAI key should work with openai_compatible/* models."""
        from app.services.chat_service import _validate_byok_key_matches_model

        result = _validate_byok_key_matches_model(
            "sk-proj-Vche123", "openai_compatible/gpt-4o"
        )
        assert result is None

    def test_custom_vendor_key_with_openai_compatible_model_valid(self):
        """Unknown vendor keys should be allowed for openai_compatible/* models."""
        from app.services.chat_service import _validate_byok_key_matches_model

        result = _validate_byok_key_matches_model(
            "vendor-custom-key-123", "openai_compatible/gpt-4o"
        )
        assert result is None

    def test_google_key_with_openai_compatible_model_rejected(self):
        """Google key (AIza) should be rejected for openai_compatible/* models."""
        from app.services.chat_service import _validate_byok_key_matches_model

        result = _validate_byok_key_matches_model(
            "AIzaSyABC123", "openai_compatible/gpt-4o"
        )
        assert result is not None
        assert "mismatch" in result.lower()

    def test_anthropic_key_with_openai_compatible_model_rejected(self):
        """Anthropic key (sk-ant-) should be rejected for openai_compatible/* models."""
        from app.services.chat_service import _validate_byok_key_matches_model

        result = _validate_byok_key_matches_model(
            "sk-ant-api03", "openai_compatible/gpt-4o"
        )
        assert result is not None
        assert "mismatch" in result.lower()

    def test_google_key_with_google_model_valid(self):
        """Google key should work with google/* models."""
        from app.services.chat_service import _validate_byok_key_matches_model

        result = _validate_byok_key_matches_model("AIzaSyABC123", "google/gemini-pro")
        assert result is None

    def test_anthropic_key_with_anthropic_model_valid(self):
        """Anthropic key should work with anthropic/* models."""
        from app.services.chat_service import _validate_byok_key_matches_model

        result = _validate_byok_key_matches_model(
            "sk-ant-api03", "anthropic/claude-3-5-sonnet"
        )
        assert result is None

    def test_ollama_model_always_valid(self):
        """Any key should work with ollama/* models (keys ignored for ollama)."""
        from app.services.chat_service import _validate_byok_key_matches_model

        result = _validate_byok_key_matches_model(
            "sk-proj-test-key", "ollama/qwen2.5:latest"
        )
        assert result is None

    def test_openrouter_key_with_openrouter_model_valid(self):
        """OpenRouter key should work with openrouter/* models."""
        from app.services.chat_service import _validate_byok_key_matches_model

        result = _validate_byok_key_matches_model(
            "sk-or-v1-abc", "openrouter/anthropic/claude-3.5-sonnet"
        )
        assert result is None

    def test_deepseek_key_with_deepseek_model_valid(self):
        """DeepSeek key should work with deepseek/* models."""
        from app.services.chat_service import _validate_byok_key_matches_model

        result = _validate_byok_key_matches_model(
            "sk-ds-abc123", "deepseek/deepseek-chat"
        )
        assert result is None


class TestProviderNormalization:
    """Tests for provider name normalization."""

    def test_normalize_openai_compatible_underscore(self):
        """openai_compatible should normalize to openai_compatible."""
        from app.services.chat_service import _normalize_provider

        result = _normalize_provider("openai_compatible")
        assert result == "openai_compatible"

    def test_normalize_openai_compatible_hyphen(self):
        """openai-compatible should normalize to openai_compatible."""
        from app.services.chat_service import _normalize_provider

        result = _normalize_provider("openai-compatible")
        assert result == "openai_compatible"

    def test_normalize_openai(self):
        """openai should normalize to openai."""
        from app.services.chat_service import _normalize_provider

        result = _normalize_provider("openai")
        assert result == "openai"

    def test_normalize_openrouter(self):
        """openrouter should normalize to openrouter."""
        from app.services.chat_service import _normalize_provider

        result = _normalize_provider("openrouter")
        assert result == "openrouter"

    def test_normalize_empty(self):
        """Empty string should normalize to empty."""
        from app.services.chat_service import _normalize_provider

        result = _normalize_provider("")
        assert result == ""


class TestUpstreamModelNameExtraction:
    """Tests for extracting upstream model names from prefixed model IDs."""

    def test_openai_prefix_stripped(self):
        """Provider prefix should be stripped from openai/* models."""
        from app.services.chat_service import _get_upstream_model_name

        result = _get_upstream_model_name("openai/gpt-4o-mini")
        assert result == "gpt-4o-mini"

    def test_openai_compatible_prefix_stripped(self):
        """Provider prefix should be stripped from openai_compatible/* models."""
        from app.services.chat_service import _get_upstream_model_name

        result = _get_upstream_model_name("openai_compatible/gpt-4o-mini-2024-07-18")
        assert result == "gpt-4o-mini-2024-07-18"

    def test_openai_compatible_hyphen_prefix_stripped(self):
        """Provider prefix should be stripped from openai-compatible/* models."""
        from app.services.chat_service import _get_upstream_model_name

        result = _get_upstream_model_name("openai-compatible/gpt-4o-mini")
        assert result == "gpt-4o-mini"

    def test_openrouter_nested_prefix_preserved(self):
        """Nested provider path should be preserved for openrouter/* models."""
        from app.services.chat_service import _get_upstream_model_name

        result = _get_upstream_model_name("openrouter/anthropic/claude-3.5-sonnet")
        assert result == "anthropic/claude-3.5-sonnet"

    def test_deepseek_prefix_stripped(self):
        """Provider prefix should be stripped from deepseek/* models."""
        from app.services.chat_service import _get_upstream_model_name

        result = _get_upstream_model_name("deepseek/deepseek-chat")
        assert result == "deepseek-chat"

    def test_no_prefix_returns_unchanged(self):
        """Model without prefix should return unchanged."""
        from app.services.chat_service import _get_upstream_model_name

        result = _get_upstream_model_name("gpt-4o-mini")
        assert result == "gpt-4o-mini"


class TestProviderResolution:
    """Tests for full provider resolution."""

    def test_resolve_openai(self):
        """openai/gpt-4o-mini should resolve correctly."""
        from app.services.chat_service import _resolve_provider

        base_url, api_key, model = _resolve_provider("openai/gpt-4o-mini")
        assert base_url == "https://api.openai.com/v1"
        assert model == "gpt-4o-mini"

    def test_resolve_openai_compatible(self):
        """openai_compatible/gpt-4o-mini should resolve correctly."""
        from app.services.chat_service import _resolve_provider

        base_url, api_key, model = _resolve_provider("openai_compatible/gpt-4o-mini")
        assert base_url == "https://api.openai.com/v1"
        assert model == "gpt-4o-mini"

    def test_resolve_openai_compatible_with_version(self):
        """openai_compatible/gpt-4o-mini-2024-07-18 should resolve correctly."""
        from app.services.chat_service import _resolve_provider

        base_url, api_key, model = _resolve_provider(
            "openai_compatible/gpt-4o-mini-2024-07-18"
        )
        assert base_url == "https://api.openai.com/v1"
        assert model == "gpt-4o-mini-2024-07-18"

    def test_resolve_openrouter(self):
        """openrouter/anthropic/claude-3.5-sonnet should resolve correctly."""
        from app.services.chat_service import _resolve_provider

        base_url, api_key, model = _resolve_provider(
            "openrouter/anthropic/claude-3.5-sonnet"
        )
        assert base_url == "https://openrouter.ai/api/v1"
        assert model == "anthropic/claude-3.5-sonnet"

    def test_resolve_deepseek(self):
        """deepseek/deepseek-chat should resolve correctly."""
        from app.services.chat_service import _resolve_provider

        base_url, api_key, model = _resolve_provider("deepseek/deepseek-chat")
        assert base_url == "https://api.deepseek.com/v1"
        assert model == "deepseek-chat"

    def test_resolve_no_prefix(self):
        """Model without prefix should use default base URL."""
        from app.services.chat_service import _resolve_provider

        base_url, api_key, model = _resolve_provider("gpt-4o-mini")
        assert model == "gpt-4o-mini"


class TestAPIReceivesCorrectModelName:
    """Acceptance tests verifying the API receives the correct model name."""

    @pytest.mark.asyncio
    async def test_send_message_strips_openai_compatible_prefix(self, mock_db):
        """send_message_to_llm should send gpt-4o-mini-2024-07-18 to API, not openai_compatible/gpt-4o-mini-2024-07-18."""
        from app.services.chat_service import send_message_to_llm
        from unittest.mock import AsyncMock, MagicMock

        fake_response = MagicMock()
        fake_response.choices = [MagicMock(message=MagicMock(content="test response"))]
        fake_response.usage = MagicMock(
            total_tokens=10, prompt_tokens=4, completion_tokens=6
        )

        captured_model = None

        async def mock_create(**kwargs):
            nonlocal captured_model
            captured_model = kwargs.get("model")
            return fake_response

        with (
            patch("app.services.chat_service.AsyncOpenAI") as MockAsyncOpenAI,
            patch(
                "app.services.chat_service.create_chat_message", new_callable=AsyncMock
            ) as mock_msg,
        ):
            mock_msg.return_value = MagicMock(id=1)
            per_req_client = MagicMock()
            per_req_client.chat.completions.create = mock_create
            MockAsyncOpenAI.return_value = per_req_client

            result = await send_message_to_llm(
                db=mock_db,
                thread_id=1,
                content="test",
                user_id=1,
                user_api_key="sk-proj-test-key",
                model_id="openai_compatible/gpt-4o-mini-2024-07-18",
            )

        assert (
            captured_model == "gpt-4o-mini-2024-07-18"
        ), f"Expected 'gpt-4o-mini-2024-07-18', got '{captured_model}'"
        assert result["success"] is True
