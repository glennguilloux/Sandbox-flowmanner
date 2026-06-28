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

    # GitHub expansion: Actions, Deployments, Releases, Discussions
    github_caps = _INTEGRATION_CAPABILITIES.get("github", [])
    assert len(github_caps) >= 18
    github_ids = {c["id"] for c in github_caps}
    assert "list_workflows" in github_ids
    assert "list_workflow_runs" in github_ids
    assert "get_workflow_run" in github_ids
    assert "rerun_workflow" in github_ids
    assert "list_deployments" in github_ids
    assert "create_release" in github_ids
    assert "list_discussions" in github_ids
    assert "get_issue" in github_ids
    assert "merge_pr" in github_ids

    # Slack expansion: threads, reactions, files
    slack_caps = _INTEGRATION_CAPABILITIES.get("slack", [])
    assert len(slack_caps) >= 11
    slack_ids = {c["id"] for c in slack_caps}
    assert "update_message" in slack_ids
    assert "delete_message" in slack_ids
    assert "reply_to_thread" in slack_ids
    assert "get_thread_replies" in slack_ids
    assert "add_reaction" in slack_ids
    assert "upload_file" in slack_ids
    assert "get_user_profile" in slack_ids

    # Intercom: customer messaging platform
    intercom_caps = _INTEGRATION_CAPABILITIES.get("intercom", [])
    assert len(intercom_caps) >= 10
    intercom_ids = {c["id"] for c in intercom_caps}
    assert "list_conversations" in intercom_ids
    assert "reply_to_conversation" in intercom_ids
    assert "list_contacts" in intercom_ids
    assert "search_contacts" in intercom_ids
    assert "list_companies" in intercom_ids

    # Asana: project management + task automation
    asana_caps = _INTEGRATION_CAPABILITIES.get("asana", [])
    assert len(asana_caps) >= 10
    asana_ids = {c["id"] for c in asana_caps}
    assert "create_task" in asana_ids
    assert "list_tasks" in asana_ids
    assert "complete_task" in asana_ids
    assert "list_projects" in asana_ids
    assert "list_sections" in asana_ids

    # GitLab: DevOps platform (MRs, issues, pipelines)
    gitlab_caps = _INTEGRATION_CAPABILITIES.get("gitlab", [])
    assert len(gitlab_caps) >= 14
    gitlab_ids = {c["id"] for c in gitlab_caps}
    assert "create_merge_request" in gitlab_ids
    assert "merge_merge_request" in gitlab_ids
    assert "approve_merge_request" in gitlab_ids
    assert "create_issue" in gitlab_ids
    assert "list_pipelines" in gitlab_ids
    assert "retry_pipeline" in gitlab_ids

    # Notion expansion: database writes + delete
    notion_caps = _INTEGRATION_CAPABILITIES.get("notion", [])
    assert len(notion_caps) >= 11
    notion_ids = {c["id"] for c in notion_caps}
    assert "get_database" in notion_ids
    assert "create_database" in notion_ids
    assert "update_database" in notion_ids
    assert "delete_page" in notion_ids

    # Linear expansion: projects, cycles, workflow states
    linear_caps = _INTEGRATION_CAPABILITIES.get("linear", [])
    assert len(linear_caps) >= 12
    linear_ids = {c["id"] for c in linear_caps}
    assert "list_projects" in linear_ids
    assert "get_project" in linear_ids
    assert "list_cycles" in linear_ids
    assert "get_cycle" in linear_ids
    assert "list_workflow_states" in linear_ids

    # ClickUp: project management (Batch 8)
    clickup_caps = _INTEGRATION_CAPABILITIES.get("clickup", [])
    assert len(clickup_caps) >= 12
    clickup_ids = {c["id"] for c in clickup_caps}
    assert "create_task" in clickup_ids
    assert "list_tasks" in clickup_ids
    assert "get_task" in clickup_ids
    assert "update_task" in clickup_ids
    assert "list_workspaces" in clickup_ids
    assert "list_spaces" in clickup_ids
    assert "add_comment" in clickup_ids

    # HubSpot: CRM platform (Batch 8)
    hubspot_caps = _INTEGRATION_CAPABILITIES.get("hubspot", [])
    assert len(hubspot_caps) >= 12
    hubspot_ids = {c["id"] for c in hubspot_caps}
    assert "create_contact" in hubspot_ids
    assert "list_contacts" in hubspot_ids
    assert "update_contact" in hubspot_ids
    assert "search_contacts" in hubspot_ids
    assert "create_deal" in hubspot_ids
    assert "list_deals" in hubspot_ids
    assert "list_companies" in hubspot_ids

    # Twilio: SMS/Voice communication (Batch 8)
    twilio_caps = _INTEGRATION_CAPABILITIES.get("twilio", [])
    assert len(twilio_caps) >= 10
    twilio_ids = {c["id"] for c in twilio_caps}
    assert "send_message" in twilio_ids
    assert "list_messages" in twilio_ids
    assert "make_call" in twilio_ids
    assert "list_calls" in twilio_ids
    assert "list_phone_numbers" in twilio_ids
    assert "get_usage" in twilio_ids


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
    assert manager.get_connector_class("intercom") is not None
    assert manager.get_connector_class("asana") is not None
    assert manager.get_connector_class("gitlab") is not None
    assert manager.get_connector_class("clickup") is not None
    assert manager.get_connector_class("hubspot") is not None
    assert manager.get_connector_class("twilio") is not None


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
    assert "intercom" in CONNECTOR_TYPES
    assert "asana" in CONNECTOR_TYPES
    assert "gitlab" in CONNECTOR_TYPES
    assert "clickup" in CONNECTOR_TYPES
    assert "hubspot" in CONNECTOR_TYPES
    assert "twilio" in CONNECTOR_TYPES
