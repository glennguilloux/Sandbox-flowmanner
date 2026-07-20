"""OAuth integration providers — configs, token encryption, and provider definitions."""

import base64
import contextlib
import os
from dataclasses import dataclass

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from app.config import settings

# ---------------------------------------------------------------------------
# OAuth token encryption — key-versioned envelope (KEK rotation scaffold)
# ---------------------------------------------------------------------------
# PROBLEM (audit §9/§12, B9): OAuth tokens were encrypted under a single
# Fernet key derived directly from ``AES_ENCRYPTION_KEY`` with no version tag.
# Rotating the key made every stored token undecryptable.
#
# FIX: new writes are wrapped in a versioned envelope that records which
# Key-Encryption-Key (KEK) version produced the ciphertext:
#
#     envelope = "v1:<kek_version>:<fernet_b64>"
#       v1            = OAuth envelope format version
#       <kek_version> = integer id of the KEK that encrypted this token
#                       (auditability; lets decrypt pick the right KEK)
#       <fernet_b64>  = Fernet token produced with that KEK
#
# The KEK is derived (PBKDF2) from ``BYOK_KEK_SECRET`` via a small key-ring
# (OAUTH_KEK_VERSIONS). Decrypt looks the KEK up by the version embedded in
# the envelope, so old ciphertext keeps decrypting after the active KEK
# rotates. Legacy (pre-scaffold, no-prefix) tokens are still decrypted by the
# original single-key path, so existing rows are never broken.
#
# KEK ROTATION RUNBOOK (operator):
#   1. Append a new entry to OAUTH_KEK_VERSIONS, e.g. ``2: {...}`` mirroring
#      v1 but with a fresh secret source / salt, then set
#      OAUTH_CURRENT_KEK_VERSION = 2.
#      ⚠️ NEVER delete the old entry while any ciphertext still references it.
#   2. Existing stored tokens stay readable — decrypt resolves the KEK from
#      the version stamped in each envelope, not from a single global key.
#   3. To proactively re-wrap every token under the new KEK, run
#      re_encrypt_token() over each stored value (in a migration or one-off
#      script). New writes already use OAUTH_CURRENT_KEK_VERSION.
#   4. Only after 100% of rows are re-wrapped may the old KEK entry be removed
#      from OAUTH_KEK_VERSIONS.
_OAUTH_ENVELOPE_VERSION = "v1"
# Active KEK version used for NEW writes. Bump this after adding a new entry
# to OAUTH_KEK_VERSIONS during a rotation.
_OAUTH_CURRENT_KEK_VERSION = 1

# KEK key-ring. Each entry derives a Fernet key from a secret source. Add new
# versions here; do not remove an entry that still has ciphertext in the DB.
_OAUTH_KEK_VERSIONS: dict[int, dict] = {
    1: {
        "secret": lambda: _oauth_kek_secret(),
        "salt": b"flowmanner-oauth-kek-v1",
        "iterations": 200_000,
    },
}


def _oauth_kek_secret() -> str:
    """Master secret for the OAuth KEK.

    Sourced from ``BYOK_KEK_SECRET`` (dedicated, non-committed secret). For
    local dev/tests only, falls back to ``AES_ENCRYPTION_KEY`` then
    ``SECRET_KEY`` so the code path stays runnable. Production MUST set
    ``BYOK_KEK_SECRET``.
    """
    secret = getattr(settings, "BYOK_KEK_SECRET", None)
    if secret:
        return secret
    return getattr(settings, "AES_ENCRYPTION_KEY", None) or settings.SECRET_KEY


def _oauth_kek_cache() -> dict[int, bytes]:
    """Derive + cache Fernet keys for every KEK version in the key-ring."""
    cache = getattr(_oauth_kek_cache, "_cache", None)
    if cache is None:
        cache = {}
        for version, spec in _OAUTH_KEK_VERSIONS.items():
            kdf = PBKDF2HMAC(
                algorithm=hashes.SHA256(),
                length=32,
                salt=spec["salt"],
                iterations=spec["iterations"],
            )
            cache[version] = base64.urlsafe_b64encode(kdf.derive(spec["secret"]().encode()))
        _oauth_kek_cache._cache = cache  # type: ignore[attr-defined]
    return cache


def _clear_oauth_kek_cache() -> None:
    """Reset the cached OAuth KEKs (used by tests after mutating settings)."""
    with contextlib.suppress(AttributeError):
        del _oauth_kek_cache._cache  # type: ignore[attr-defined]


@dataclass
class OAuthProviderConfig:
    slug: str
    name: str
    authorize_url: str
    token_url: str
    client_id_env: str  # env var name for client_id
    client_secret_env: str  # env var name for client_secret
    scopes: list[str]
    extra_auth_params: dict | None = None

    @property
    def client_id(self) -> str | None:
        return os.getenv(self.client_id_env)

    @property
    def client_secret(self) -> str | None:
        return os.getenv(self.client_secret_env)

    @property
    def is_configured(self) -> bool:
        return bool(self.client_id and self.client_secret)


OAUTH_PROVIDERS: dict[str, OAuthProviderConfig] = {
    "github": OAuthProviderConfig(
        slug="github",
        name="GitHub",
        authorize_url="https://github.com/login/oauth/authorize",
        token_url="https://github.com/login/oauth/access_token",
        client_id_env="GITHUB_OAUTH_CLIENT_ID",
        client_secret_env="GITHUB_OAUTH_CLIENT_SECRET",
        scopes=["read:user", "repo"],
    ),
    "slack": OAuthProviderConfig(
        slug="slack",
        name="Slack",
        authorize_url="https://slack.com/oauth/v2/authorize",
        token_url="https://slack.com/api/oauth.v2.access",
        client_id_env="SLACK_OAUTH_CLIENT_ID",
        client_secret_env="SLACK_OAUTH_CLIENT_SECRET",
        scopes=["channels:read", "chat:write", "users:read"],
    ),
    "google_drive": OAuthProviderConfig(
        slug="google_drive",
        name="Google Drive",
        authorize_url="https://accounts.google.com/o/oauth2/v2/auth",
        token_url="https://oauth2.googleapis.com/token",
        client_id_env="GOOGLE_OAUTH_CLIENT_ID",
        client_secret_env="GOOGLE_OAUTH_CLIENT_SECRET",
        scopes=["https://www.googleapis.com/auth/drive.readonly"],
    ),
    "notion": OAuthProviderConfig(
        slug="notion",
        name="Notion",
        authorize_url="https://api.notion.com/v1/oauth/authorize",
        token_url="https://api.notion.com/v1/oauth/token",
        client_id_env="NOTION_OAUTH_CLIENT_ID",
        client_secret_env="NOTION_OAUTH_CLIENT_SECRET",
        scopes=[],
    ),
    "linear": OAuthProviderConfig(
        slug="linear",
        name="Linear",
        authorize_url="https://linear.app/oauth/authorize",
        token_url="https://api.linear.app/oauth/token",
        client_id_env="LINEAR_OAUTH_CLIENT_ID",
        client_secret_env="LINEAR_OAUTH_CLIENT_SECRET",
        scopes=["read", "write"],
    ),
}


def get_fernet(kek_version: int | None = None) -> Fernet:
    """Get a Fernet instance for the given OAuth KEK version.

    Defaults to the active KEK version used for new writes.
    """
    version = kek_version if kek_version is not None else _OAUTH_CURRENT_KEK_VERSION
    keys = _oauth_kek_cache()
    if version not in keys:
        raise ValueError(f"Unknown OAuth KEK version {version!r}; known versions: {sorted(keys)}")
    return Fernet(keys[version])


def encrypt_token(token: str) -> str:
    """Encrypt a token string for storage using the versioned OAuth envelope.

    New writes are stamped with the active KEK version so they remain
    decryptable after a KEK rotation (decrypt resolves the KEK by version).
    """
    f = get_fernet()
    ct = base64.urlsafe_b64encode(f.encrypt(token.encode())).decode()
    return f"{_OAUTH_ENVELOPE_VERSION}:{_OAUTH_CURRENT_KEK_VERSION}:{ct}"


def decrypt_token(encrypted: str) -> str:
    """Decrypt a stored encrypted token.

    Tolerates BOTH forms:
      * legacy (pre-scaffold) — no envelope prefix, encrypted directly with
        ``AES_ENCRYPTION_KEY`` (current behavior preserved); and
      * new versioned envelope ``v1:<kek_version>:<fernet_b64>``.
    """
    if encrypted.startswith(f"{_OAUTH_ENVELOPE_VERSION}:"):
        return _decrypt_versioned(encrypted)
    return _decrypt_legacy(encrypted)


def _decrypt_versioned(encrypted: str) -> str:
    """Decrypt the versioned envelope, resolving the KEK by stamped version."""
    parts = encrypted.split(":", 2)
    if len(parts) != 3:
        raise ValueError(f"Malformed OAuth envelope: expected 3 parts, got {len(parts)}")
    _prefix, version_str, ct_b64 = parts
    try:
        version = int(version_str)
    except ValueError as exc:
        raise ValueError(f"Invalid KEK version in OAuth envelope: {version_str!r}") from exc
    f = get_fernet(kek_version=version)
    return f.decrypt(base64.urlsafe_b64decode(ct_b64)).decode()


def _decrypt_legacy(encrypted: str) -> str:
    """Decrypt pre-scaffold tokens (single Fernet key from AES_ENCRYPTION_KEY)."""
    key = settings.AES_ENCRYPTION_KEY
    if key == "change-me-in-production":
        raise RuntimeError("AES_ENCRYPTION_KEY must be set to a valid Fernet key in production")
    f = Fernet(key.encode() if isinstance(key, str) else key)
    return f.decrypt(encrypted.encode()).decode()


def re_encrypt_token(encrypted: str) -> str:
    """Decrypt with whatever form it is and re-encrypt under the current KEK.

    Used by migrations / one-off scripts to re-wrap stored tokens under a new
    KEK version during rotation. The plaintext is never returned to the caller.
    """
    plaintext = decrypt_token(encrypted)
    return encrypt_token(plaintext)
