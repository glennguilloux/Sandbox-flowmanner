import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.llm_router import ModelRouter

os.environ.setdefault("OPENAI_API_KEY", "sk-test")

pytestmark = pytest.mark.integration


class TestModelRouterInit:
    def test_init_with_defaults(self):
        router = ModelRouter()
        assert router.db is None
        assert router.user_id is None

    def test_init_with_db_and_user_id(self):
        mock_db = MagicMock()
        router = ModelRouter(db_session=mock_db, user_id="user-123")
        assert router.db == mock_db
        assert router.user_id == "user-123"


class TestRouteRequest:
    @pytest.mark.asyncio
    async def test_route_request_success(self):
        with patch("app.services.llm_router._resolve_provider") as mock_resolve:
            mock_resolve.return_value = (
                "https://api.example.com",
                "sk-test-key",
                "gpt-4",
            )
            with patch("app.services.llm_router.AsyncOpenAI") as mock_client_class:
                mock_client = AsyncMock()
                mock_response = AsyncMock()
                mock_response.choices = [MagicMock(message=MagicMock(content="Hello"))]
                mock_response.usage = MagicMock(prompt_tokens=10, completion_tokens=5, total_tokens=15)
                mock_client.chat.completions.create.return_value = mock_response
                mock_client_class.return_value = mock_client

                router = ModelRouter()
                result = await router.route_request(
                    messages=[{"role": "user", "content": "Hi"}],
                    user_id="user-1",
                )

                assert result["success"] is True
                assert result["content"] == "Hello"
                assert result["cost"]["input_tokens"] == 10
                assert result["cost"]["output_tokens"] == 5

    @pytest.mark.asyncio
    async def test_route_request_failure(self):
        with patch("app.services.llm_router._resolve_provider") as mock_resolve:
            mock_resolve.return_value = (
                "https://api.example.com",
                "sk-test-key",
                "gpt-4",
            )
            with patch("app.services.llm_router.AsyncOpenAI") as mock_client_class:
                mock_client = AsyncMock()
                mock_client.chat.completions.create.side_effect = Exception("API error")
                mock_client_class.return_value = mock_client

                router = ModelRouter()
                result = await router.route_request(
                    messages=[{"role": "user", "content": "Hi"}],
                )

                assert result["success"] is False
                assert "API error" in result["error"]


class TestCheckAllProvidersHealth:
    @pytest.mark.asyncio
    async def test_health_check_all_providers(self):
        import os

        os.environ["DEEPSEEK_API_KEY"] = "sk-test"
        with (
            patch(
                "app.services.llm_router.PROVIDER_MAP",
                {"deepseek": ("https://api.deepseek.com", "DEEPSEEK_API_KEY")},
            ),
            patch("app.services.llm_router._resolve_provider") as mock_resolve,
            patch("app.services.llm_router.AsyncOpenAI") as mock_client_class,
        ):
            mock_resolve.return_value = (
                "https://api.deepseek.com",
                "sk-test",
                "deepseek-v4-flash",
            )
            mock_client = AsyncMock()
            mock_client.chat.completions.create.return_value = MagicMock()
            mock_client_class.return_value = mock_client

            router = ModelRouter()
            health = await router.check_all_providers_health()

            assert "deepseek" in health
            assert health["deepseek"].healthy is True
