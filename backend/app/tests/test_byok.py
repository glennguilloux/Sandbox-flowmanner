from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

# Mock user for testing
MOCK_USER = SimpleNamespace(id=1, email="test@example.com", role="pro")


@pytest.fixture
def app():
    """Create test app with mocked dependencies."""
    from fastapi import FastAPI

    from app.api.v1.byok import router

    app = FastAPI()
    app.include_router(router)

    # Mock get_current_user dependency
    async def mock_get_current_user():
        return MOCK_USER

    app.dependency_overrides = {
        # This would need proper setup with the actual dependency
    }
    return app


@pytest.fixture
def client(app):
    return TestClient(app)


@pytest.mark.asyncio
async def test_create_api_key():
    """Test creating a new API key."""
    with patch("app.api.v1.byok.get_current_user", return_value=MOCK_USER), patch(
        "app.api.v1.byok.get_db"
    ) as mock_get_db, patch(
        "app.utils.encryption.encrypt_api_key", return_value="encrypted_key"
    ), patch(
        "app.api.v1.byok.UserAPIKey"
    ) as MockUserAPIKey:

        from app.api.v1.byok import APIKeyCreate, create_api_key

        # Mock DB session
        mock_db = AsyncMock()
        mock_get_db.return_value = mock_db

        # Mock created key
        mock_key = MagicMock()
        mock_key.id = 1
        mock_key.provider = "openai"
        mock_key.key_label = "My OpenAI Key"
        mock_key.is_active = True
        mock_key.created_at.isoformat.return_value = "2026-04-30T12:00:00"
        mock_key.updated_at.isoformat.return_value = "2026-04-30T12:00:00"

        # Make MockUserAPIKey() return our mock_key
        MockUserAPIKey.return_value = mock_key

        # Call the function
        result = await create_api_key(
            data=APIKeyCreate(
                provider="openai", api_key="sk-test123", label="My OpenAI Key"
            ),
            user=MOCK_USER,
            db=mock_db,
        )

        assert result["data"]["provider"] == "openai"
        assert result["data"]["key_label"] == "My OpenAI Key"
        mock_db.add.assert_called_once()
        mock_db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_list_api_keys():
    """Test listing API keys."""
    with patch("app.api.v1.byok.get_current_user", return_value=MOCK_USER), patch(
        "app.api.v1.byok.get_db"
    ) as mock_get_db:

        from app.api.v1.byok import list_api_keys

        # Mock DB session
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_keys = [
            MagicMock(
                id=1,
                provider="openai",
                key_label="OpenAI",
                is_active=True,
                created_at=MagicMock(isoformat=lambda: "2026-04-30T12:00:00"),
                updated_at=MagicMock(isoformat=lambda: "2026-04-30T12:00:00"),
            ),
            MagicMock(
                id=2,
                provider="anthropic",
                key_label="Anthropic",
                is_active=True,
                created_at=MagicMock(isoformat=lambda: "2026-04-30T12:00:00"),
                updated_at=MagicMock(isoformat=lambda: "2026-04-30T12:00:00"),
            ),
        ]
        mock_result.scalars.return_value.all.return_value = mock_keys
        mock_db.execute.return_value = mock_result
        mock_get_db.return_value = mock_db

        # Call the function
        result = await list_api_keys(user=MOCK_USER, db=mock_db)

        assert len(result) == 2
        assert result[0]["provider"] == "openai"
        assert result[1]["provider"] == "anthropic"


@pytest.mark.asyncio
async def test_delete_api_key():
    """Test deleting (soft-delete) an API key."""
    with patch("app.api.v1.byok.get_current_user", return_value=MOCK_USER), patch(
        "app.api.v1.byok.get_db"
    ) as mock_get_db:

        from app.api.v1.byok import delete_api_key

        # Mock DB session
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_key = MagicMock(id=1, user_id=1, is_active=True)
        mock_result.scalar_one_or_none.return_value = mock_key
        mock_db.execute.return_value = mock_result
        mock_get_db.return_value = mock_db

        # Call the function
        result = await delete_api_key(key_id=1, user=MOCK_USER, db=mock_db)

        assert result is None
        assert mock_key.is_active == False
        mock_db.commit.assert_awaited_once()


def test_encrypt_decrypt_api_key():
    """Test encryption utility."""
    from app.utils.encryption import decrypt_api_key, encrypt_api_key

    original_key = "sk-test123456789"
    encrypted = encrypt_api_key(original_key)
    decrypted = decrypt_api_key(encrypted)

    assert decrypted == original_key
    assert encrypted != original_key


def test_validate_provider():
    """Test provider validation."""
    from app.utils.encryption import validate_provider

    assert validate_provider("openai") == True
    assert validate_provider("OpenAI") == True
    assert validate_provider("comfyui") == True
    assert validate_provider("invalid") == False
