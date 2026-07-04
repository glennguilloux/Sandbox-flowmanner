"""Tests for Stripe integration wiring.

Verifies that the Stripe integration is properly wired through all layers:
OAuth provider, AVAILABLE_INTEGRATIONS, manifest, bridge capabilities,
webhook router, OAuth callback router, connector, and settings.
"""

import pytest


def test_stripe_in_v1_oauth_providers():
    """Stripe OAuth provider is registered."""
    from app.core.oauth import OAUTH_PROVIDERS

    provider = OAUTH_PROVIDERS.get("stripe")
    assert provider is not None
    assert provider.slug == "stripe"
    assert provider.name == "Stripe"
    assert provider.authorize_url == "https://connect.stripe.com/oauth/authorize"
    assert provider.token_url == "https://connect.stripe.com/oauth/token"
    assert provider.client_id_env == "STRIPE_OAUTH_CLIENT_ID"
    assert provider.client_secret_env == "STRIPE_OAUTH_CLIENT_SECRET"
    assert "read_write" in provider.scopes


def test_stripe_in_available_integrations():
    """Stripe is in the static AVAILABLE_INTEGRATIONS list."""
    from app.api.v1.integrations import AVAILABLE_INTEGRATIONS

    stripe = next((i for i in AVAILABLE_INTEGRATIONS if i.slug == "stripe"), None)
    assert stripe is not None
    assert stripe.name == "Stripe"
    assert stripe.auth_type == "oauth2"
    assert stripe.category == "development"


def test_stripe_manifest_exists():
    """Stripe manifest file exists and is valid."""
    from pathlib import Path

    manifest_path = Path(__file__).resolve().parents[1] / "integrations" / "manifests" / "stripe.json"
    assert manifest_path.exists(), f"Manifest not found: {manifest_path}"

    import json

    manifest = json.loads(manifest_path.read_text())
    assert manifest["slug"] == "stripe"
    assert manifest["name"] == "Stripe"
    assert manifest["auth_type"] == "oauth2"
    assert len(manifest["capabilities"]) >= 13


def test_stripe_bridge_capabilities():
    """Stripe has all 13 bridge capabilities registered."""
    from app.services.integration_bridge import _INTEGRATION_CAPABILITIES

    caps = _INTEGRATION_CAPABILITIES.get("stripe", [])
    assert len(caps) >= 13

    ids = {c["id"] for c in caps}
    expected = {
        "get_account",
        "list_charges",
        "get_charge",
        "list_customers",
        "get_customer",
        "list_invoices",
        "get_invoice",
        "list_subscriptions",
        "get_subscription",
        "list_products",
        "list_prices",
        "get_balance",
        "create_payment_link",
    }
    assert expected.issubset(ids), f"Missing capabilities: {expected - ids}"


def test_stripe_webhook_router_exists():
    """Stripe webhook router is importable."""
    from app.api.v1.integration_webhooks import router

    assert router is not None
    # Verify the webhook route is defined
    routes = [r.path for r in router.routes]
    assert "/{provider}/webhook" in routes


def test_stripe_oauth_callback_router_exists():
    """Stripe OAuth callback router is importable."""
    from app.api.v1.stripe_oauth import router

    assert router is not None
    routes = [r.path for r in router.routes]
    assert "/stripe/oauth/callback" in routes


def test_stripe_connector_importable():
    """StripeConnector is importable and has 13 actions."""
    from app.services.connectors.stripe_connector import StripeConnector

    assert StripeConnector is not None
    assert len(StripeConnector.ACTIONS) == 13


def test_stripe_settings_exist():
    """Stripe settings are defined in config."""
    from app.config import settings

    assert hasattr(settings, "STRIPE_OAUTH_CLIENT_ID")
    assert hasattr(settings, "STRIPE_OAUTH_CLIENT_SECRET")
    assert hasattr(settings, "STRIPE_WEBHOOK_SECRET")
