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
    "google": OAuthProviderConfig(
        slug="google",
        name="Google",
        authorize_url="https://accounts.google.com/o/oauth2/v2/auth",
        token_url="https://oauth2.googleapis.com/token",
        client_id_env="GOOGLE_OAUTH_CLIENT_ID",
        client_secret_env="GOOGLE_OAUTH_CLIENT_SECRET",
        scopes=[
            "https://www.googleapis.com/auth/drive.readonly",
            "https://www.googleapis.com/auth/drive.file",
            "https://www.googleapis.com/auth/gmail.send",
            "https://www.googleapis.com/auth/gmail.readonly",
            "https://www.googleapis.com/auth/calendar.events",
            "https://www.googleapis.com/auth/calendar.readonly",
        ],
        extra_auth_params={"access_type": "offline", "prompt": "consent"},
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
    "vercel": OAuthProviderConfig(
        slug="vercel",
        name="Vercel",
        authorize_url="https://vercel.com/oauth/authorize",
        token_url="https://vercel.com/oauth/token",
        client_id_env="VERCEL_OAUTH_CLIENT_ID",
        client_secret_env="VERCEL_OAUTH_CLIENT_SECRET",
        scopes=["user", "projects", "deployments"],
    ),
    "jira": OAuthProviderConfig(
        slug="jira",
        name="Jira",
        authorize_url="https://auth.atlassian.com/authorize",
        token_url="https://auth.atlassian.com/oauth/token",
        client_id_env="JIRA_OAUTH_CLIENT_ID",
        client_secret_env="JIRA_OAUTH_CLIENT_SECRET",
        scopes=["read:jira-work", "write:jira-work", "read:jira-user"],
        extra_auth_params={"audience": "api.atlassian.com", "prompt": "consent"},
    ),
    "confluence": OAuthProviderConfig(
        slug="confluence",
        name="Confluence",
        authorize_url="https://auth.atlassian.com/authorize",
        token_url="https://auth.atlassian.com/oauth/token",
        client_id_env="CONFLUENCE_OAUTH_CLIENT_ID",
        client_secret_env="CONFLUENCE_OAUTH_CLIENT_SECRET",
        scopes=[
            "read:confluence-content.all",
            "write:confluence-content",
            "read:confluence-space.summary",
        ],
        extra_auth_params={"audience": "api.atlassian.com", "prompt": "consent"},
    ),
    "figma": OAuthProviderConfig(
        slug="figma",
        name="Figma",
        authorize_url="https://www.figma.com/oauth",
        token_url="https://www.figma.com/api/oauth/token",
        client_id_env="FIGMA_OAUTH_CLIENT_ID",
        client_secret_env="FIGMA_OAUTH_CLIENT_SECRET",
        scopes=[
            "file_content:read",
            "file_comments:read",
            "file_comments:write",
            "file_versions:read",
        ],
    ),
    "stripe": OAuthProviderConfig(
        slug="stripe",
        name="Stripe",
        authorize_url="https://connect.stripe.com/oauth/authorize",
        token_url="https://connect.stripe.com/oauth/token",
        client_id_env="STRIPE_OAUTH_CLIENT_ID",
        client_secret_env="STRIPE_OAUTH_CLIENT_SECRET",
        scopes=["read_write"],
    ),
    "pagerduty": OAuthProviderConfig(
        slug="pagerduty",
        name="PagerDuty",
        authorize_url="https://identity.pagerduty.com/oauth/authorize",
        token_url="https://identity.pagerduty.com/oauth/token",
        client_id_env="PAGERDUTY_OAUTH_CLIENT_ID",
        client_secret_env="PAGERDUTY_OAUTH_CLIENT_SECRET",
        scopes=[
            "incidents.read",
            "incidents.write",
            "services.read",
            "schedules.read",
            "escalation_policies.read",
        ],
    ),
    "datadog": OAuthProviderConfig(
        slug="datadog",
        name="Datadog",
        authorize_url="https://app.datadoghq.com/oauth2/v1/authorize",
        token_url="https://app.datadoghq.com/oauth2/v1/token",
        client_id_env="DATADOG_OAUTH_CLIENT_ID",
        client_secret_env="DATADOG_OAUTH_CLIENT_SECRET",
        scopes=[
            "dashboards_read",
            "dashboards_write",
            "monitors_read",
            "monitors_write",
            "metrics_read",
            "events_read",
            "incidents_read",
            "incidents_write",
        ],
    ),
    "airtable": OAuthProviderConfig(
        slug="airtable",
        name="Airtable",
        authorize_url="https://airtable.com/oauth2/v1/authorize",
        token_url="https://airtable.com/oauth2/v1/token",
        client_id_env="AIRTABLE_OAUTH_CLIENT_ID",
        client_secret_env="AIRTABLE_OAUTH_CLIENT_SECRET",
        scopes=[
            "data.records:read",
            "data.records:write",
            "schema.bases:read",
        ],
    ),
    "intercom": OAuthProviderConfig(
        slug="intercom",
        name="Intercom",
        authorize_url="https://app.intercom.com/oauth",
        token_url="https://api.intercom.io/auth/eagle/token",
        client_id_env="INTERCOM_OAUTH_CLIENT_ID",
        client_secret_env="INTERCOM_OAUTH_CLIENT_SECRET",
        scopes=[
            "Read and list users",
            "Write conversations",
            "Read conversations",
            "Read admins",
        ],
    ),
    "asana": OAuthProviderConfig(
        slug="asana",
        name="Asana",
        authorize_url="https://app.asana.com/-/oauth_authorize",
        token_url="https://app.asana.com/-/oauth_token",
        client_id_env="ASANA_OAUTH_CLIENT_ID",
        client_secret_env="ASANA_OAUTH_CLIENT_SECRET",
        scopes=[],  # Asana uses "default" scope — no specific scopes needed
    ),
    "gitlab": OAuthProviderConfig(
        slug="gitlab",
        name="GitLab",
        authorize_url="https://gitlab.com/oauth/authorize",
        token_url="https://gitlab.com/oauth/token",
        client_id_env="GITLAB_OAUTH_CLIENT_ID",
        client_secret_env="GITLAB_OAUTH_CLIENT_SECRET",
        scopes=["api"],
    ),
    "clickup": OAuthProviderConfig(
        slug="clickup",
        name="ClickUp",
        authorize_url="https://app.clickup.com/api",
        token_url="https://api.clickup.com/api/v2/oauth/token",
        client_id_env="CLICKUP_OAUTH_CLIENT_ID",
        client_secret_env="CLICKUP_OAUTH_CLIENT_SECRET",
        scopes=[],  # ClickUp has no scopes — user authorizes per-workspace
    ),
    "hubspot": OAuthProviderConfig(
        slug="hubspot",
        name="HubSpot",
        authorize_url="https://app.hubspot.com/oauth/authorize",
        token_url="https://api.hubapi.com/oauth/v1/token",
        client_id_env="HUBSPOT_OAUTH_CLIENT_ID",
        client_secret_env="HUBSPOT_OAUTH_CLIENT_SECRET",
        scopes=[
            "crm.objects.contacts.read",
            "crm.objects.contacts.write",
            "crm.objects.companies.read",
            "crm.objects.companies.write",
            "crm.objects.deals.read",
            "crm.objects.deals.write",
            "crm.objects.owners.read",
            "tickets",
        ],
    ),
    "shopify": OAuthProviderConfig(
        slug="shopify",
        name="Shopify",
        authorize_url="https://{shop}.myshopify.com/admin/oauth/authorize",
        token_url="https://{shop}.myshopify.com/admin/oauth/access_token",
        client_id_env="SHOPIFY_OAUTH_CLIENT_ID",
        client_secret_env="SHOPIFY_OAUTH_CLIENT_SECRET",
        scopes=[
            "read_products",
            "write_products",
            "read_orders",
            "write_orders",
            "read_customers",
            "read_inventory",
        ],
    ),
    "zendesk": OAuthProviderConfig(
        slug="zendesk",
        name="Zendesk",
        authorize_url="https://{subdomain}.zendesk.com/oauth/authorizations/new",
        token_url="https://{subdomain}.zendesk.com/oauth/tokens",
        client_id_env="ZENDESK_OAUTH_CLIENT_ID",
        client_secret_env="ZENDESK_OAUTH_CLIENT_SECRET",
        scopes=[
            "read",
            "write",
        ],
    ),
    "monday": OAuthProviderConfig(
        slug="monday",
        name="Monday.com",
        authorize_url="https://auth.monday.com/oauth2/authorize",
        token_url="https://auth.monday.com/oauth2/token",
        client_id_env="MONDAY_OAUTH_CLIENT_ID",
        client_secret_env="MONDAY_OAUTH_CLIENT_SECRET",
        scopes=[
            "boards:read",
            "boards:write",
            "items:read",
            "items:write",
            "users:read",
        ],
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
