"""
External API Connectors Module

Provides a unified framework for integrating with external services:
- Slack
- Discord
- Email (SMTP/IMAP)
- HTTP Webhooks

Usage:
    from app.services.connectors import ConnectorManager, SlackConnector, DiscordConnector

    manager = ConnectorManager()
    await manager.register_connector("slack_main", slack_config)
    response = await manager.execute("slack_main", "send_message", {...})
"""

from typing import Optional

from .airtable_connector import AirtableConnector
from .asana_connector import AsanaConnector
from .base import (
    AuthenticationError,
    AuthType,
    BaseConnector,
    ConnectorConfig,
    ConnectorError,
    ConnectorResponse,
    ConnectorStatus,
    RateLimitConfig,
    RateLimitExceeded,
)
from .clickup_connector import ClickUpConnector
from .confluence_connector import ConfluenceConnector
from .datadog_connector import DatadogConnector
from .discord_connector import DiscordConnector
from .email_connector import EmailConnector
from .figma_connector import FigmaConnector
from .github_connector import GitHubConnector
from .gitlab_connector import GitLabConnector
from .google_connector import GoogleConnector
from .hubspot_connector import HubSpotConnector
from .intercom_connector import IntercomConnector
from .jira_connector import JiraConnector
from .linear_connector import LinearConnector
from .manager import ConnectorManager
from .monday_connector import MondayConnector
from .notion_connector import NotionConnector
from .pagerduty_connector import PagerDutyConnector
from .sentry_connector import SentryConnector
from .shopify_connector import ShopifyConnector
from .slack_connector import SlackConnector
from .stripe_connector import StripeConnector
from .telegram_connector import TelegramConnector
from .twilio_connector import TwilioConnector
from .vercel_connector import VercelConnector
from .webhook_connector import WebhookConnector
from .zendesk_connector import ZendeskConnector

__all__ = [
    "AirtableConnector",
    "AsanaConnector",
    "AuthType",
    "AuthenticationError",
    "BaseConnector",
    "ClickUpConnector",
    "ConfluenceConnector",
    "ConnectorConfig",
    "ConnectorError",
    "ConnectorManager",
    "ConnectorResponse",
    "ConnectorStatus",
    "DatadogConnector",
    "DiscordConnector",
    "EmailConnector",
    "FigmaConnector",
    "GitHubConnector",
    "GitLabConnector",
    "GoogleConnector",
    "HubSpotConnector",
    "IntercomConnector",
    "JiraConnector",
    "LinearConnector",
    "NotionConnector",
    "PagerDutyConnector",
    "RateLimitConfig",
    "RateLimitExceeded",
    "SentryConnector",
    "SlackConnector",
    "StripeConnector",
    "TwilioConnector",
    "VercelConnector",
    "WebhookConnector",
    "get_connector_manager",
]

# Connector type registry
CONNECTOR_TYPES = {
    "slack": SlackConnector,
    "discord": DiscordConnector,
    "email": EmailConnector,
    "webhook": WebhookConnector,
    "github": GitHubConnector,
    "gitlab": GitLabConnector,
    "google": GoogleConnector,
    "intercom": IntercomConnector,
    "notion": NotionConnector,
    "jira": JiraConnector,
    "confluence": ConfluenceConnector,
    "figma": FigmaConnector,
    "hubspot": HubSpotConnector,
    "linear": LinearConnector,
    "airtable": AirtableConnector,
    "asana": AsanaConnector,
    "clickup": ClickUpConnector,
    "datadog": DatadogConnector,
    "pagerduty": PagerDutyConnector,
    "sentry": SentryConnector,
    "stripe": StripeConnector,
    "twilio": TwilioConnector,
    "vercel": VercelConnector,
    "shopify": ShopifyConnector,
    "zendesk": ZendeskConnector,
    "monday": MondayConnector,
    "telegram": TelegramConnector,
}


def get_connector_class(connector_type: str):
    """Get connector class by type name"""
    return CONNECTOR_TYPES.get(connector_type)


def list_available_connectors():
    """List all available connector types"""
    return list(CONNECTOR_TYPES.keys())


# Singleton manager instance
_connector_manager: ConnectorManager | None = None


def get_connector_manager() -> ConnectorManager:
    """Get or create the singleton ConnectorManager instance"""
    global _connector_manager
    if _connector_manager is None:
        _connector_manager = ConnectorManager()
    return _connector_manager
