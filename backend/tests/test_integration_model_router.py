import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

os.environ.setdefault("OPENAI_API_KEY", "sk-test")

pytestmark = pytest.mark.integration


class TestModelRouterSuccessFlagNotSwallowed:
    @pytest.mark.asyncio
    @patch("app.services.llm_router._resolve_provider", return_value=("", "", "test-model"))
    async def test_route_request_returns_success_false_when_no_api_key(self, mock_resolve):
        from app.services.llm_router import ModelRouter

        router = ModelRouter()
        result = await router.route_request(
            messages=[{"role": "user", "content": "Hello"}],
            user_id="user-1",
            is_admin=False,
            model_preference="test/test-model",
        )

        assert isinstance(result, dict)
        assert result["success"] is False
        assert "error" in result
        assert "No API key" in result["error"]

    @pytest.mark.asyncio
    @patch("app.services.llm_router._resolve_provider", return_value=("", "", "test-model"))
    async def test_route_request_success_false_contains_error_message(self, mock_resolve):
        from app.services.llm_router import ModelRouter

        router = ModelRouter()
        result = await router.route_request(
            messages=[{"role": "user", "content": "Hello"}],
            user_id="user-abc",
            is_admin=False,
        )

        assert result["success"] is False
        assert isinstance(result.get("error"), str)
        assert len(result["error"]) > 0

    @pytest.mark.asyncio
    @patch("app.services.llm_router._resolve_provider")
    @patch("app.services.llm_router._make_client")
    async def test_route_request_returns_exception_error(self, mock_make_client, mock_resolve):
        from app.services.llm_router import ModelRouter

        mock_resolve.return_value = ("http://base", "sk-test", "test-model")
        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(side_effect=Exception("API Timeout"))
        mock_make_client.return_value = mock_client

        router = ModelRouter()
        result = await router.route_request(
            messages=[{"role": "user", "content": "Test"}],
            model_preference="test/test",
            _fallback=False,
        )

        assert result["success"] is False
        assert "API Timeout" in result["error"]


class TestModelRouterBYOKPath:
    @pytest.mark.asyncio
    @patch("app.services.llm_router._make_client")
    @patch("app.services.llm_router._resolve_provider", return_value=("http://default", "sk-default", "test-model"))
    async def test_model_preference_uses_byok_override(self, mock_resolve, mock_make_client):
        from app.services.llm_router import ModelRouter

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content="Success"))]
        mock_response.usage = None
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
        mock_make_client.return_value = mock_client

        router = ModelRouter()
        await router.route_request(
            messages=[{"role": "user", "content": "Hello"}],
            model_preference="test/test-model",
            byok_key_override="sk-override-key",
            byok_base_url_override="http://override-base",
        )

        mock_make_client.assert_called_once_with("http://override-base", "sk-override-key")

    @pytest.mark.asyncio
    @patch("app.services.llm_router._make_client")
    @patch("app.services.llm_router._resolve_provider", return_value=("http://default", "sk-default", "test-model"))
    async def test_model_preference_uses_db_byok_key(self, mock_resolve, mock_make_client):
        from app.services.llm_router import ModelRouter

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content="Success"))]
        mock_response.usage = None
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
        mock_make_client.return_value = mock_client

        router = ModelRouter(user_id="user-123")

        with patch.object(router, "_get_byok_key", new_callable=AsyncMock) as mock_get_byok:
            mock_get_byok.return_value = ("sk-db-key", "http://db-base")

            await router.route_request(
                messages=[{"role": "user", "content": "Hello"}],
                model_preference="test/test-model",
            )

            mock_get_byok.assert_called_once()
            mock_make_client.assert_called_once_with("http://db-base", "sk-db-key")

    @pytest.mark.asyncio
    @patch("app.services.llm_router._make_client")
    @patch("app.services.llm_router._resolve_provider", return_value=("http://default", "sk-default", "test-model"))
    async def test_byok_preference_takes_priority(self, mock_resolve, mock_make_client):
        from app.services.llm_router import ModelRouter

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content="OK"))]
        mock_response.usage = None
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
        mock_make_client.return_value = mock_client

        router = ModelRouter()
        await router.route_request(
            messages=[{"role": "user", "content": "Hello"}],
            model_preference="test/test-model",
            byok_key_override="sk-priority-key",
        )

        # The BYOK key should be used, not the platform default
        call_args = mock_make_client.call_args
        assert call_args[0][1] == "sk-priority-key"


class TestModelRouterUserIdPropagation:
    @pytest.mark.asyncio
    async def test_is_model_available_passes_user_id_to_get_byok(self):
        from app.services.llm_router import ModelRouter

        router = ModelRouter()

        with (
            patch("app.services.llm_router._resolve_provider", return_value=("", "", "test-model")),
            patch.object(router, "_get_byok_key", new_callable=AsyncMock) as mock_get_byok,
        ):
            mock_db = MagicMock()
            mock_get_byok.return_value = ("sk-found", "http://base")

            result = await router._is_model_available(
                "test/test-model",
                user_id="user-byok-123",
                db=mock_db,
            )

            mock_get_byok.assert_called_once_with("user-byok-123", provider_hint="test", db=mock_db)
            assert result is True

    @pytest.mark.asyncio
    @patch("app.services.llm_router._resolve_provider", return_value=("", "", "test-model"))
    async def test_is_model_available_returns_false_when_no_key(self, mock_resolve):
        from app.services.llm_router import ModelRouter

        router = ModelRouter()

        with patch.object(router, "_get_byok_key", new_callable=AsyncMock) as mock_get_byok:
            mock_get_byok.return_value = (None, None)

            result = await router._is_model_available(
                "test/test-model",
                user_id="user-no-key",
                db=MagicMock(),
            )

            assert result is False

    @pytest.mark.asyncio
    async def test_route_request_passes_user_id_through(self):
        from app.services.llm_router import ModelRouter

        router = ModelRouter()

        with (
            patch("app.services.llm_router._resolve_provider") as mock_resolve,
            patch("app.services.llm_router._make_client") as mock_make_client,
        ):
            mock_resolve.return_value = ("http://base", "sk-test", "test-model")
            mock_client = MagicMock()
            mock_response = MagicMock()
            mock_response.choices = [MagicMock(message=MagicMock(content="Hi"))]
            mock_response.usage = MagicMock(prompt_tokens=5, completion_tokens=5, total_tokens=10)
            mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
            mock_make_client.return_value = mock_client

            result = await router.route_request(
                messages=[{"role": "user", "content": "Hello"}],
                model_preference="test/test-model",
                user_id="specific-user-id",
            )

            assert result["success"] is True
            assert result["metadata"]["user_id"] == "specific-user-id"
