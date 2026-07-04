from __future__ import annotations

import base64
import logging
import os

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from app.config import settings

logger = logging.getLogger(__name__)

# Legacy hardcoded salt (used for v1 format keys)
_LEGACY_SALT = b"flowmanner-salt-"

# Versioned format prefix
_V2_PREFIX = "v2:"


def _derive_fernet_key(salt: bytes) -> bytes:
    """Derive a Fernet key from the configured secret and a given salt."""
    secret = getattr(settings, "ENCRYPTION_KEY", None) or settings.SECRET_KEY
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=100_000)
    return base64.urlsafe_b64encode(kdf.derive(secret.encode()))


def encrypt_api_key(api_key: str) -> str:
    """Encrypt an API key with a random per-key salt.

    Format: ``v2:<base64_salt>:<fernet_token>``
    Each encryption generates a fresh 16-byte salt so that two identical
    plaintexts produce different ciphertexts.
    """
    salt = os.urandom(16)
    fernet = Fernet(_derive_fernet_key(salt))
    encrypted = fernet.encrypt(api_key.encode()).decode()
    salt_b64 = base64.urlsafe_b64encode(salt).decode()
    result = f"{_V2_PREFIX}{salt_b64}:{encrypted}"
    logger.debug("BYOK encrypt: key_len=%d, salt=%s", len(api_key), salt_b64)
    return result


def decrypt_api_key(encrypted_key: str) -> str:
    """Decrypt an API key (v1 legacy or v2 per-key-salt format).

    * **v2 keys** (``v2:<salt>:<token>``) use the per-key salt for PBKDF2.
    * **v1 keys** (bare base64 blob) fall back to the legacy hardcoded salt.
    """
    logger.debug("BYOK decrypt: encrypted_len=%d", len(encrypted_key))

    if encrypted_key.startswith(_V2_PREFIX):
        # v2: per-key salt
        parts = encrypted_key.split(":", 2)
        if len(parts) != 3:
            raise ValueError(f"Malformed v2 encrypted key: expected 3 parts, got {len(parts)}")
        _prefix, salt_b64, token = parts
        salt = base64.urlsafe_b64decode(salt_b64)
        fernet = Fernet(_derive_fernet_key(salt))
        return fernet.decrypt(token.encode()).decode()

    # v1: legacy hardcoded salt (base64-encoded Fernet token)
    try:
        fernet = Fernet(_derive_fernet_key(_LEGACY_SALT))
        return fernet.decrypt(base64.urlsafe_b64decode(encrypted_key)).decode()
    except (InvalidToken, Exception) as exc:
        logger.warning("BYOK decrypt failed (legacy format): %s", exc)
        raise


def re_encrypt_api_key(encrypted_key: str) -> str:
    """Decrypt with the current format and re-encrypt with a fresh per-key salt.

    Used by the Alembic migration to upgrade v1 keys to v2.
    """
    plaintext = decrypt_api_key(encrypted_key)
    return encrypt_api_key(plaintext)


def validate_provider(provider: str) -> bool:
    """Validate that the provider is supported."""
    is_valid = provider.lower() in [
        "openai",
        "openai_compatible",
        "anthropic",
        "google",
        "deepseek",
        "openrouter",
        "llamacpp",
        "zhipuai",
        "comfyui",
        "stability",
        "groq",
        "together",
        "fireworks",
        "deepinfra",
        "xai",
    ]
    logger.debug("BYOK validate: provider=%s valid=%s", provider, is_valid)
    return is_valid
