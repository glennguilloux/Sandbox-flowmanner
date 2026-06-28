"""Tests for cross-integration workflow discoverability.

Verifies that all integration bridge capabilities are registered so the
agent can use them in cross-integration workflows (e.g., Sentry error →
Linear/Jira issue → Vercel rollback).
"""

import pytest


def test_sentry_linear_jira_vercel_tools_all_discoverable():
    """All four Batch 1+2 integrations have bridge capabilities registered."""
    from app.services.integration_bridge import _INTEGRATION_CAPABILITIES

    sentry_caps = _INTEGRATION_CAPABILITIES.get("sentry", [])
    linear_caps = _INTEGRATION_CAPABILITIES.get("linear", [])
    jira_caps = _INTEGRATION_CAPABILITIES.get("jira", [])
    vercel_caps = _INTEGRATION_CAPABILITIES.get("vercel", [])

    assert len(sentry_caps) >= 8
    assert len(linear_caps) >= 7
    assert len(jira_caps) >= 10
    assert len(vercel_caps) >= 9

    # Sentry: get stack trace + poll for errors
    sentry_ids = {c["id"] for c in sentry_caps}
    assert "get_latest_event" in sentry_ids
    assert "list_issues" in sentry_ids

    # Linear: create issue from error
    linear_ids = {c["id"] for c in linear_caps}
    assert "create_issue" in linear_ids

    # Jira: create issue + check for duplicates
    jira_ids = {c["id"] for c in jira_caps}
    assert "create_issue" in jira_ids
    assert "search_issues" in jira_ids

    # Vercel: deployment monitoring + rollback
    vercel_ids = {c["id"] for c in vercel_caps}
    assert "get_deployment" in vercel_ids
    assert "cancel_deployment" in vercel_ids
    assert "redeploy" in vercel_ids


def test_all_connectors_registered_in_manager():
    """All Batch 1+2 connectors are registered in the ConnectorManager."""
    from app.services.connectors.manager import ConnectorManager

    manager = ConnectorManager()
    assert manager.get_connector_class("sentry") is not None
    assert manager.get_connector_class("linear") is not None
    assert manager.get_connector_class("jira") is not None
    assert manager.get_connector_class("vercel") is not None


def test_all_connectors_registered_in_init():
    """All Batch 1+2 connectors are registered in CONNECTOR_TYPES."""
    from app.services.connectors import CONNECTOR_TYPES

    assert "sentry" in CONNECTOR_TYPES
    assert "linear" in CONNECTOR_TYPES
    assert "jira" in CONNECTOR_TYPES
    assert "vercel" in CONNECTOR_TYPES
