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
    with (
        patch("app.api.v1.byok.get_current_user", return_value=MOCK_USER),
        patch("app.api.v1.byok.get_db") as mock_get_db,
        patch("app.utils.encryption.encrypt_api_key", return_value="encrypted_key"),
        patch("app.api.v1.byok.UserAPIKey") as MockUserAPIKey,
    ):
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
            data=APIKeyCreate(provider="openai", api_key="sk-test123", label="My OpenAI Key"),
            user=MOCK_USER,
            db=mock_db,
        )

        assert result["provider"] == "openai"
        assert result["key_label"] == "My OpenAI Key"
        mock_db.add.assert_called_once()
        mock_db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_list_api_keys():
    """Test listing API keys."""
    with (
        patch("app.api.v1.byok.get_current_user", return_value=MOCK_USER),
        patch("app.api.v1.byok.get_db") as mock_get_db,
    ):
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
    with (
        patch("app.api.v1.byok.get_current_user", return_value=MOCK_USER),
        patch("app.api.v1.byok.get_db") as mock_get_db,
    ):
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
    """Test encryption utility — v3 envelope format."""
    from app.utils.encryption import decrypt_api_key, encrypt_api_key

    original_key = "«redacted:sk-…»"
    encrypted = encrypt_api_key(original_key)
    decrypted = decrypt_api_key(encrypted)

    assert decrypted == original_key
    assert encrypted.startswith("v3:"), "New encryptions must use v3 envelope format"
    # Random DEK means two encryptions of the same plaintext differ
    encrypted2 = encrypt_api_key(original_key)
    assert encrypted != encrypted2, "Per-record DEK must produce different ciphertexts"
    assert decrypt_api_key(encrypted2) == original_key


def test_decrypt_legacy_v1_key():
    """Test that v1 (legacy hardcoded-salt) keys can still be decrypted."""
    import base64

    from cryptography.fernet import Fernet
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

    from app.utils import encryption as enc_module

    # Simulate a v1 key using the legacy hardcoded salt
    secret = "test-secret-key-for-byok"
    legacy_salt = b"flowmanner-salt-"
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=legacy_salt, iterations=100_000)
    legacy_key = base64.urlsafe_b64encode(kdf.derive(secret.encode()))
    fernet = Fernet(legacy_key)
    plaintext = "sk-legacy-v1-key-value"
    v1_encrypted = base64.urlsafe_b64encode(fernet.encrypt(plaintext.encode())).decode()

    # decrypt_api_key should handle v1 format transparently
    from unittest.mock import patch

    mock_settings = type("S", (), {"ENCRYPTION_KEY": secret, "SECRET_KEY": secret})()
    with patch.object(enc_module, "settings", mock_settings):
        result = enc_module.decrypt_api_key(v1_encrypted)
    assert result == plaintext


def test_re_encrypt_api_key():
    """Test re_encrypt upgrades v1 to v2 format."""
    import base64

    from cryptography.fernet import Fernet
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

    from app.utils import encryption as enc_module

    secret = "test-secret-key-for-byok"
    legacy_salt = b"flowmanner-salt-"
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=legacy_salt, iterations=100_000)
    legacy_key = base64.urlsafe_b64encode(kdf.derive(secret.encode()))
    fernet = Fernet(legacy_key)
    plaintext = "sk-re-encrypt-test"
    v1_encrypted = base64.urlsafe_b64encode(fernet.encrypt(plaintext.encode())).decode()

    mock_settings = type("S", (), {"ENCRYPTION_KEY": secret, "SECRET_KEY": secret})()
    with patch.object(enc_module, "settings", mock_settings):
        v2_encrypted = enc_module.re_encrypt_api_key(v1_encrypted)

    assert v2_encrypted.startswith("v3:"), "re_encrypt must produce v3 envelope format"
    assert v2_encrypted != v1_encrypted
    with patch.object(enc_module, "settings", mock_settings):
        assert enc_module.decrypt_api_key(v2_encrypted) == plaintext


def test_legacy_v1_decrypt_disabled_by_flag():
    """ENCRYPTION_ALLOW_LEGACY_DECRYPT=False must hard-reject v1 keys.

    Verifies the non-breaking hardening: with the flag off, the weakened
    legacy hardcoded-salt path is disabled and decryption of v1 data raises
    instead of silently using the static salt.
    """
    import base64

    from cryptography.fernet import Fernet
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

    from app.utils import encryption as enc_module

    secret = "test-secret-key-for-byok"
    legacy_salt = b"flowmanner-salt-"
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=legacy_salt, iterations=100_000)
    legacy_key = base64.urlsafe_b64encode(kdf.derive(secret.encode()))
    fernet = Fernet(legacy_key)
    plaintext = "«redacted:sk-…»"
    v1_encrypted = base64.urlsafe_b64encode(fernet.encrypt(plaintext.encode())).decode()

    # Default (True) still decrypts v1 — backward-compatible.
    mock_settings_default = type(
        "S",
        (),
        {
            "ENCRYPTION_KEY": secret,
            "SECRET_KEY": secret,
            "ENCRYPTION_ALLOW_LEGACY_DECRYPT": True,
        },
    )()
    with patch.object(enc_module, "settings", mock_settings_default):
        assert enc_module.decrypt_api_key(v1_encrypted) == plaintext

    # Flag off: v1 must raise, not use the legacy salt.
    mock_settings_off = type(
        "S",
        (),
        {
            "ENCRYPTION_KEY": secret,
            "SECRET_KEY": secret,
            "ENCRYPTION_ALLOW_LEGACY_DECRYPT": False,
        },
    )()
    with (
        patch.object(enc_module, "settings", mock_settings_off),
        pytest.raises(ValueError, match="legacy v1 format"),
    ):
        enc_module.decrypt_api_key(v1_encrypted)


def test_validate_provider():
    """Test provider validation."""
    from app.utils.encryption import validate_provider

    assert validate_provider("openai") == True
    assert validate_provider("OpenAI") == True
    assert validate_provider("comfyui") == True
    assert validate_provider("invalid") == False


@pytest.mark.asyncio
async def test_update_api_key_no_rekey():
    """Editing label/base_url/models must NOT re-encrypt the stored key."""
    with (
        patch("app.api.v1.byok.get_current_user", return_value=MOCK_USER),
        patch("app.api.v1.byok.get_db") as mock_get_db,
        patch("app.api.v1.byok.encrypt_api_key") as mock_encrypt,
    ):
        from app.api.v1.byok import APIKeyUpdate, update_api_key

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_key = MagicMock(
            id=1,
            user_id=1,
            provider="openai",
            key_label="Old",
            is_active=True,
            base_url=None,
            encrypted_key="stored-encrypted",
            created_at=MagicMock(isoformat=lambda: "2026-04-30T12:00:00"),
            updated_at=MagicMock(isoformat=lambda: "2026-04-30T12:00:00"),
        )
        mock_key.get_models_list.return_value = ["openai/gpt-4o"]
        mock_result.scalar_one_or_none.return_value = mock_key
        mock_db.execute.return_value = mock_result
        mock_get_db.return_value = mock_db

        result = await update_api_key(
            key_id=1,
            data=APIKeyUpdate(label="New", base_url="https://example.com/v1", models=["openai/gpt-4o"]),
            user=MOCK_USER,
            db=mock_db,
        )

        assert result["key_label"] == "New"
        assert result["base_url"] == "https://example.com/v1"
        assert result["models"] == ["openai/gpt-4o"]
        mock_encrypt.assert_not_called()  # secret untouched
        mock_db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_update_api_key_rekey_on_secret():
    """Supplying api_key must re-encrypt the stored secret."""
    with (
        patch("app.api.v1.byok.get_current_user", return_value=MOCK_USER),
        patch("app.api.v1.byok.get_db") as mock_get_db,
        patch("app.api.v1.byok.encrypt_api_key", return_value="new-encrypted") as mock_encrypt,
    ):
        from app.api.v1.byok import APIKeyUpdate, update_api_key

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_key = MagicMock(
            id=1,
            user_id=1,
            provider="openai",
            key_label="K",
            is_active=True,
            base_url=None,
            encrypted_key="stored-encrypted",
            created_at=MagicMock(isoformat=lambda: "2026-04-30T12:00:00"),
            updated_at=MagicMock(isoformat=lambda: "2026-04-30T12:00:00"),
        )
        mock_key.get_models_list.return_value = None
        mock_result.scalar_one_or_none.return_value = mock_key
        mock_db.execute.return_value = mock_result
        mock_get_db.return_value = mock_db

        await update_api_key(
            key_id=1,
            data=APIKeyUpdate(api_key="sk-brand-new"),
            user=MOCK_USER,
            db=mock_db,
        )

        mock_encrypt.assert_called_once_with("sk-brand-new")
        assert mock_key.encrypted_key == "new-encrypted"


@pytest.mark.asyncio
async def test_update_api_key_missing_returns_404():
    """Updating a non-existent / other user's key returns 404."""
    with (
        patch("app.api.v1.byok.get_current_user", return_value=MOCK_USER),
        patch("app.api.v1.byok.get_db") as mock_get_db,
    ):
        from fastapi import HTTPException

        from app.api.v1.byok import APIKeyUpdate, update_api_key

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None  # not found
        mock_db.execute.return_value = mock_result
        mock_get_db.return_value = mock_db

        with pytest.raises(HTTPException) as exc:
            await update_api_key(
                key_id=999,
                data=APIKeyUpdate(label="x"),
                user=MOCK_USER,
                db=mock_db,
            )
        assert exc.value.status_code == 404
