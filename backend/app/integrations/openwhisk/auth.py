#!/usr/bin/env python3
"""
OpenWhisk Authentication Manager

Handles API key authentication and token management for OpenWhisk.
Supports self-hosted OpenWhisk with API key-based auth.
"""

import base64
import logging
import os

logger = logging.getLogger(__name__)


class OpenWhiskAuthManager:
    """
    Authentication manager for OpenWhisk

    Manages API key authentication and session tokens.
    """

    def __init__(self, api_key: str | None = None):
        """
        Initialize auth manager

        Args:
            api_key: OpenWhisk API key or None (load from env)
        """
        if api_key is None:
            api_key = os.getenv("OPENWHISK_API_KEY")

        if not api_key:
            raise ValueError(
                "OpenWhisk API key is required. Set OPENWHISK_API_KEY environment variable or pass api_key parameter."
            )

        self.api_key = api_key
        self.auth_header = self._build_auth_header(api_key)
        self.namespace = os.getenv("OPENWHISK_NAMESPACE", "_")

        logger.info("OpenWhiskAuthManager initialized")

    def _build_auth_header(self, api_key: str) -> str:
        """
        Build authentication header

        OpenWhisk expects: Basic <base64(api_key:>)
        For API key auth, we use the key as username with empty password

        Args:
            api_key: OpenWhisk API key

        Returns:
            Authorization header value
        """
        # Basic auth with API key as username, empty password
        credentials = f"{api_key}:"
        encoded = base64.b64encode(credentials.encode()).decode()
        return f"Basic {encoded}"

    def get_auth_header(self) -> str:
        """
        Get authentication header for requests

        Returns:
            Authorization header value
        """
        return self.auth_header

    def get_headers(self, content_type: str = "application/json") -> dict:
        """
        Get full headers for HTTP requests

        Args:
            content_type: Content-Type header value

        Returns:
            Dictionary of headers
        """
        return {
            "Authorization": self.auth_header,
            "Content-Type": content_type,
            "User-Agent": "Workflows-Platform-OpenWhisk-Auth/1.0",
        }

    def validate_api_key(self) -> tuple[bool, str | None]:
        """
        Validate API key format

        Returns:
            (is_valid, error_message)
        """
        if not self.api_key:
            return False, "API key is empty"

        # API keys should be at least 16 characters
        if len(self.api_key) < 16:
            return False, "API key is too short"

        # API keys typically are alphanumeric with colons
        if ":" in self.api_key:
            # It might be a username:password format
            parts = self.api_key.split(":")
            if len(parts) != 2:
                return (
                    False,
                    "Invalid API key format (should be key or username:password)",
                )

        return True, None

    def rotate_api_key(self, new_api_key: str) -> None:
        """
        Rotate API key

        Args:
            new_api_key: New API key to use
        """
        logger.warning("Rotating OpenWhisk API key")
        self.api_key = new_api_key
        self.auth_header = self._build_auth_header(new_api_key)
        logger.info("API key rotated successfully")

    def mask_api_key(self, show_chars: int = 4) -> str:
        """
        Mask API key for logging

        Args:
            show_chars: Number of characters to show at end

        Returns:
            Masked API key (e.g., "abcd********xyz123")
        """
        if len(self.api_key) <= show_chars:
            return self.api_key

        visible = self.api_key[-show_chars:]
        masked = "*" * (len(self.api_key) - show_chars)
        return f"{masked}{visible}"


def get_auth_manager() -> OpenWhiskAuthManager | None:
    """
    Factory function to get configured auth manager

    Returns:
        OpenWhiskAuthManager instance or None if not configured
    """
    try:
        manager = OpenWhiskAuthManager()
        logger.info("Auth manager ready (namespace: %s)", manager.namespace)
        return manager
    except ValueError as e:
        logger.warning("Auth manager not configured: %s", e)
        return None
