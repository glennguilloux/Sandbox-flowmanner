"""OAuth integration providers — configs, token encryption, and provider definitions."""

import os
from dataclasses import dataclass

from cryptography.fernet import Fernet

from app.config import settings


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


def get_fernet() -> Fernet:
    """Get a Fernet instance from the configured AES_ENCRYPTION_KEY."""
    key = settings.AES_ENCRYPTION_KEY
    if key == "change-me-in-production":
        raise RuntimeError("AES_ENCRYPTION_KEY must be set to a valid Fernet key in production")
    return Fernet(key.encode() if isinstance(key, str) else key)


def encrypt_token(token: str) -> str:
    """Encrypt a token string for storage."""
    f = get_fernet()
    return f.encrypt(token.encode()).decode()


def decrypt_token(encrypted: str) -> str:
    """Decrypt a stored encrypted token."""
    f = get_fernet()
    return f.decrypt(encrypted.encode()).decode()
