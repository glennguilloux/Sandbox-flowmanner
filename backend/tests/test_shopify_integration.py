"""Tests for Shopify integration wiring.

Verifies that the Shopify integration is properly wired through all layers:
AVAILABLE_INTEGRATIONS, manifest, bridge capabilities,
webhook router, connector, OAuth provider, and settings.
"""

import pytest


def test_shopify_in_v1_oauth_providers():
    """Shopify is in the OAuth providers dict."""
    from app.core.oauth import OAUTH_PROVIDERS

    shopify = OAUTH_PROVIDERS.get("shopify")
    assert shopify is not None
    assert shopify.slug == "shopify"
    assert shopify.name == "Shopify"
    assert "myshopify.com" in shopify.authorize_url


def test_shopify_in_available_integrations():
    """Shopify is in the static AVAILABLE_INTEGRATIONS list."""
    from app.api.v1.integrations import AVAILABLE_INTEGRATIONS

    shopify = next((i for i in AVAILABLE_INTEGRATIONS if i.slug == "shopify"), None)
    assert shopify is not None
    assert shopify.name == "Shopify"
    assert shopify.auth_type == "oauth2"
    assert shopify.category == "ecommerce"


def test_shopify_manifest_exists():
    """Shopify manifest file exists and is valid."""
    from pathlib import Path

    manifest_path = Path(__file__).resolve().parents[1] / "integrations" / "manifests" / "shopify.json"
    assert manifest_path.exists(), f"Manifest not found: {manifest_path}"

    import json

    manifest = json.loads(manifest_path.read_text())
    assert manifest["slug"] == "shopify"
    assert manifest["name"] == "Shopify"
    assert manifest["auth_type"] == "oauth2"
    assert len(manifest["capabilities"]) >= 12


def test_shopify_bridge_capabilities():
    """Shopify has all 12 bridge capabilities registered."""
    from app.services.integration_bridge import _INTEGRATION_CAPABILITIES

    caps = _INTEGRATION_CAPABILITIES.get("shopify", [])
    assert len(caps) >= 12

    ids = {c["id"] for c in caps}
    expected = {
        "get_shop",
        "list_products",
        "get_product",
        "create_product",
        "list_orders",
        "get_order",
        "update_order",
        "list_customers",
        "get_customer",
        "list_inventory_levels",
        "create_webhook",
        "list_transactions",
    }
    assert expected.issubset(ids), f"Missing capabilities: {expected - ids}"


def test_shopify_webhook_router_exists():
    """Shopify webhook router is importable."""
    from app.api.v1.integration_webhooks import router

    assert router is not None
    routes = [r.path for r in router.routes]
    assert "/{provider}/webhook" in routes


def test_shopify_connector_importable():
    """ShopifyConnector is importable and has 12 actions."""
    from app.services.connectors.shopify_connector import ShopifyConnector

    assert ShopifyConnector is not None
    assert len(ShopifyConnector.ACTIONS) == 12


def test_shopify_settings_exist():
    """Shopify settings are defined in config."""
    from app.config import settings

    assert hasattr(settings, "SHOPIFY_OAUTH_CLIENT_ID")
    assert hasattr(settings, "SHOPIFY_OAUTH_CLIENT_SECRET")
    assert hasattr(settings, "SHOPIFY_WEBHOOK_SECRET")
