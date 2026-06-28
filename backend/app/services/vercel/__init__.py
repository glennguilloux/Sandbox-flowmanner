"""Vercel integration service — REST API client for deployment monitoring and actions."""

from .vercel_client import VercelAPIError, VercelClient

__all__ = ["VercelAPIError", "VercelClient"]
