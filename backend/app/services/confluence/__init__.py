"""Confluence integration service — REST API client for Atlassian Confluence Cloud."""

from .confluence_client import ConfluenceAPIError, ConfluenceClient

__all__ = ["ConfluenceAPIError", "ConfluenceClient"]
