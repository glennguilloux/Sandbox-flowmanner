from __future__ import annotations

import base64
import logging

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from app.config import settings

logger = logging.getLogger(__name__)


def _get_encryption_key() -> bytes:
    """Derive a Fernet key from the configured secret."""
    # Use ENCRYPTION_KEY from settings, or fall back to SECRET_KEY
    secret = getattr(settings, "ENCRYPTION_KEY", None) or settings.SECRET_KEY
    salt = b"flowmanner-salt-"  # In production, use a unique salt per key
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=100000)
    key = base64.urlsafe_b64encode(kdf.derive(secret.encode()))
    return key


def encrypt_api_key(api_key: str) -> str:
    """Encrypt an API key using AES-256 (via Fernet)."""
    logger.debug("BYOK encrypt: key_len=%d", len(api_key))
    fernet = Fernet(_get_encryption_key())
    encrypted = fernet.encrypt(api_key.encode())
    return base64.urlsafe_b64encode(encrypted).decode()


def decrypt_api_key(encrypted_key: str) -> str:
    """Decrypt an API key."""
    logger.debug("BYOK decrypt: encrypted_len=%d", len(encrypted_key))
    fernet = Fernet(_get_encryption_key())
    decrypted = fernet.decrypt(base64.urlsafe_b64decode(encrypted_key))
    return decrypted.decode()


def validate_provider(provider: str) -> bool:
    """Validate that the provider is supported."""
    is_valid = provider.lower() in [
        "openai", "openai_compatible", "anthropic", "google",
        "deepseek", "openrouter", "llamacpp", "zhipuai",
        "comfyui", "stability",
        "groq", "together", "fireworks", "deepinfra", "xai",
    ]
    logger.debug("BYOK validate: provider=%s valid=%s", provider, is_valid)
    return is_valid
