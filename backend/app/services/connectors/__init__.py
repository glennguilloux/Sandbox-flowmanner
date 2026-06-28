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
from .confluence_connector import ConfluenceConnector
from .discord_connector import DiscordConnector
from .email_connector import EmailConnector
from .figma_connector import FigmaConnector
from .github_connector import GitHubConnector
from .google_connector import GoogleConnector
from .jira_connector import JiraConnector
from .linear_connector import LinearConnector
from .manager import ConnectorManager
from .notion_connector import NotionConnector
from .pagerduty_connector import PagerDutyConnector
from .sentry_connector import SentryConnector
from .slack_connector import SlackConnector
from .stripe_connector import StripeConnector
from .vercel_connector import VercelConnector
from .webhook_connector import WebhookConnector

__all__ = [
    "AuthType",
    "AuthenticationError",
    "BaseConnector",
    "ConfluenceConnector",
    "ConnectorConfig",
    "ConnectorError",
    "ConnectorManager",
    "ConnectorResponse",
    "ConnectorStatus",
    "DiscordConnector",
    "EmailConnector",
    "FigmaConnector",
    "GitHubConnector",
    "GoogleConnector",
    "JiraConnector",
    "LinearConnector",
    "NotionConnector",
    "PagerDutyConnector",
    "RateLimitConfig",
    "RateLimitExceeded",
    "SentryConnector",
    "SlackConnector",
    "StripeConnector",
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
    "google": GoogleConnector,
    "notion": NotionConnector,
    "jira": JiraConnector,
    "confluence": ConfluenceConnector,
    "figma": FigmaConnector,
    "linear": LinearConnector,
    "pagerduty": PagerDutyConnector,
    "sentry": SentryConnector,
    "stripe": StripeConnector,
    "vercel": VercelConnector,
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
