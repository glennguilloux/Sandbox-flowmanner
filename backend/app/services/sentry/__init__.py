"""
Sentry Integration Package

Provides Sentry SDK integration, MCP client for Sentry AI,
capability registration, and fix recommendation pipeline.
"""

from .fix_recommender import (
    FixPriority,
    FixRecommender,
    FixStatus,
    PendingFix,
    get_fix_recommender,
)
from .sentry_capability import (
    register_sentry_capabilities,
    unregister_sentry_capabilities,
)
from .sentry_integration import (
    SentryConfig,
    SentryIntegration,
    get_sentry_integration,
    init_sentry,
)
from .sentry_mcp_client import (
    FixRecommendation,
    SeerAnalysis,
    SentryIssue,
    SentryMCPClient,
    get_sentry_mcp_client,
)

__all__ = [
    "FixPriority",
    "FixRecommendation",
    # Fix Recommender
    "FixRecommender",
    "FixStatus",
    "PendingFix",
    "SeerAnalysis",
    "SentryConfig",
    # Integration
    "SentryIntegration",
    "SentryIssue",
    # MCP Client
    "SentryMCPClient",
    "get_fix_recommender",
    "get_sentry_integration",
    "get_sentry_mcp_client",
    "init_sentry",
    # Capability
    "register_sentry_capabilities",
    "unregister_sentry_capabilities",
]
