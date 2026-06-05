#!/usr/bin/env python3
"""
Webhook Handler Service

A generic webhook handling system for receiving webhooks from external services
and routing them to appropriate handlers.

Components:
- WebhookHandlerService: Main service for webhook processing
- WebhookRouter: Event routing based on source and event type
- RetryManager: Retry logic for failed handlers
- Signature verification for multiple providers (GitHub, Stripe, Slack, etc.)
"""

from .retry import RetryManager, retry_manager
from .router import WebhookRouter, webhook_router
from .service import WebhookHandlerService, webhook_service
from .signature import GitHubVerifier, HMACVerifier, SignatureVerifier, SlackVerifier, StripeVerifier, get_verifier

__all__ = [
    "GitHubVerifier",
    "HMACVerifier",
    # Retry manager
    "RetryManager",
    # Signature verification
    "SignatureVerifier",
    "SlackVerifier",
    "StripeVerifier",
    # Main service
    "WebhookHandlerService",
    # Router
    "WebhookRouter",
    "get_verifier",
    "retry_manager",
    "webhook_router",
    "webhook_service",
]
