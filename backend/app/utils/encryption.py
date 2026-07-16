from __future__ import annotations

import base64
import logging
import os

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from app.config import settings

logger = logging.getLogger(__name__)

# Legacy hardcoded salt (used ONLY for v1 backward-compat decrypt of old rows).
_LEGACY_SALT = b"flowmanner-salt-"

# Envelope format prefix.
_V3_PREFIX = "v3"
# Format: v3:<kek_id>:<wrapped_dek>:<payload>
#   <kek_id>    = base64 identifier of the active KEK (auditability)
#   <wrapped_dek> = KEK-encrypted data-encryption key (Fernet token)
#   <payload>   = DEK-encrypted API key (Fernet token, random nonce per call)
_V2_PREFIX = "v2"

# Length of the data-encryption key (DEK) in bytes (32 = AES-256).
_DEK_BYTES = 32
# PBKDF2 iterations used to derive the KEK from the master secret.
_KEK_ITERATIONS = 200_000
# Static per-process salt for the KEK derivation (not secret, not per-record).
_KEK_SALT = b"flowmanner-kek-v3"
# Informational id for the single active KEK (auditability in the stored token).
_KEK_ID = b"v3-active"


# ---------------------------------------------------------------------------
# Key-encryption key (KEK) — the master secret, derived once and cached.
# ---------------------------------------------------------------------------
# Previous design derived a Fernet key directly from settings.SECRET_KEY for
# every encrypt/decrypt call. That was single-key (no KEK/DEK separation) AND
# it referenced settings.ENCRYPTION_KEY, which does not exist in this project
# (the real field is AES_ENCRYPTION_KEY) — so it silently fell back to the
# JWT signing secret. Envelope encryption removes both problems: the master
# secret is read from a dedicated field, strengthened with a higher iteration
# count, and used only to wrap per-record DEKs. Compromise of a single
# record's ciphertext does not expose the master secret or other records, and
# rotating the KEK is a re-wrap rather than a full re-encrypt.
_KEK_CACHE: bytes | None = None


def _kek_secret() -> str:
    """Return the master secret used to derive the KEK.

    Sourced from ``BYOK_KEK_SECRET`` (a dedicated, non-committed secret).
    For local development/tests only, falls back to ``AES_ENCRYPTION_KEY`` then
    ``SECRET_KEY`` so the code path stays runnable — but production config MUST
    set ``BYOK_KEK_SECRET`` (enforced by ``settings.validate_production``).
    """
    secret = getattr(settings, "BYOK_KEK_SECRET", None)
    if secret:
        return secret
    return getattr(settings, "AES_ENCRYPTION_KEY", None) or settings.SECRET_KEY


def _get_kek() -> bytes:
    """Derive and cache the key-encryption key (KEK)."""
    global _KEK_CACHE
    if _KEK_CACHE is not None:
        return _KEK_CACHE
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=_KEK_SALT,
        iterations=_KEK_ITERATIONS,
    )
    _KEK_CACHE = base64.urlsafe_b64encode(kdf.derive(_kek_secret().encode()))
    return _KEK_CACHE


def _clear_kek_cache() -> None:
    """Reset the cached KEK (used by tests after mutating settings)."""
    global _KEK_CACHE
    _KEK_CACHE = None


def _fernet_from_key(key: bytes) -> Fernet:
    return Fernet(key)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def encrypt_api_key(api_key: str) -> str:
    """Encrypt an API key using envelope encryption (KEK wraps a per-record DEK).

    Each call generates a fresh random DEK. The DEK is itself encrypted
    ("wrapped") by the KEK and stored alongside the payload, so the master
    secret never sits next to the data and rotating the KEK only requires a
    re-wrap. Fernet embeds a random nonce, so two identical plaintexts still
    produce different ciphertexts.
    """
    kek = _get_kek()
    dek = os.urandom(_DEK_BYTES)
    dek_fernet = _fernet_from_key(base64.urlsafe_b64encode(dek))

    # Wrap the DEK with the KEK.
    wrapped_dek = _fernet_from_key(kek).encrypt(dek)

    # Encrypt the payload with the DEK.
    ciphertext = dek_fernet.encrypt(api_key.encode())

    result = f"{_V3_PREFIX}:{base64.urlsafe_b64encode(_KEK_ID).decode()}:{base64.urlsafe_b64encode(wrapped_dek).decode()}:{base64.urlsafe_b64encode(ciphertext).decode()}"
    # Never log the plaintext or the ciphertext — only lengths.
    logger.debug(
        "BYOK encrypt: key_len=%d ciphertext_len=%d",
        len(api_key),
        len(ciphertext),
    )
    return result


def decrypt_api_key(encrypted_key: str) -> str:
    """Decrypt an API key (v1 legacy, v2 per-key-salt, or v3 envelope)."""
    logger.debug("BYOK decrypt: encrypted_len=%d", len(encrypted_key))

    if encrypted_key.startswith(_V3_PREFIX):
        return _decrypt_v3(encrypted_key)
    if encrypted_key.startswith(_V2_PREFIX):
        return _decrypt_v2(encrypted_key)
    return _decrypt_v1(encrypted_key)


def _decrypt_v3(encrypted_key: str) -> str:
    kek = _get_kek()
    parts = encrypted_key.split(":")
    # v3:<kek_id>:<wrapped_dek>:<ciphertext>
    if len(parts) != 4:
        raise ValueError(f"Malformed v3 encrypted key: expected 4 parts, got {len(parts)}")
    _prefix, _kek_id, wrapped_dek_b64, ciphertext_b64 = parts
    wrapped_dek = base64.urlsafe_b64decode(wrapped_dek_b64)
    ciphertext = base64.urlsafe_b64decode(ciphertext_b64)

    # Unwrap the DEK using the KEK, then decrypt the payload with the DEK.
    dek = _fernet_from_key(kek).decrypt(wrapped_dek)
    return _fernet_from_key(base64.urlsafe_b64encode(dek)).decrypt(ciphertext).decode()


def _decrypt_v2(encrypted_key: str) -> str:
    """Decrypt the former per-key-salt (single-key) format for backward compat."""
    parts = encrypted_key.split(":", 2)
    if len(parts) != 3:
        raise ValueError(f"Malformed v2 encrypted key: expected 3 parts, got {len(parts)}")
    _prefix, salt_b64, token = parts
    salt = base64.urlsafe_b64decode(salt_b64)
    fernet = Fernet(_derive_v2_fernet_key(salt))
    return fernet.decrypt(token.encode()).decode()


def _derive_v2_fernet_key(salt: bytes) -> bytes:
    secret = _kek_secret()
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=100_000)
    return base64.urlsafe_b64encode(kdf.derive(secret.encode()))


def _decrypt_v1(encrypted_key: str) -> str:
    """Decrypt the legacy hardcoded-salt v1 format (read-only backward compat)."""
    if not getattr(settings, "ENCRYPTION_ALLOW_LEGACY_DECRYPT", True):
        raise ValueError(
            "Encrypted value uses the legacy v1 format, which is disabled "
            "(ENCRYPTION_ALLOW_LEGACY_DECRYPT=False). Re-encrypt it with the "
            "v3 envelope format before disabling legacy decryption."
        )
    try:
        fernet = Fernet(_derive_v2_fernet_key(_LEGACY_SALT))
        return fernet.decrypt(base64.urlsafe_b64decode(encrypted_key)).decode()
    except (InvalidToken, Exception) as exc:
        logger.warning("BYOK decrypt failed (legacy format): %s", exc)
        raise


def re_encrypt_api_key(encrypted_key: str) -> str:
    """Decrypt with whatever format it is and re-encrypt as v3 envelope.

    Used by the Alembic migration to upgrade v1/v2 keys to v3.
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
