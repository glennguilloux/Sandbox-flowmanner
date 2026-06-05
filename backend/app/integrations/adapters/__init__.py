"""Integration adapters — service-specific actions for connected OAuth apps."""

from app.integrations.adapters.base import BaseIntegrationAdapter
from app.integrations.adapters.github import GitHubAdapter
from app.integrations.adapters.google_drive import GoogleDriveAdapter
from app.integrations.adapters.linear import LinearAdapter
from app.integrations.adapters.notion import NotionAdapter
from app.integrations.adapters.slack import SlackAdapter

__all__ = [
    "BaseIntegrationAdapter",
    "GitHubAdapter",
    "GoogleDriveAdapter",
    "LinearAdapter",
    "NotionAdapter",
    "SlackAdapter",
]
