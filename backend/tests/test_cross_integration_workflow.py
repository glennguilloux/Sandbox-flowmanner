"""Tests for cross-integration workflow discoverability.

Verifies that all integration bridge capabilities are registered so the
agent can use them in cross-integration workflows (e.g., Sentry error →
Linear/Jira issue → Vercel rollback).
"""

import pytest


def test_sentry_linear_jira_vercel_confluence_figma_tools_all_discoverable():
    """All Batch 1-3 integrations have bridge capabilities registered."""
    from app.services.integration_bridge import _INTEGRATION_CAPABILITIES

    sentry_caps = _INTEGRATION_CAPABILITIES.get("sentry", [])
    linear_caps = _INTEGRATION_CAPABILITIES.get("linear", [])
    jira_caps = _INTEGRATION_CAPABILITIES.get("jira", [])
    vercel_caps = _INTEGRATION_CAPABILITIES.get("vercel", [])
    confluence_caps = _INTEGRATION_CAPABILITIES.get("confluence", [])
    figma_caps = _INTEGRATION_CAPABILITIES.get("figma", [])

    assert len(sentry_caps) >= 8
    assert len(linear_caps) >= 7
    assert len(jira_caps) >= 10
    assert len(vercel_caps) >= 9
    assert len(confluence_caps) >= 11
    assert len(figma_caps) >= 8

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

    # Confluence: wiki management + post-mortem workflow
    confluence_ids = {c["id"] for c in confluence_caps}
    assert "create_page" in confluence_ids
    assert "search_content" in confluence_ids
    assert "add_comment" in confluence_ids

    # Figma: design-to-dev pipeline
    figma_ids = {c["id"] for c in figma_caps}
    assert "get_file" in figma_ids
    assert "list_comments" in figma_ids
    assert "post_comment" in figma_ids

    # Stripe: billing/payments + revenue impact
    stripe_caps = _INTEGRATION_CAPABILITIES.get("stripe", [])
    assert len(stripe_caps) >= 13
    stripe_ids = {c["id"] for c in stripe_caps}
    assert "list_charges" in stripe_ids
    assert "get_balance" in stripe_ids
    assert "create_payment_link" in stripe_ids

    # PagerDuty: incident management + on-call
    pagerduty_caps = _INTEGRATION_CAPABILITIES.get("pagerduty", [])
    assert len(pagerduty_caps) >= 12
    pagerduty_ids = {c["id"] for c in pagerduty_caps}
    assert "create_incident" in pagerduty_ids
    assert "list_incidents" in pagerduty_ids
    assert "update_incident" in pagerduty_ids

    # Datadog: monitoring + observability
    datadog_caps = _INTEGRATION_CAPABILITIES.get("datadog", [])
    assert len(datadog_caps) >= 12
    datadog_ids = {c["id"] for c in datadog_caps}
    assert "list_monitors" in datadog_ids
    assert "query_metrics" in datadog_ids
    assert "list_events" in datadog_ids

    # Airtable: database workflows
    airtable_caps = _INTEGRATION_CAPABILITIES.get("airtable", [])
    assert len(airtable_caps) >= 9
    airtable_ids = {c["id"] for c in airtable_caps}
    assert "list_records" in airtable_ids
    assert "create_record" in airtable_ids
    assert "list_bases" in airtable_ids


def test_all_connectors_registered_in_manager():
    """All Batch 1-4 connectors are registered in the ConnectorManager."""
    from app.services.connectors.manager import ConnectorManager

    manager = ConnectorManager()
    assert manager.get_connector_class("sentry") is not None
    assert manager.get_connector_class("linear") is not None
    assert manager.get_connector_class("jira") is not None
    assert manager.get_connector_class("vercel") is not None
    assert manager.get_connector_class("confluence") is not None
    assert manager.get_connector_class("figma") is not None
    assert manager.get_connector_class("stripe") is not None
    assert manager.get_connector_class("pagerduty") is not None
    assert manager.get_connector_class("datadog") is not None
    assert manager.get_connector_class("airtable") is not None


def test_all_connectors_registered_in_init():
    """All Batch 1-4 connectors are registered in CONNECTOR_TYPES."""
    from app.services.connectors import CONNECTOR_TYPES

    assert "sentry" in CONNECTOR_TYPES
    assert "linear" in CONNECTOR_TYPES
    assert "jira" in CONNECTOR_TYPES
    assert "vercel" in CONNECTOR_TYPES
    assert "confluence" in CONNECTOR_TYPES
    assert "figma" in CONNECTOR_TYPES
    assert "stripe" in CONNECTOR_TYPES
    assert "pagerduty" in CONNECTOR_TYPES
    assert "datadog" in CONNECTOR_TYPES
    assert "airtable" in CONNECTOR_TYPES
