"""Tests for BYOK key injection and model selection in chat_service.py."""

import os
import socket
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

os.environ.setdefault("OPENAI_API_KEY", "sk-test")


def _redis_reachable() -> bool:
    """Best-effort check for a reachable Redis (Celery backend).

    ``send_message_to_llm`` is a full integration path: it records tool cost
    via a Celery/Redis fire-and-forget call after the LLM response. Without a
    reachable Redis the call enters Celery's 20-retry backoff (~100s) and the
    test hangs. Skip these integration tests when Redis isn't up so the suite
    stays green in offline/sandboxed environments while still running in CI.
    """
    url = os.environ.get("REDIS_URL") or os.environ.get("CELERY_BROKER_URL") or ""
    if not url:
        return False
    try:
        # redis://[:pass@]host:port[/db] -> connect to host:port quickly
        from urllib.parse import urlparse

        parsed = urlparse(url)
        host = parsed.hostname or "localhost"
        port = parsed.port or 6379
        with socket.create_connection((host, port), timeout=1.0):
            return True
    except OSError:
        return False


requires_redis = pytest.mark.skipif(
    not _redis_reachable(),
    reason="Redis/Celery backend unreachable — integration test skipped in offline sandbox",
)


class FakeCompletion:
    """Minimal non-streaming completion response."""

    def __init__(self, content: str = "hello", tokens: int = 10):
        self.choices = [MagicMock(message=MagicMock(content=content, tool_calls=None))]
        self.usage = MagicMock(total_tokens=tokens, prompt_tokens=4, completion_tokens=tokens - 4)


class FakeChunk:
    def __init__(self, content: str):
        self.choices = [MagicMock(delta=MagicMock(content=content))]


@pytest.fixture
def mock_db():
    """Async db session that returns a dummy ChatMessage on flush/refresh."""
    db = AsyncMock()
    msg = MagicMock()
    msg.id = 42
    db.flush = AsyncMock()
    db.refresh = AsyncMock()
    db.add = MagicMock()
    # execute returns a scalar result for count queries
    db.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=msg)))
    return db


@requires_redis
@pytest.mark.asyncio
async def test_default_key_path(mock_db):
    """send_message_to_llm uses env-var client when no user_api_key provided."""
    fake_response = FakeCompletion(content="world", tokens=8)

    with (
        patch("app.services.chat_service._client") as mock_client,
        patch("app.services.chat_service.AsyncOpenAI") as MockAsyncOpenAI,
        patch("app.services.chat_service.create_chat_message", new_callable=AsyncMock) as mock_msg,
    ):
        mock_msg.return_value = MagicMock(id=1)
        mock_client.chat.completions.create = AsyncMock(return_value=fake_response)
        # Make sure even if a new AsyncOpenAI is created, its create returns the same mock
        new_client = MagicMock()
        new_client.chat.completions.create = mock_client.chat.completions.create
        MockAsyncOpenAI.return_value = new_client

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


@requires_redis
@pytest.mark.asyncio
async def test_byok_key_injection(mock_db):
    """send_message_to_llm creates a NEW AsyncOpenAI client when user_api_key is supplied."""
    fake_response = FakeCompletion(content="byok response", tokens=12)

    with (
        patch("app.services.chat_service.AsyncOpenAI") as MockAsyncOpenAI,
        patch("app.services.chat_service.create_chat_message", new_callable=AsyncMock) as mock_msg,
    ):
        mock_msg.return_value = MagicMock(id=2)
        per_req_client = MagicMock()
        per_req_client.chat.completions.create = AsyncMock(return_value=fake_response)
        MockAsyncOpenAI.return_value = per_req_client

        import app.services.chat_service as cs

        result = await cs.send_message_to_llm(
            db=mock_db,
            thread_id=1,
            content="test",
            user_id=7,
            user_api_key="sk-byok-test-key",
            model_id="gpt-4o",
        )

    assert result["success"] is True
    assert result["content"] == "byok response"
    # A per-request AsyncOpenAI must have been instantiated with the user key
    MockAsyncOpenAI.assert_called_once()
    init_kwargs = MockAsyncOpenAI.call_args.kwargs
    assert init_kwargs.get("api_key") == "sk-byok-test-key"


@requires_redis
@pytest.mark.asyncio
async def test_byok_key_not_stored(mock_db):
    """Verify user_api_key is not persisted — it is only passed to the per-request client."""
    fake_response = FakeCompletion(content="ok", tokens=5)

    with (
        patch("app.services.chat_service.AsyncOpenAI") as MockAsyncOpenAI,
        patch("app.services.chat_service.create_chat_message", new_callable=AsyncMock) as mock_msg,
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


@requires_redis
@pytest.mark.asyncio
async def test_model_id_overrides_default(mock_db):
    """model_id parameter overrides the default LLM_MODEL_NAME."""
    fake_response = FakeCompletion(content="fine-tuned", tokens=6)

    with (
        patch("app.services.chat_service._client") as mock_client,
        patch("app.services.chat_service.create_chat_message", new_callable=AsyncMock) as mock_msg,
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


@requires_redis
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
        patch("app.services.chat_service.create_chat_message", new_callable=AsyncMock) as mock_msg,
    ):
        mock_msg.return_value = MagicMock(id=10)
        per_req_client = MagicMock()
        per_req_client.chat.completions.create = AsyncMock(return_value=fake_stream_response)
        MockAsyncOpenAI.return_value = per_req_client

        import app.services.chat_service as cs

        events = [
            event
            async for event in cs.stream_message_to_llm(
                db=mock_db,
                thread_id=1,
                content="stream me",
                user_id=3,
                user_api_key="sk-stream-key",
            )
        ]

    MockAsyncOpenAI.assert_called_once()
    init_kwargs = MockAsyncOpenAI.call_args.kwargs
    assert init_kwargs.get("api_key") == "sk-stream-key"

    import json

    token_events = [json.loads(e) for e in events if json.loads(e).get("type") == "token"]
    assert len(token_events) == 2


@requires_redis
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
        patch("app.services.chat_service.AsyncOpenAI") as MockAsyncOpenAI,
        patch("app.services.chat_service.create_chat_message", new_callable=AsyncMock) as mock_msg,
    ):
        mock_msg.return_value = MagicMock(id=11)
        mock_client.chat.completions.create = AsyncMock(return_value=fake_stream_response)
        # Make sure even if a new AsyncOpenAI is created, its create returns the same mock
        new_client = MagicMock()
        new_client.chat.completions.create = mock_client.chat.completions.create
        MockAsyncOpenAI.return_value = new_client

        import app.services.chat_service as cs

        events = [
            event
            async for event in cs.stream_message_to_llm(
                db=mock_db,
                thread_id=2,
                content="default stream",
                user_id=4,
                user_api_key=None,
            )
        ]

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
        """Keys starting with sk- are generic (OpenAI, Together, DeepInfra) so return None."""
        from app.services.chat_service import _detect_provider_from_key

        result = _detect_provider_from_key("***")
        assert result is None

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

        result = _validate_byok_key_matches_model("sk-test-key", "openai/gpt-4o")
        assert result is None

    def test_openai_key_with_openai_compatible_model_valid(self):
        """OpenAI key should work with openai_compatible/* models."""
        from app.services.chat_service import _validate_byok_key_matches_model

        result = _validate_byok_key_matches_model("sk-proj-Vche123", "openai_compatible/gpt-4o")
        assert result is None

    def test_custom_vendor_key_with_openai_compatible_model_valid(self):
        """Unknown vendor keys should be allowed for openai_compatible/* models."""
        from app.services.chat_service import _validate_byok_key_matches_model

        result = _validate_byok_key_matches_model("vendor-custom-key-123", "openai_compatible/gpt-4o")
        assert result is None

    def test_google_key_with_openai_compatible_model_rejected(self):
        """Google key (AIza) should be rejected for openai_compatible/* models."""
        from app.services.chat_service import _validate_byok_key_matches_model

        result = _validate_byok_key_matches_model("AIzaSyABC123", "openai_compatible/gpt-4o")
        assert result is not None
        assert "mismatch" in result.lower()

    def test_anthropic_key_with_openai_compatible_model_rejected(self):
        """Anthropic key (sk-ant-) should be rejected for openai_compatible/* models."""
        from app.services.chat_service import _validate_byok_key_matches_model

        result = _validate_byok_key_matches_model("sk-ant-api03", "openai_compatible/gpt-4o")
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

        result = _validate_byok_key_matches_model("sk-ant-api03", "anthropic/claude-3-5-sonnet")
        assert result is None

    def test_llamacpp_model_always_valid(self):
        """Any key should work with llamacpp/* models (keys ignored for llamacpp)."""
        from app.services.chat_service import _validate_byok_key_matches_model

        result = _validate_byok_key_matches_model("sk-test-key", "llamacpp/qwen2.5:latest")
        assert result is None

    def test_openrouter_key_with_openrouter_model_valid(self):
        """OpenRouter key should work with openrouter/* models."""
        from app.services.chat_service import _validate_byok_key_matches_model

        result = _validate_byok_key_matches_model("sk-or-v1-abc", "openrouter/anthropic/claude-3.5-sonnet")
        assert result is None

    def test_deepseek_key_with_deepseek_model_valid(self):
        """DeepSeek key should work with deepseek/* models."""
        from app.services.chat_service import _validate_byok_key_matches_model

        result = _validate_byok_key_matches_model("sk-ds-abc123", "deepseek/deepseek-chat")
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

        base_url, _api_key, model = _resolve_provider("openai/gpt-4o-mini")
        assert base_url == "https://api.openai.com/v1"
        assert model == "gpt-4o-mini"

    def test_resolve_openai_compatible(self):
        """openai_compatible/gpt-4o-mini should resolve correctly."""
        from app.services.chat_service import _resolve_provider

        base_url, _api_key, model = _resolve_provider("openai_compatible/gpt-4o-mini")
        assert base_url == "https://api.openai.com/v1"
        assert model == "gpt-4o-mini"

    def test_resolve_openai_compatible_with_version(self):
        """openai_compatible/gpt-4o-mini-2024-07-18 should resolve correctly."""
        from app.services.chat_service import _resolve_provider

        base_url, _api_key, model = _resolve_provider("openai_compatible/gpt-4o-mini-2024-07-18")
        assert base_url == "https://api.openai.com/v1"
        assert model == "gpt-4o-mini-2024-07-18"


class TestLookupStoredByokKey:
    """Regression tests for _lookup_stored_byok_key generic-key fallback.

    Root cause (2026-07-19): an openai_compatible (generic) BYOK key is stored
    with provider="openai_compatible" regardless of the model prefix. When a
    model like tencent/hy3:free is requested, the provider hint is "tencent",
    which never equals "openai_compatible", so the lookup returned (None, None)
    and chat fell through to the platform key (400/403). Generic keys must be
    used for any model id.
    """

    @pytest.mark.asyncio
    async def test_generic_openai_compatible_key_used_for_any_model(self):
        """A stored openai_compatible key must satisfy a non-matching hint."""
        from app.services.chat_service import _lookup_stored_byok_key

        key = MagicMock()
        key.provider = "openai_compatible"
        key.id = 72
        key.get_api_key.return_value = "«redacted:sk-…»"
        key.base_url = "https://vendor.example.com/v1"

        db = AsyncMock()
        result = MagicMock()
        result.scalars.return_value.all.return_value = [key]
        db.execute.return_value = result

        api_key, base_url = await _lookup_stored_byok_key(db, user_id=33, provider_hint="tencent")

        assert api_key == "«redacted:sk-…»", "generic key must be used, not None"
        assert base_url == "https://vendor.example.com/v1"

    @pytest.mark.asyncio
    async def test_exact_provider_match_preferred_over_generic(self):
        """An exact provider match wins over a generic key."""
        from app.services.chat_service import _lookup_stored_byok_key

        specific = MagicMock()
        specific.provider = "deepseek"
        specific.id = 10
        specific.get_api_key.return_value = "«redacted:sk-…»"
        specific.base_url = "https://api.deepseek.com"

        generic = MagicMock()
        generic.provider = "openai_compatible"
        generic.id = 11
        generic.get_api_key.return_value = "vendor-key"
        generic.base_url = "https://vendor.example.com/v1"

        db = AsyncMock()
        result = MagicMock()
        result.scalars.return_value.all.return_value = [generic, specific]
        db.execute.return_value = result

        api_key, base_url = await _lookup_stored_byok_key(db, user_id=1, provider_hint="deepseek")

        assert api_key == "«redacted:sk-…»", "exact provider match must win"
        assert base_url == "https://api.deepseek.com"

    def test_resolve_openrouter(self):
        """openrouter/anthropic/claude-3.5-sonnet should resolve correctly."""
        from app.services.chat_service import _resolve_provider

        base_url, _api_key, model = _resolve_provider("openrouter/anthropic/claude-3.5-sonnet")
        assert base_url == "https://openrouter.ai/api/v1"
        assert model == "anthropic/claude-3.5-sonnet"

    def test_resolve_deepseek(self):
        """deepseek/deepseek-chat should resolve correctly."""
        from app.services.chat_service import _resolve_provider

        base_url, _api_key, model = _resolve_provider("deepseek/deepseek-chat")
        assert base_url == "https://api.deepseek.com/v1"
        assert model == "deepseek-chat"

    def test_resolve_no_prefix(self):
        """Model without prefix should use default base URL."""
        from app.services.chat_service import _resolve_provider

        _base_url, _api_key, model = _resolve_provider("gpt-4o-mini")
        assert model == "gpt-4o-mini"


@requires_redis
class TestAPIReceivesCorrectModelName:
    """Acceptance tests verifying the API receives the correct model name."""

    @pytest.mark.asyncio
    async def test_send_message_strips_openai_compatible_prefix(self, mock_db):
        """send_message_to_llm should send gpt-4o-mini-2024-07-18 to API, not openai_compatible/gpt-4o-mini-2024-07-18."""
        from unittest.mock import AsyncMock, MagicMock

        from app.services.chat_service import send_message_to_llm

        fake_response = MagicMock()
        fake_response.choices = [MagicMock(message=MagicMock(content="test response"))]
        fake_response.usage = MagicMock(total_tokens=10, prompt_tokens=4, completion_tokens=6)

        captured_model = None

        async def mock_create(**kwargs):
            nonlocal captured_model
            captured_model = kwargs.get("model")
            return fake_response

        with (
            patch("app.services.chat_service.AsyncOpenAI") as MockAsyncOpenAI,
            patch("app.services.chat_service.create_chat_message", new_callable=AsyncMock) as mock_msg,
            # The real _safe_effective_base_url does a live DNS/SSRF lookup that
            # hangs in offline/sandboxed test environments (no network). Stub it
            # to return the requested base URL unchanged so the test exercises
            # the model-name-stripping path, not the network guard.
            patch(
                "app.services.chat_service._safe_effective_base_url",
                new=AsyncMock(side_effect=lambda effective_base, default_base_url: effective_base or default_base_url),
            ),
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
                user_api_key="sk-test-key",
                model_id="openai_compatible/gpt-4o-mini-2024-07-18",
            )

        assert captured_model == "gpt-4o-mini-2024-07-18", f"Expected 'gpt-4o-mini-2024-07-18', got '{captured_model}'"
        assert result["success"] is True
