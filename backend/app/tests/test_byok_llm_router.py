"""Regression tests for BYOK key-selection convergence in llm_router.

These pin the contract that the two BYOK key-resolution paths MUST agree
(app/services/AGENTS.md rule 4):

- On no provider match, `_get_byok_key` must return ``(None, None)`` — NOT
  fall back to the first active key of ANY provider (which would bill a
  wrong-provider key against the wrong model family).
- A returned ``base_url`` must pass the same SSRF gate as
  ``app/api/v1/api_keys.py:_is_safe_outbound_url``; an unsafe URL is rejected
  and the provider default is used instead.
- ``route_request`` must refuse a wrong-provider key BEFORE the client call,
  mirroring ``chat_service._validate_byok_key_matches_model``.
"""

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

os.environ.setdefault("OPENAI_API_KEY", "sk-test")

pytestmark = pytest.mark.integration


class _FakeKey:
    """Minimal stand-in for a UserAPIKey row."""

    def __init__(self, kid, provider, api_key, base_url):
        self.id = kid
        self.provider = provider
        self._api_key = api_key
        self.base_url = base_url

    def get_api_key(self):
        return self._api_key


def _make_db_session(keys):
    """Build a fake AsyncSession whose execute() yields the given keys."""
    result = MagicMock()
    scalars = MagicMock()
    scalars.all.return_value = keys
    result.scalars.return_value = scalars
    session = AsyncMock()
    session.execute.return_value = result
    return session


class TestGetByokKeyNoMatchReturnsNone:
    @pytest.mark.asyncio
    async def test_no_provider_match_returns_none_none_not_keys0(self):
        from app.services.llm_router import ModelRouter

        # Stored key is for a DIFFERENT provider than the requested model.
        keys = [_FakeKey(1, "anthropic", "sk-anthropic-xyz", None)]
        db = _make_db_session(keys)

        router = ModelRouter()
        api_key, base_url = await router._get_byok_key("42", provider_hint="openai", db=db)

        # Before the fix this returned ("sk-anthropic-xyz", None) — a
        # wrong-provider key that could reach OpenAI and be billed wrongly.
        assert api_key is None
        assert base_url is None

    @pytest.mark.asyncio
    async def test_multiple_keys_wrong_provider_returns_none_none(self):
        from app.services.llm_router import ModelRouter

        keys = [
            _FakeKey(1, "openrouter", "sk-or-1", "https://openrouter.ai/api/v1"),
            _FakeKey(2, "deepseek", "sk-ds-1", None),
        ]
        db = _make_db_session(keys)

        router = ModelRouter()
        api_key, base_url = await router._get_byok_key("7", provider_hint="openai", db=db)

        assert api_key is None
        assert base_url is None

    @pytest.mark.asyncio
    async def test_provider_match_returns_key_and_base_url(self):
        from app.services.llm_router import ModelRouter

        keys = [_FakeKey(9, "openai", "sk-openai-abc", "https://api.openai.com/v1")]
        db = _make_db_session(keys)

        router = ModelRouter()
        api_key, base_url = await router._get_byok_key("42", provider_hint="openai", db=db)

        assert api_key == "sk-openai-abc"
        assert base_url == "https://api.openai.com/v1"


class TestGetByokKeyUnsafeBaseUrl:
    @pytest.mark.asyncio
    async def test_unsafe_base_url_rejected_returns_none_base(self):
        from app.services.llm_router import ModelRouter

        # Private/loopback base_url must NOT be propagated.
        keys = [_FakeKey(3, "openai", "sk-openai-abc", "http://127.0.0.1:8080/v1")]
        db = _make_db_session(keys)

        router = ModelRouter()
        api_key, base_url = await router._get_byok_key("42", provider_hint="openai", db=db)

        assert api_key == "sk-openai-abc"
        # Unsafe base_url is dropped -> falls back to provider default (None).
        assert base_url is None

    @pytest.mark.asyncio
    async def test_safe_base_url_preserved(self):
        from app.services.llm_router import ModelRouter

        safe = "https://api.openai.com/v1"
        keys = [_FakeKey(4, "openai", "sk-openai-abc", safe)]
        db = _make_db_session(keys)

        router = ModelRouter()
        _api_key, base_url = await router._get_byok_key("42", provider_hint="openai", db=db)

        assert base_url == safe


class TestRouteRequestProviderMismatch:
    @pytest.mark.asyncio
    @patch("app.services.llm_router._make_client")
    @patch(
        "app.services.llm_router._resolve_provider",
        return_value=("http://default", "sk-default", "test-model"),
    )
    async def test_wrong_provider_key_surfaces_error(self, mock_resolve, mock_make_client):
        from app.services.llm_router import ModelRouter

        router = ModelRouter()

        with patch.object(router, "_get_byok_key", new_callable=AsyncMock) as mock_get_byok:
            # An OpenRouter-prefixed key (sk-or-…) is unambiguously the WRONG
            # provider for an openai/* model -> must be refused.
            mock_get_byok.return_value = ("sk-or-wrong-provider-key", None)

            result = await router.route_request(
                messages=[{"role": "user", "content": "Hello"}],
                model_preference="openai/gpt-4o",
                user_id="user-42",
            )

            # The client must NOT be built/used with a wrong-provider key.
            mock_make_client.assert_not_called()
            assert result["success"] is False
            assert "Provider mismatch" in result["error"]

    @pytest.mark.asyncio
    @patch("app.services.llm_router._make_client")
    @patch(
        "app.services.llm_router._resolve_provider",
        return_value=("http://default", "sk-default", "test-model"),
    )
    async def test_matching_provider_key_ok(self, mock_resolve, mock_make_client):
        from app.services.llm_router import ModelRouter

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content="Success"))]
        mock_response.usage = None
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
        mock_make_client.return_value = mock_client

        router = ModelRouter()

        with patch.object(router, "_get_byok_key", new_callable=AsyncMock) as mock_get_byok:
            # An OpenAI-prefixed key (sk-proj-…) matches an openai/* model.
            mock_get_byok.return_value = ("sk-proj-right-provider-key", None)

            result = await router.route_request(
                messages=[{"role": "user", "content": "Hello"}],
                model_preference="openai/gpt-4o",
                user_id="user-42",
            )

            assert result["success"] is True
            mock_make_client.assert_called_once()
