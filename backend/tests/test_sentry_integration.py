"""Tests for Sentry user-facing integration wiring."""

import pytest


def test_sentry_in_available_integrations():
    """Sentry appears in the static AVAILABLE_INTEGRATIONS list."""
    from app.api.v1.integrations import AVAILABLE_INTEGRATIONS

    slugs = [i.slug for i in AVAILABLE_INTEGRATIONS]
    assert "sentry" in slugs


def test_sentry_manifest_exists():
    """Sentry manifest JSON exists and is valid."""
    from app.services.integration_manifest_service import manifest_service

    m = manifest_service.get("sentry")
    assert m is not None
    assert m["auth_type"] == "api_key"
    assert len(m["capabilities"]) >= 8


def test_sentry_client_importable():
    """SentryClient can be imported and instantiated."""
    from app.services.sentry.sentry_client import SentryClient

    client = SentryClient(base_url="https://sentry.io", auth_token="test")
    assert client.base_url == "https://sentry.io"


def test_sentry_connector_importable():
    """SentryConnector can be imported and has expected actions."""
    from app.services.connectors.sentry_connector import SentryConnector

    assert SentryConnector.CONNECTOR_TYPE == "sentry"
    assert "list_issues" in SentryConnector.ACTIONS
    assert "get_latest_event" in SentryConnector.ACTIONS
    assert len(SentryConnector.ACTIONS) == 8


def test_sentry_webhook_router_exists():
    """Sentry webhook router is importable with correct paths."""
    from app.api.v1.sentry_webhook import router

    assert router is not None
    paths = [r.path for r in router.routes]  # type: ignore[union-attr]
    assert "/sentry/webhook" in paths


def test_sentry_bridge_capabilities():
    """Sentry capabilities are registered in the integration bridge."""
    from app.services.integration_bridge import _INTEGRATION_CAPABILITIES

    caps = _INTEGRATION_CAPABILITIES.get("sentry", [])
    assert len(caps) >= 8
    cap_ids = [c["id"] for c in caps]
    assert "list_issues" in cap_ids
    assert "get_latest_event" in cap_ids


def test_sentry_in_non_oauth_configs():
    """Sentry is registered in _NON_OAUTH_CONFIGS for API-key auth."""
    from app.services.integration_bridge import _NON_OAUTH_CONFIGS

    sentry_cfg = _NON_OAUTH_CONFIGS.get("sentry")
    assert sentry_cfg is not None
    assert sentry_cfg["auth_type"] == "bearer_token"


def test_sentry_settings_exist():
    """Sentry webhook settings exist in config."""
    from app.config import settings

    assert hasattr(settings, "SENTRY_WEBHOOK_SECRET")
    assert hasattr(settings, "SENTRY_USER_OAUTH_CLIENT_ID")
    assert hasattr(settings, "SENTRY_USER_OAUTH_CLIENT_SECRET")
