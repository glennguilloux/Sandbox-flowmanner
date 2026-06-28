"""
Integration Bridge — Wires OAuth-connected integrations into Nexus capabilities.

When a user connects an external service (Slack, GitHub, Google) via the
settings/integrations page, this bridge:

1. Registers the connection's capabilities in the Nexus CapabilityRegistry
   so agents can discover and execute them.
2. On disconnect, unregisters those capabilities.
3. On startup, re-registers capabilities for all active connections.
4. Provides a factory to create live connector instances backed by the
   user's encrypted OAuth tokens.
"""

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.oauth import OAUTH_PROVIDERS, decrypt_token, encrypt_token

logger = logging.getLogger(__name__)

# ── Capability definitions per integration slug ──────────────────────

_INTEGRATION_CAPABILITIES: dict[str, list[dict[str, Any]]] = {
    "slack": [
        {
            "id": "send_message",
            "name": "Send Slack Message",
            "description": "Send a message to a Slack channel or user",
            "params": {"channel": "string", "text": "string"},
        },
        {
            "id": "update_message",
            "name": "Update Slack Message",
            "description": "Update an existing message in a channel",
            "params": {"channel": "string", "ts": "string", "text": "string"},
        },
        {
            "id": "delete_message",
            "name": "Delete Slack Message",
            "description": "Delete a message from a channel",
            "params": {"channel": "string", "ts": "string"},
        },
        {
            "id": "reply_to_thread",
            "name": "Reply to Slack Thread",
            "description": "Reply to an existing message thread",
            "params": {"channel": "string", "thread_ts": "string", "text": "string"},
        },
        {
            "id": "get_thread_replies",
            "name": "Get Slack Thread Replies",
            "description": "Get all replies in a message thread",
            "params": {"channel": "string", "ts": "string"},
        },
        {
            "id": "get_channel_history",
            "name": "Get Slack Channel History",
            "description": "Get recent messages from a Slack channel",
            "params": {"channel": "string", "limit": "integer"},
        },
        {
            "id": "list_channels",
            "name": "List Slack Channels",
            "description": "List all channels in the Slack workspace",
            "params": {},
        },
        {
            "id": "list_users",
            "name": "List Slack Users",
            "description": "List all users in the Slack workspace",
            "params": {},
        },
        {
            "id": "get_user_profile",
            "name": "Get Slack User Profile",
            "description": "Get detailed profile info for a Slack user",
            "params": {"user": "string"},
        },
        {
            "id": "add_reaction",
            "name": "Add Slack Reaction",
            "description": "Add an emoji reaction to a message",
            "params": {"channel": "string", "ts": "string", "name": "string"},
        },
        {
            "id": "get_user_profile",
            "name": "Get Slack User Profile",
            "description": "Get detailed profile info for a Slack user",
            "params": {"user": "string"},
        },
        {
            "id": "upload_file",
            "name": "Upload Slack File",
            "description": "Upload a file to a Slack channel",
            "params": {"channels": "string", "filename": "string", "content": "string"},
        },
    ],
    "github": [
        {
            "id": "create_issue",
            "name": "Create GitHub Issue",
            "description": "Create a new issue on a GitHub repository",
            "params": {
                "owner": "string",
                "repo": "string",
                "title": "string",
                "body": "string",
            },
        },
        {
            "id": "list_issues",
            "name": "List GitHub Issues",
            "description": "List issues in a GitHub repository",
            "params": {"owner": "string", "repo": "string", "state": "string"},
        },
        {
            "id": "get_issue",
            "name": "Get GitHub Issue",
            "description": "Get details of a specific issue",
            "params": {"owner": "string", "repo": "string", "issue_number": "integer"},
        },
        {
            "id": "add_issue_comment",
            "name": "Add GitHub Issue Comment",
            "description": "Add a comment to an issue",
            "params": {"owner": "string", "repo": "string", "issue_number": "integer", "body": "string"},
        },
        {
            "id": "create_pr",
            "name": "Create GitHub Pull Request",
            "description": "Create a pull request on a GitHub repository",
            "params": {
                "owner": "string",
                "repo": "string",
                "title": "string",
                "head": "string",
                "base": "string",
            },
        },
        {
            "id": "list_prs",
            "name": "List GitHub Pull Requests",
            "description": "List pull requests in a GitHub repository",
            "params": {"owner": "string", "repo": "string", "state": "string"},
        },
        {
            "id": "get_pr",
            "name": "Get GitHub Pull Request",
            "description": "Get details of a specific pull request",
            "params": {"owner": "string", "repo": "string", "pr_number": "integer"},
        },
        {
            "id": "merge_pr",
            "name": "Merge GitHub Pull Request",
            "description": "Merge a pull request",
            "params": {"owner": "string", "repo": "string", "pr_number": "integer", "merge_method": "string"},
        },
        {
            "id": "search_code",
            "name": "Search GitHub Code",
            "description": "Search code across GitHub repositories",
            "params": {"q": "string"},
        },
        {
            "id": "get_repo",
            "name": "Get GitHub Repository",
            "description": "Get details about a GitHub repository",
            "params": {"owner": "string", "repo": "string"},
        },
        {
            "id": "list_repos",
            "name": "List GitHub Repositories",
            "description": "List repositories for the authenticated user",
            "params": {},
        },
        {
            "id": "list_workflows",
            "name": "List GitHub Workflows",
            "description": "List GitHub Actions workflows in a repository",
            "params": {"owner": "string", "repo": "string"},
        },
        {
            "id": "list_workflow_runs",
            "name": "List GitHub Workflow Runs",
            "description": "List workflow runs for a repository",
            "params": {"owner": "string", "repo": "string", "per_page": "integer"},
        },
        {
            "id": "get_workflow_run",
            "name": "Get GitHub Workflow Run",
            "description": "Get details of a specific workflow run",
            "params": {"owner": "string", "repo": "string", "run_id": "integer"},
        },
        {
            "id": "rerun_workflow",
            "name": "Rerun GitHub Workflow",
            "description": "Rerun a failed workflow run",
            "params": {"owner": "string", "repo": "string", "run_id": "integer"},
        },
        {
            "id": "list_deployments",
            "name": "List GitHub Deployments",
            "description": "List deployments for a repository",
            "params": {"owner": "string", "repo": "string"},
        },
        {
            "id": "create_release",
            "name": "Create GitHub Release",
            "description": "Create a new release for a repository",
            "params": {"owner": "string", "repo": "string", "tag_name": "string", "name": "string", "body": "string"},
        },
        {
            "id": "list_discussions",
            "name": "List GitHub Discussions",
            "description": "List discussions in a repository (GraphQL)",
            "params": {"owner": "string", "repo": "string", "first": "integer"},
        },
    ],
    "notion": [
        {
            "id": "search",
            "name": "Search Notion",
            "description": "Search pages and databases by title in Notion",
            "params": {"q": "string", "page_size": "integer"},
        },
        {
            "id": "list_databases",
            "name": "List Notion Databases",
            "description": "List all databases shared with the Notion integration",
            "params": {"page_size": "integer"},
        },
        {
            "id": "query_database",
            "name": "Query Notion Database",
            "description": "Query rows from a Notion database with optional filters and sorts",
            "params": {"database_id": "string", "filter": "object", "sorts": "array"},
        },
        {
            "id": "get_database",
            "name": "Get Notion Database",
            "description": "Get a Notion database schema by ID",
            "params": {"database_id": "string"},
        },
        {
            "id": "create_database",
            "name": "Create Notion Database",
            "description": "Create a new Notion database under a page",
            "params": {"parent": "object", "title": "array", "properties": "object"},
        },
        {
            "id": "update_database",
            "name": "Update Notion Database",
            "description": "Update a Notion database schema (title, properties, description)",
            "params": {"database_id": "string", "title": "array", "properties": "object"},
        },
        {
            "id": "get_page",
            "name": "Get Notion Page",
            "description": "Get the properties and content of a Notion page",
            "params": {"page_id": "string"},
        },
        {
            "id": "create_page",
            "name": "Create Notion Page",
            "description": "Create a new page in a Notion database or as a sub-page",
            "params": {"parent": "object", "properties": "object", "children": "array"},
        },
        {
            "id": "update_page",
            "name": "Update Notion Page",
            "description": "Update the properties or archive status of a Notion page",
            "params": {"page_id": "string", "properties": "object"},
        },
        {
            "id": "delete_page",
            "name": "Delete (Archive) Notion Page",
            "description": "Archive a Notion page (soft delete)",
            "params": {"page_id": "string"},
        },
        {
            "id": "get_block_children",
            "name": "Get Notion Block Children",
            "description": "Get the content blocks of a Notion page or block",
            "params": {"block_id": "string", "page_size": "integer"},
        },
        {
            "id": "append_block_children",
            "name": "Append Notion Blocks",
            "description": "Add content blocks to a Notion page or block",
            "params": {"block_id": "string", "children": "array"},
        },
    ],
    "discord": [
        {
            "id": "send_message",
            "name": "Send Discord Message",
            "description": "Send a message (text or embed) to a Discord channel",
            "params": {"channel_id": "string", "content": "string", "embeds": "array"},
        },
        {
            "id": "edit_message",
            "name": "Edit Discord Message",
            "description": "Edit a previously sent message in a Discord channel",
            "params": {
                "channel_id": "string",
                "message_id": "string",
                "content": "string",
            },
        },
        {
            "id": "get_channel_messages",
            "name": "Get Discord Channel Messages",
            "description": "Read recent messages from a Discord channel",
            "params": {
                "channel_id": "string",
                "limit": "integer",
                "before": "string",
                "after": "string",
            },
        },
        {
            "id": "list_channels",
            "name": "List Discord Channels",
            "description": "List all channels in a Discord guild",
            "params": {"guild_id": "string"},
        },
        {
            "id": "list_guilds",
            "name": "List Discord Guilds",
            "description": "List all guilds (servers) the bot is a member of",
            "params": {"limit": "integer"},
        },
        {
            "id": "get_guild",
            "name": "Get Discord Guild",
            "description": "Get detailed information about a Discord guild",
            "params": {"guild_id": "string"},
        },
        {
            "id": "get_user",
            "name": "Get Discord User",
            "description": "Get a Discord user's profile by ID",
            "params": {"user_id": "string"},
        },
        {
            "id": "create_dm",
            "name": "Create Discord DM",
            "description": "Create a direct message channel with a user",
            "params": {"recipient_id": "string"},
        },
        {
            "id": "add_reaction",
            "name": "Add Discord Reaction",
            "description": "Add an emoji reaction to a message",
            "params": {
                "channel_id": "string",
                "message_id": "string",
                "emoji": "string",
            },
        },
        {
            "id": "create_channel",
            "name": "Create Discord Channel",
            "description": "Create a new channel in a Discord guild",
            "params": {"guild_id": "string", "name": "string", "type": "integer"},
        },
    ],
    "sentry": [
        {
            "id": "list_organizations",
            "name": "List Sentry Organizations",
            "description": "List Sentry organizations accessible to the connected account",
            "params": {},
        },
        {
            "id": "list_projects",
            "name": "List Sentry Projects",
            "description": "List projects in a Sentry organization",
            "params": {"org_slug": "string"},
        },
        {
            "id": "list_issues",
            "name": "List Sentry Issues",
            "description": "List error issues in a Sentry organization/project",
            "params": {"org_slug": "string", "query": "string", "limit": "integer"},
        },
        {
            "id": "get_issue",
            "name": "Get Sentry Issue",
            "description": "Get details of a specific Sentry issue",
            "params": {"issue_id": "string"},
        },
        {
            "id": "get_latest_event",
            "name": "Get Sentry Latest Event",
            "description": "Get the latest event (with stack trace) for a Sentry issue",
            "params": {"issue_id": "string"},
        },
        {
            "id": "resolve_issue",
            "name": "Resolve Sentry Issue",
            "description": "Mark a Sentry issue as resolved",
            "params": {"issue_id": "string"},
        },
        {
            "id": "ignore_issue",
            "name": "Ignore Sentry Issue",
            "description": "Mark a Sentry issue as ignored",
            "params": {"issue_id": "string"},
        },
        {
            "id": "list_releases",
            "name": "List Sentry Releases",
            "description": "List releases in a Sentry organization",
            "params": {"org_slug": "string"},
        },
    ],
    "linear": [
        {
            "id": "create_issue",
            "name": "Create Linear Issue",
            "description": "Create a new issue in Linear",
            "params": {
                "title": "string",
                "team_id": "string",
                "description": "string",
                "priority": "integer",
            },
        },
        {
            "id": "update_issue",
            "name": "Update Linear Issue",
            "description": "Update an existing Linear issue (title, status, priority, etc.)",
            "params": {
                "issue_id": "string",
                "title": "string",
                "state_id": "string",
                "priority": "integer",
            },
        },
        {
            "id": "get_issue",
            "name": "Get Linear Issue",
            "description": "Get a Linear issue by ID or identifier (e.g., TEAM-123)",
            "params": {"issue_id": "string", "identifier": "string"},
        },
        {
            "id": "list_issues",
            "name": "List Linear Issues",
            "description": "List issues for a Linear team",
            "params": {"team_id": "string", "max_results": "integer"},
        },
        {
            "id": "search_issues",
            "name": "Search Linear Issues",
            "description": "Search for Linear issues by identifier (e.g., TEAM-123)",
            "params": {"q": "string"},
        },
        {
            "id": "add_comment",
            "name": "Add Linear Comment",
            "description": "Add a comment to a Linear issue",
            "params": {"issue_id": "string", "body": "string"},
        },
        {
            "id": "list_teams",
            "name": "List Linear Teams",
            "description": "List all teams in the Linear workspace",
            "params": {},
        },
        {
            "id": "list_projects",
            "name": "List Linear Projects",
            "description": "List projects for a Linear team",
            "params": {"team_id": "string", "first": "integer"},
        },
        {
            "id": "get_project",
            "name": "Get Linear Project",
            "description": "Get a Linear project by ID",
            "params": {"project_id": "string"},
        },
        {
            "id": "list_cycles",
            "name": "List Linear Cycles",
            "description": "List cycles for a Linear team",
            "params": {"team_id": "string", "first": "integer"},
        },
        {
            "id": "get_cycle",
            "name": "Get Linear Cycle",
            "description": "Get a Linear cycle by ID with its issues",
            "params": {"cycle_id": "string"},
        },
        {
            "id": "list_workflow_states",
            "name": "List Linear Workflow States",
            "description": "List workflow states for a Linear team (for issue status transitions)",
            "params": {"team_id": "string"},
        },
    ],
    "vercel": [
        {
            "id": "get_me",
            "name": "Get Vercel User",
            "description": "Get authenticated Vercel user info",
            "params": {},
        },
        {
            "id": "list_projects",
            "name": "List Vercel Projects",
            "description": "List Vercel projects",
            "params": {"limit": "integer"},
        },
        {
            "id": "get_project",
            "name": "Get Vercel Project",
            "description": "Get project details",
            "params": {"project_id": "string"},
        },
        {
            "id": "list_deployments",
            "name": "List Vercel Deployments",
            "description": "List deployments, optionally filtered by project",
            "params": {"project_id": "string", "limit": "integer"},
        },
        {
            "id": "get_deployment",
            "name": "Get Vercel Deployment",
            "description": "Get deployment details (status, URL, build info)",
            "params": {"deployment_id": "string"},
        },
        {
            "id": "cancel_deployment",
            "name": "Cancel Vercel Deployment",
            "description": "Cancel a running deployment",
            "params": {"deployment_id": "string"},
        },
        {
            "id": "redeploy",
            "name": "Redeploy Vercel Project",
            "description": "Trigger a redeployment from an existing deployment",
            "params": {"deployment_id": "string", "target": "string"},
        },
        {
            "id": "get_deployment_logs",
            "name": "Get Deployment Logs",
            "description": "Get build events and logs for a deployment",
            "params": {"deployment_id": "string"},
        },
        {
            "id": "list_domains",
            "name": "List Vercel Domains",
            "description": "List domains for a Vercel project",
            "params": {"project_id": "string"},
        },
    ],
    "jira": [
        {
            "id": "list_projects",
            "name": "List Jira Projects",
            "description": "List all Jira projects",
            "params": {},
        },
        {
            "id": "get_project",
            "name": "Get Jira Project",
            "description": "Get Jira project details",
            "params": {"project_key": "string"},
        },
        {
            "id": "search_issues",
            "name": "Search Jira Issues",
            "description": "Search issues with JQL query",
            "params": {"jql": "string", "max_results": "integer"},
        },
        {
            "id": "get_issue",
            "name": "Get Jira Issue",
            "description": "Get Jira issue details",
            "params": {"issue_key": "string"},
        },
        {
            "id": "create_issue",
            "name": "Create Jira Issue",
            "description": "Create a new Jira issue (description auto-converted to ADF)",
            "params": {
                "project_key": "string",
                "summary": "string",
                "issue_type": "string",
                "description": "string",
            },
        },
        {
            "id": "update_issue",
            "name": "Update Jira Issue",
            "description": "Update Jira issue fields",
            "params": {"issue_key": "string", "fields": "object"},
        },
        {
            "id": "add_comment",
            "name": "Add Jira Comment",
            "description": "Add a comment to a Jira issue (auto-converted to ADF)",
            "params": {"issue_key": "string", "body": "string"},
        },
        {
            "id": "transition_issue",
            "name": "Transition Jira Issue",
            "description": "Change issue status via transition",
            "params": {"issue_key": "string", "transition_id": "string"},
        },
        {
            "id": "list_boards",
            "name": "List Jira Boards",
            "description": "List Scrum/Kanban boards",
            "params": {},
        },
        {
            "id": "list_sprints",
            "name": "List Jira Sprints",
            "description": "List sprints for a board",
            "params": {"board_id": "integer"},
        },
    ],
    "confluence": [
        {
            "id": "get_me",
            "name": "Get Confluence User",
            "description": "Get authenticated Confluence user info",
            "params": {},
        },
        {
            "id": "list_spaces",
            "name": "List Confluence Spaces",
            "description": "List Confluence spaces",
            "params": {"limit": "integer"},
        },
        {
            "id": "get_space",
            "name": "Get Confluence Space",
            "description": "Get space details",
            "params": {"space_id": "string"},
        },
        {
            "id": "get_page",
            "name": "Get Confluence Page",
            "description": "Get page details with body",
            "params": {"page_id": "string"},
        },
        {
            "id": "create_page",
            "name": "Create Confluence Page",
            "description": "Create a new page in a Confluence space",
            "params": {
                "space_id": "string",
                "title": "string",
                "body": "string",
                "parent_id": "string",
            },
        },
        {
            "id": "update_page",
            "name": "Update Confluence Page",
            "description": "Update page content (auto-increments version)",
            "params": {
                "page_id": "string",
                "title": "string",
                "body": "string",
            },
        },
        {
            "id": "search_content",
            "name": "Search Confluence Content",
            "description": "Search content with CQL query",
            "params": {"cql": "string", "limit": "integer"},
        },
        {
            "id": "list_page_children",
            "name": "List Confluence Page Children",
            "description": "List sub-pages of a page",
            "params": {"page_id": "string", "limit": "integer"},
        },
        {
            "id": "add_comment",
            "name": "Add Confluence Comment",
            "description": "Add a comment to a Confluence page",
            "params": {"page_id": "string", "body": "string"},
        },
        {
            "id": "list_attachments",
            "name": "List Confluence Attachments",
            "description": "List attachments on a page",
            "params": {"page_id": "string", "limit": "integer"},
        },
        {
            "id": "add_labels",
            "name": "Add Confluence Labels",
            "description": "Add labels to a Confluence page",
            "params": {"page_id": "string", "labels": "array"},
        },
    ],
    "figma": [
        {
            "id": "get_me",
            "name": "Get Figma User",
            "description": "Get authenticated Figma user info",
            "params": {},
        },
        {
            "id": "get_file",
            "name": "Get Figma File",
            "description": "Get file details (nodes, styles, components)",
            "params": {"file_key": "string"},
        },
        {
            "id": "get_file_nodes",
            "name": "Get Figma File Nodes",
            "description": "Get specific nodes from a file",
            "params": {"file_key": "string", "node_ids": "array"},
        },
        {
            "id": "list_comments",
            "name": "List Figma Comments",
            "description": "List comments on a Figma file",
            "params": {"file_key": "string"},
        },
        {
            "id": "post_comment",
            "name": "Post Figma Comment",
            "description": "Add a comment to a Figma file",
            "params": {"file_key": "string", "message": "string"},
        },
        {
            "id": "get_file_versions",
            "name": "Get Figma File Versions",
            "description": "Get version history of a file",
            "params": {"file_key": "string"},
        },
        {
            "id": "list_team_projects",
            "name": "List Figma Team Projects",
            "description": "List projects for a Figma team",
            "params": {"team_id": "string"},
        },
        {
            "id": "list_project_files",
            "name": "List Figma Project Files",
            "description": "List files in a Figma project",
            "params": {"project_id": "string"},
        },
    ],
    "stripe": [
        {
            "id": "get_account",
            "name": "Get Stripe Account",
            "description": "Get connected Stripe account info",
            "params": {},
        },
        {
            "id": "list_charges",
            "name": "List Stripe Charges",
            "description": "List charges (paginated)",
            "params": {"limit": "integer", "starting_after": "string"},
        },
        {
            "id": "get_charge",
            "name": "Get Stripe Charge",
            "description": "Get charge details",
            "params": {"charge_id": "string"},
        },
        {
            "id": "list_customers",
            "name": "List Stripe Customers",
            "description": "List customers (paginated)",
            "params": {"limit": "integer", "starting_after": "string"},
        },
        {
            "id": "get_customer",
            "name": "Get Stripe Customer",
            "description": "Get customer details",
            "params": {"customer_id": "string"},
        },
        {
            "id": "list_invoices",
            "name": "List Stripe Invoices",
            "description": "List invoices (paginated)",
            "params": {"limit": "integer", "starting_after": "string"},
        },
        {
            "id": "get_invoice",
            "name": "Get Stripe Invoice",
            "description": "Get invoice details",
            "params": {"invoice_id": "string"},
        },
        {
            "id": "list_subscriptions",
            "name": "List Stripe Subscriptions",
            "description": "List subscriptions (paginated)",
            "params": {"limit": "integer", "status": "string"},
        },
        {
            "id": "get_subscription",
            "name": "Get Stripe Subscription",
            "description": "Get subscription details",
            "params": {"subscription_id": "string"},
        },
        {
            "id": "list_products",
            "name": "List Stripe Products",
            "description": "List products (paginated)",
            "params": {"limit": "integer"},
        },
        {
            "id": "list_prices",
            "name": "List Stripe Prices",
            "description": "List prices, optionally filtered by product",
            "params": {"product": "string", "limit": "integer"},
        },
        {
            "id": "get_balance",
            "name": "Get Stripe Balance",
            "description": "Get current Stripe balance",
            "params": {},
        },
        {
            "id": "create_payment_link",
            "name": "Create Stripe Payment Link",
            "description": "Create a checkout payment link",
            "params": {"line_items": "array"},
        },
    ],
    "pagerduty": [
        {
            "id": "get_me",
            "name": "Get PagerDuty User",
            "description": "Get authenticated PagerDuty user info",
            "params": {},
        },
        {
            "id": "list_incidents",
            "name": "List PagerDuty Incidents",
            "description": "List incidents, optionally filtered by status and urgency",
            "params": {"limit": "integer", "statuses": "array", "urgencies": "array"},
        },
        {
            "id": "get_incident",
            "name": "Get PagerDuty Incident",
            "description": "Get incident details",
            "params": {"incident_id": "string"},
        },
        {
            "id": "create_incident",
            "name": "Create PagerDuty Incident",
            "description": "Create a new incident",
            "params": {"title": "string", "service_id": "string", "urgency": "string", "body": "string"},
        },
        {
            "id": "update_incident",
            "name": "Update PagerDuty Incident",
            "description": "Update incident (acknowledge, resolve, add note)",
            "params": {"incident_id": "string", "status": "string", "note": "string"},
        },
        {
            "id": "list_services",
            "name": "List PagerDuty Services",
            "description": "List PagerDuty services",
            "params": {"limit": "integer"},
        },
        {
            "id": "get_service",
            "name": "Get PagerDuty Service",
            "description": "Get service details",
            "params": {"service_id": "string"},
        },
        {
            "id": "list_schedules",
            "name": "List PagerDuty Schedules",
            "description": "List on-call schedules",
            "params": {"limit": "integer"},
        },
        {
            "id": "get_schedule",
            "name": "Get PagerDuty Schedule",
            "description": "Get schedule details",
            "params": {"schedule_id": "string"},
        },
        {
            "id": "list_escalation_policies",
            "name": "List PagerDuty Escalation Policies",
            "description": "List escalation policies",
            "params": {"limit": "integer"},
        },
        {
            "id": "list_users",
            "name": "List PagerDuty Users",
            "description": "List PagerDuty users",
            "params": {"limit": "integer"},
        },
        {
            "id": "get_user",
            "name": "Get PagerDuty User",
            "description": "Get user details",
            "params": {"user_id": "string"},
        },
    ],
    "datadog": [
        {
            "id": "get_current_user",
            "name": "Get Datadog User",
            "description": "Get authenticated Datadog user info",
            "params": {},
        },
        {
            "id": "list_monitors",
            "name": "List Datadog Monitors",
            "description": "List all monitors, optionally filtered by tags",
            "params": {"monitor_tags": "string", "page_size": "integer"},
        },
        {
            "id": "get_monitor",
            "name": "Get Datadog Monitor",
            "description": "Get monitor details",
            "params": {"monitor_id": "integer"},
        },
        {
            "id": "list_incidents",
            "name": "List Datadog Incidents",
            "description": "List incidents",
            "params": {"page_size": "integer"},
        },
        {
            "id": "get_incident",
            "name": "Get Datadog Incident",
            "description": "Get incident details",
            "params": {"incident_id": "string"},
        },
        {
            "id": "create_incident",
            "name": "Create Datadog Incident",
            "description": "Create a new incident",
            "params": {"title": "string", "severity": "string"},
        },
        {
            "id": "update_incident",
            "name": "Update Datadog Incident",
            "description": "Update incident (title, severity, state)",
            "params": {"incident_id": "string", "title": "string", "severity": "string", "state": "string"},
        },
        {
            "id": "list_dashboards",
            "name": "List Datadog Dashboards",
            "description": "List all dashboards",
            "params": {},
        },
        {
            "id": "get_dashboard",
            "name": "Get Datadog Dashboard",
            "description": "Get dashboard details",
            "params": {"dashboard_id": "string"},
        },
        {
            "id": "list_metrics",
            "name": "List Datadog Metrics",
            "description": "List available metric names",
            "params": {},
        },
        {
            "id": "query_metrics",
            "name": "Query Datadog Metrics",
            "description": "Query metrics over a time range",
            "params": {"query": "string", "from_time": "integer", "to_time": "integer"},
        },
        {
            "id": "list_events",
            "name": "List Datadog Events",
            "description": "List events in a time range",
            "params": {"start": "integer", "end": "integer", "tags": "string"},
        },
    ],
    "airtable": [
        {
            "id": "list_bases",
            "name": "List Airtable Bases",
            "description": "List all accessible bases",
            "params": {},
        },
        {
            "id": "get_base",
            "name": "Get Airtable Base",
            "description": "Get base details",
            "params": {"base_id": "string"},
        },
        {
            "id": "list_tables",
            "name": "List Airtable Tables",
            "description": "List tables in a base",
            "params": {"base_id": "string"},
        },
        {
            "id": "get_table",
            "name": "Get Airtable Table",
            "description": "Get table schema",
            "params": {"base_id": "string", "table_id": "string"},
        },
        {
            "id": "list_records",
            "name": "List Airtable Records",
            "description": "List records in a table with optional filters",
            "params": {
                "base_id": "string",
                "table_id": "string",
                "max_records": "integer",
                "view": "string",
                "filter_by_formula": "string",
            },
        },
        {
            "id": "get_record",
            "name": "Get Airtable Record",
            "description": "Get a single record",
            "params": {"base_id": "string", "table_id": "string", "record_id": "string"},
        },
        {
            "id": "create_record",
            "name": "Create Airtable Record",
            "description": "Create a record in a table",
            "params": {"base_id": "string", "table_id": "string", "fields": "object"},
        },
        {
            "id": "update_record",
            "name": "Update Airtable Record",
            "description": "Update a record",
            "params": {"base_id": "string", "table_id": "string", "record_id": "string", "fields": "object"},
        },
        {
            "id": "delete_record",
            "name": "Delete Airtable Record",
            "description": "Delete a record",
            "params": {"base_id": "string", "table_id": "string", "record_id": "string"},
        },
    ],
    "asana": [
        {
            "id": "get_me",
            "name": "Get Asana User",
            "description": "Get authenticated Asana user info",
            "params": {},
        },
        {
            "id": "list_workspaces",
            "name": "List Asana Workspaces",
            "description": "List user's Asana workspaces",
            "params": {},
        },
        {
            "id": "list_projects",
            "name": "List Asana Projects",
            "description": "List Asana projects, optionally filtered by workspace",
            "params": {"workspace": "string"},
        },
        {
            "id": "get_project",
            "name": "Get Asana Project",
            "description": "Get Asana project details",
            "params": {"project_gid": "string"},
        },
        {
            "id": "list_tasks",
            "name": "List Asana Tasks",
            "description": "List Asana tasks with optional filters",
            "params": {"project": "string", "assignee": "string", "workspace": "string"},
        },
        {
            "id": "get_task",
            "name": "Get Asana Task",
            "description": "Get Asana task details",
            "params": {"task_gid": "string"},
        },
        {
            "id": "create_task",
            "name": "Create Asana Task",
            "description": "Create a new Asana task",
            "params": {
                "name": "string",
                "projects": "array",
                "notes": "string",
                "assignee": "string",
                "due_on": "string",
            },
        },
        {
            "id": "update_task",
            "name": "Update Asana Task",
            "description": "Update an existing Asana task",
            "params": {
                "task_gid": "string",
                "name": "string",
                "notes": "string",
                "assignee": "string",
                "due_on": "string",
                "completed": "boolean",
            },
        },
        {
            "id": "complete_task",
            "name": "Complete Asana Task",
            "description": "Mark an Asana task as completed",
            "params": {"task_gid": "string"},
        },
        {
            "id": "list_sections",
            "name": "List Asana Sections",
            "description": "List sections in an Asana project",
            "params": {"project_gid": "string"},
        },
    ],
    "gitlab": [
        {
            "id": "get_me",
            "name": "Get GitLab User",
            "description": "Get authenticated GitLab user info",
            "params": {},
        },
        {
            "id": "list_projects",
            "name": "List GitLab Projects",
            "description": "List GitLab projects filtered by membership",
            "params": {"page": "integer", "per_page": "integer"},
        },
        {
            "id": "get_project",
            "name": "Get GitLab Project",
            "description": "Get GitLab project details",
            "params": {"project_id": "string"},
        },
        {
            "id": "list_merge_requests",
            "name": "List GitLab Merge Requests",
            "description": "List merge requests for a project",
            "params": {"project_id": "string", "state": "string"},
        },
        {
            "id": "get_merge_request",
            "name": "Get GitLab Merge Request",
            "description": "Get merge request details",
            "params": {"project_id": "string", "mr_iid": "integer"},
        },
        {
            "id": "create_merge_request",
            "name": "Create GitLab Merge Request",
            "description": "Create a new merge request",
            "params": {"project_id": "string", "source_branch": "string", "target_branch": "string", "title": "string"},
        },
        {
            "id": "merge_merge_request",
            "name": "Merge GitLab Merge Request",
            "description": "Merge a merge request",
            "params": {"project_id": "string", "mr_iid": "integer"},
        },
        {
            "id": "approve_merge_request",
            "name": "Approve GitLab Merge Request",
            "description": "Approve a merge request",
            "params": {"project_id": "string", "mr_iid": "integer"},
        },
        {
            "id": "list_issues",
            "name": "List GitLab Issues",
            "description": "List issues for a project",
            "params": {"project_id": "string", "state": "string"},
        },
        {
            "id": "get_issue",
            "name": "Get GitLab Issue",
            "description": "Get issue details",
            "params": {"project_id": "string", "issue_iid": "integer"},
        },
        {
            "id": "create_issue",
            "name": "Create GitLab Issue",
            "description": "Create a new issue",
            "params": {"project_id": "string", "title": "string", "description": "string"},
        },
        {
            "id": "add_issue_note",
            "name": "Add GitLab Issue Comment",
            "description": "Add a comment to an issue",
            "params": {"project_id": "string", "issue_iid": "integer", "body": "string"},
        },
        {
            "id": "list_pipelines",
            "name": "List GitLab Pipelines",
            "description": "List pipelines for a project",
            "params": {"project_id": "string", "status": "string"},
        },
        {
            "id": "retry_pipeline",
            "name": "Retry GitLab Pipeline",
            "description": "Retry a failed pipeline",
            "params": {"project_id": "string", "pipeline_id": "integer"},
        },
    ],
    "intercom": [
        {
            "id": "get_admin",
            "name": "Get Intercom Admin",
            "description": "Get authenticated Intercom admin info",
            "params": {},
        },
        {
            "id": "list_conversations",
            "name": "List Intercom Conversations",
            "description": "List conversations with customers",
            "params": {"per_page": "integer"},
        },
        {
            "id": "get_conversation",
            "name": "Get Intercom Conversation",
            "description": "Get details of a specific conversation",
            "params": {"conversation_id": "string"},
        },
        {
            "id": "reply_to_conversation",
            "name": "Reply to Intercom Conversation",
            "description": "Reply to a customer conversation",
            "params": {"conversation_id": "string", "body": "string", "message_type": "string"},
        },
        {
            "id": "list_contacts",
            "name": "List Intercom Contacts",
            "description": "List contacts in the Intercom workspace",
            "params": {"per_page": "integer"},
        },
        {
            "id": "get_contact",
            "name": "Get Intercom Contact",
            "description": "Get details of a specific contact",
            "params": {"contact_id": "string"},
        },
        {
            "id": "list_companies",
            "name": "List Intercom Companies",
            "description": "List companies in the Intercom workspace",
            "params": {"per_page": "integer"},
        },
        {
            "id": "list_teams",
            "name": "List Intercom Teams",
            "description": "List teams in the Intercom workspace",
            "params": {},
        },
        {
            "id": "list_tags",
            "name": "List Intercom Tags",
            "description": "List tags in the Intercom workspace",
            "params": {},
        },
        {
            "id": "search_contacts",
            "name": "Search Intercom Contacts",
            "description": "Search contacts by name or email",
            "params": {"query": "string"},
        },
    ],
    "clickup": [
        {
            "id": "get_user",
            "name": "Get ClickUp User",
            "description": "Get authenticated ClickUp user info",
            "params": {},
        },
        {
            "id": "list_workspaces",
            "name": "List ClickUp Workspaces",
            "description": "List user's ClickUp workspaces (teams)",
            "params": {},
        },
        {
            "id": "list_spaces",
            "name": "List ClickUp Spaces",
            "description": "List spaces in a ClickUp workspace",
            "params": {"team_id": "string"},
        },
        {
            "id": "list_folders",
            "name": "List ClickUp Folders",
            "description": "List folders in a ClickUp space",
            "params": {"space_id": "string"},
        },
        {
            "id": "list_lists",
            "name": "List ClickUp Lists",
            "description": "List lists in a ClickUp folder",
            "params": {"folder_id": "string"},
        },
        {
            "id": "list_tasks",
            "name": "List ClickUp Tasks",
            "description": "List tasks in a ClickUp list",
            "params": {"list_id": "string", "page": "integer", "order_by": "string"},
        },
        {
            "id": "get_task",
            "name": "Get ClickUp Task",
            "description": "Get ClickUp task details",
            "params": {"task_id": "string"},
        },
        {
            "id": "create_task",
            "name": "Create ClickUp Task",
            "description": "Create a new ClickUp task",
            "params": {
                "list_id": "string",
                "name": "string",
                "description": "string",
                "priority": "integer",
                "status": "string",
            },
        },
        {
            "id": "update_task",
            "name": "Update ClickUp Task",
            "description": "Update a ClickUp task",
            "params": {
                "task_id": "string",
                "name": "string",
                "description": "string",
                "status": "string",
                "priority": "integer",
            },
        },
        {
            "id": "get_comments",
            "name": "Get ClickUp Task Comments",
            "description": "Get comments on a ClickUp task",
            "params": {"task_id": "string"},
        },
        {
            "id": "add_comment",
            "name": "Add ClickUp Task Comment",
            "description": "Add a comment to a ClickUp task",
            "params": {"task_id": "string", "comment_text": "string"},
        },
        {
            "id": "list_time_entries",
            "name": "List ClickUp Time Entries",
            "description": "List time entries for a ClickUp workspace",
            "params": {"team_id": "string"},
        },
    ],
    "hubspot": [
        {
            "id": "get_owner",
            "name": "Get HubSpot Owner",
            "description": "Get HubSpot owner info (credential validation)",
            "params": {},
        },
        {
            "id": "list_contacts",
            "name": "List HubSpot Contacts",
            "description": "List HubSpot contacts with pagination",
            "params": {"limit": "integer", "after": "string"},
        },
        {
            "id": "get_contact",
            "name": "Get HubSpot Contact",
            "description": "Get HubSpot contact details",
            "params": {"contact_id": "string"},
        },
        {
            "id": "create_contact",
            "name": "Create HubSpot Contact",
            "description": "Create a new HubSpot contact",
            "params": {"properties": "object"},
        },
        {
            "id": "update_contact",
            "name": "Update HubSpot Contact",
            "description": "Update a HubSpot contact",
            "params": {"contact_id": "string", "properties": "object"},
        },
        {
            "id": "list_companies",
            "name": "List HubSpot Companies",
            "description": "List HubSpot companies",
            "params": {"limit": "integer", "after": "string"},
        },
        {
            "id": "get_company",
            "name": "Get HubSpot Company",
            "description": "Get HubSpot company details",
            "params": {"company_id": "string"},
        },
        {
            "id": "list_deals",
            "name": "List HubSpot Deals",
            "description": "List HubSpot deals",
            "params": {"limit": "integer", "after": "string"},
        },
        {
            "id": "get_deal",
            "name": "Get HubSpot Deal",
            "description": "Get HubSpot deal details",
            "params": {"deal_id": "string"},
        },
        {
            "id": "create_deal",
            "name": "Create HubSpot Deal",
            "description": "Create a new HubSpot deal",
            "params": {"properties": "object"},
        },
        {
            "id": "search_contacts",
            "name": "Search HubSpot Contacts",
            "description": "Search HubSpot contacts by query",
            "params": {"query": "string", "limit": "integer"},
        },
        {
            "id": "list_tickets",
            "name": "List HubSpot Tickets",
            "description": "List HubSpot support tickets",
            "params": {"limit": "integer", "after": "string"},
        },
    ],
    "twilio": [
        {
            "id": "get_account",
            "name": "Get Twilio Account",
            "description": "Get Twilio account info",
            "params": {},
        },
        {
            "id": "list_messages",
            "name": "List Twilio Messages",
            "description": "List Twilio SMS/MMS messages",
            "params": {"to": "string", "from": "string", "page_size": "integer"},
        },
        {
            "id": "send_message",
            "name": "Send Twilio SMS",
            "description": "Send an SMS/MMS via Twilio",
            "params": {"to": "string", "from": "string", "body": "string"},
        },
        {
            "id": "list_calls",
            "name": "List Twilio Calls",
            "description": "List Twilio calls",
            "params": {"to": "string", "from": "string", "page_size": "integer"},
        },
        {
            "id": "get_call",
            "name": "Get Twilio Call",
            "description": "Get Twilio call details",
            "params": {"call_sid": "string"},
        },
        {
            "id": "make_call",
            "name": "Make Twilio Call",
            "description": "Make an outbound call via Twilio",
            "params": {"to": "string", "from": "string", "url": "string", "twiml": "string"},
        },
        {
            "id": "list_phone_numbers",
            "name": "List Twilio Phone Numbers",
            "description": "List purchased Twilio phone numbers",
            "params": {},
        },
        {
            "id": "get_recording",
            "name": "Get Twilio Recording",
            "description": "Get a Twilio call recording",
            "params": {"recording_sid": "string"},
        },
        {
            "id": "list_recordings",
            "name": "List Twilio Recordings",
            "description": "List Twilio call recordings",
            "params": {"call_sid": "string"},
        },
        {
            "id": "get_usage",
            "name": "Get Twilio Usage",
            "description": "Get Twilio usage and billing records",
            "params": {},
        },
    ],
    "google": [
        # Drive
        {
            "id": "drive_list_files",
            "name": "List Google Drive Files",
            "description": "List files in Google Drive",
            "params": {"folder_id": "string", "max_results": "integer"},
        },
        {
            "id": "drive_search_files",
            "name": "Search Google Drive Files",
            "description": "Search for files by name in Google Drive",
            "params": {"query": "string", "max_results": "integer"},
        },
        {
            "id": "drive_get_file",
            "name": "Get Google Drive File",
            "description": "Get file metadata from Google Drive",
            "params": {"file_id": "string"},
        },
        {
            "id": "drive_create_folder",
            "name": "Create Google Drive Folder",
            "description": "Create a new folder in Google Drive",
            "params": {"name": "string", "parent_id": "string"},
        },
        # Gmail
        {
            "id": "gmail_send",
            "name": "Send Gmail Email",
            "description": "Send an email via Gmail",
            "params": {"to": "string", "subject": "string", "body": "string"},
        },
        {
            "id": "gmail_list",
            "name": "List Gmail Emails",
            "description": "List recent emails from Gmail inbox",
            "params": {"max_results": "integer", "q": "string"},
        },
        {
            "id": "gmail_search",
            "name": "Search Gmail Emails",
            "description": "Search emails in Gmail",
            "params": {"q": "string", "max_results": "integer"},
        },
        # Calendar
        {
            "id": "calendar_list_events",
            "name": "List Calendar Events",
            "description": "List events from Google Calendar",
            "params": {
                "calendar_id": "string",
                "max_results": "integer",
                "time_min": "string",
                "time_max": "string",
            },
        },
        {
            "id": "calendar_create_event",
            "name": "Create Calendar Event",
            "description": "Create a new event in Google Calendar",
            "params": {
                "summary": "string",
                "start": "object",
                "end": "object",
                "description": "string",
            },
        },
        {
            "id": "calendar_get_event",
            "name": "Get Calendar Event",
            "description": "Get details about a Google Calendar event",
            "params": {"calendar_id": "string", "event_id": "string"},
        },
    ],
    "shopify": [
        {
            "id": "get_shop",
            "name": "Get Shopify Shop",
            "description": "Get shop info (credential validation)",
            "params": {},
        },
        {
            "id": "list_products",
            "name": "List Shopify Products",
            "description": "List products",
            "params": {"limit": "integer"},
        },
        {
            "id": "get_product",
            "name": "Get Shopify Product",
            "description": "Get product details",
            "params": {"product_id": "integer"},
        },
        {
            "id": "create_product",
            "name": "Create Shopify Product",
            "description": "Create a product",
            "params": {"title": "string"},
        },
        {
            "id": "list_orders",
            "name": "List Shopify Orders",
            "description": "List orders",
            "params": {"limit": "integer", "status": "string"},
        },
        {
            "id": "get_order",
            "name": "Get Shopify Order",
            "description": "Get order details",
            "params": {"order_id": "integer"},
        },
        {
            "id": "update_order",
            "name": "Update Shopify Order",
            "description": "Update an order",
            "params": {"order_id": "integer"},
        },
        {
            "id": "list_customers",
            "name": "List Shopify Customers",
            "description": "List customers",
            "params": {"limit": "integer"},
        },
        {
            "id": "get_customer",
            "name": "Get Shopify Customer",
            "description": "Get customer details",
            "params": {"customer_id": "integer"},
        },
        {
            "id": "list_inventory_levels",
            "name": "List Shopify Inventory Levels",
            "description": "List inventory levels",
            "params": {"inventory_item_ids": "string"},
        },
        {
            "id": "create_webhook",
            "name": "Create Shopify Webhook",
            "description": "Create a webhook",
            "params": {"topic": "string", "address": "string"},
        },
        {
            "id": "list_transactions",
            "name": "List Shopify Transactions",
            "description": "List payment transactions",
            "params": {"order_id": "integer"},
        },
    ],
    "zendesk": [
        {"id": "get_me", "name": "Get Zendesk User", "description": "Get current user info", "params": {}},
        {
            "id": "list_tickets",
            "name": "List Zendesk Tickets",
            "description": "List tickets",
            "params": {"page": "integer", "per_page": "integer"},
        },
        {
            "id": "get_ticket",
            "name": "Get Zendesk Ticket",
            "description": "Get ticket details",
            "params": {"ticket_id": "integer"},
        },
        {
            "id": "create_ticket",
            "name": "Create Zendesk Ticket",
            "description": "Create a ticket",
            "params": {"subject": "string"},
        },
        {
            "id": "update_ticket",
            "name": "Update Zendesk Ticket",
            "description": "Update a ticket",
            "params": {"ticket_id": "integer"},
        },
        {
            "id": "list_users",
            "name": "List Zendesk Users",
            "description": "List users",
            "params": {"page": "integer", "per_page": "integer"},
        },
        {
            "id": "get_user",
            "name": "Get Zendesk User",
            "description": "Get user details",
            "params": {"user_id": "integer"},
        },
        {
            "id": "search_tickets",
            "name": "Search Zendesk Tickets",
            "description": "Search tickets with query syntax",
            "params": {"query": "string"},
        },
        {
            "id": "list_organizations",
            "name": "List Zendesk Organizations",
            "description": "List organizations",
            "params": {"page": "integer"},
        },
        {
            "id": "list_groups",
            "name": "List Zendesk Groups",
            "description": "List agent groups",
            "params": {"page": "integer"},
        },
        {
            "id": "add_ticket_comment",
            "name": "Add Zendesk Ticket Comment",
            "description": "Add a comment to a ticket",
            "params": {"ticket_id": "integer", "comment_body": "string"},
        },
        {
            "id": "list_ticket_metrics",
            "name": "List Zendesk Ticket Metrics",
            "description": "List ticket metrics",
            "params": {"page": "integer"},
        },
    ],
    "monday": [
        {"id": "get_me", "name": "Get Monday User", "description": "Get current user info", "params": {}},
        {
            "id": "list_boards",
            "name": "List Monday Boards",
            "description": "List boards",
            "params": {"limit": "integer"},
        },
        {
            "id": "get_board",
            "name": "Get Monday Board",
            "description": "Get board details with columns and groups",
            "params": {"board_id": "string"},
        },
        {
            "id": "list_items",
            "name": "List Monday Items",
            "description": "List items in a board",
            "params": {"board_id": "string", "limit": "integer"},
        },
        {
            "id": "get_item",
            "name": "Get Monday Item",
            "description": "Get item details with column values",
            "params": {"item_id": "string"},
        },
        {
            "id": "create_item",
            "name": "Create Monday Item",
            "description": "Create an item in a board",
            "params": {"board_id": "string", "item_name": "string"},
        },
        {
            "id": "update_item",
            "name": "Update Monday Item",
            "description": "Update item column values",
            "params": {"item_id": "string", "board_id": "string", "column_values": "string"},
        },
        {
            "id": "create_update",
            "name": "Create Monday Update (Comment)",
            "description": "Add a comment/update to an item",
            "params": {"item_id": "string", "body": "string"},
        },
        {
            "id": "list_users",
            "name": "List Monday Users",
            "description": "List workspace users",
            "params": {"limit": "integer"},
        },
        {"id": "list_workspaces", "name": "List Monday Workspaces", "description": "List workspaces", "params": {}},
    ],
    "telegram": [
        {
            "id": "get_me",
            "name": "Get Telegram Bot Info",
            "description": "Get bot info (credential validation)",
            "params": {},
        },
        {
            "id": "send_message",
            "name": "Send Telegram Message",
            "description": "Send a text message to a chat",
            "params": {"chat_id": "string", "text": "string"},
        },
        {
            "id": "send_photo",
            "name": "Send Telegram Photo",
            "description": "Send a photo (URL or file_id)",
            "params": {"chat_id": "string", "photo": "string"},
        },
        {
            "id": "send_document",
            "name": "Send Telegram Document",
            "description": "Send a file/document",
            "params": {"chat_id": "string", "document": "string"},
        },
        {
            "id": "edit_message",
            "name": "Edit Telegram Message",
            "description": "Edit a previously sent message",
            "params": {"chat_id": "string", "message_id": "integer", "text": "string"},
        },
        {
            "id": "delete_message",
            "name": "Delete Telegram Message",
            "description": "Delete a message",
            "params": {"chat_id": "string", "message_id": "integer"},
        },
        {
            "id": "forward_message",
            "name": "Forward Telegram Message",
            "description": "Forward a message to another chat",
            "params": {"chat_id": "string", "from_chat_id": "string", "message_id": "integer"},
        },
        {
            "id": "get_chat",
            "name": "Get Telegram Chat Info",
            "description": "Get chat info",
            "params": {"chat_id": "string"},
        },
        {
            "id": "get_chat_member",
            "name": "Get Telegram Chat Member",
            "description": "Get info about a chat member",
            "params": {"chat_id": "string", "user_id": "integer"},
        },
        {
            "id": "pin_message",
            "name": "Pin Telegram Message",
            "description": "Pin a message in a chat",
            "params": {"chat_id": "string", "message_id": "integer"},
        },
        {
            "id": "set_webhook",
            "name": "Set Telegram Webhook",
            "description": "Configure webhook URL for bot updates",
            "params": {"url": "string"},
        },
        {
            "id": "get_updates",
            "name": "Get Telegram Updates",
            "description": "Poll for updates (alternative to webhook)",
            "params": {"limit": "integer"},
        },
    ],
}
# These skip the per-user OAuth token DB lookup entirely.
# Add new entries here when building API-key-backed connectors.

_NON_OAUTH_CONFIGS: dict[str, dict[str, Any]] = {
    "linear": {
        "name": "linear-workspace",
        "auth_type": "api_key",
        "label": "Linear API key",
    },
    "discord": {
        "name": "discord-bot",
        "auth_type": "bearer_token",
        "label": "Discord bot token",
    },
    "apiflow": {
        "name": "apiflow-instance",
        "auth_type": "api_key",
        "label": "Apiflow API key + instance URL",
    },
    "sentry": {
        "name": "sentry-instance",
        "auth_type": "bearer_token",
        "label": "Sentry API token",
    },
    "twilio": {
        "name": "twilio-instance",
        "auth_type": "api_key",
        "label": "Twilio API Key SID + Secret",
    },
    "telegram": {
        "name": "telegram-bot",
        "auth_type": "api_key",
        "label": "Telegram Bot Token",
    },
}


# ── Bridge Service ────────────────────────────────────────────────────


@dataclass
class IntegrationCapabilityRegistration:
    """Tracks a user's registered integration capability IDs."""

    user_id: int
    slug: str
    capability_ids: list[str] = field(default_factory=list)


class IntegrationBridge:
    """
    Bridges OAuth token storage to the Nexus capability system.

    Responsibilities:
    - Register/unregister integration capabilities per user
    - Create live connector instances backed by encrypted tokens
    - Re-register all active connections on startup
    """

    def __init__(self):
        self._active_registrations: dict[str, IntegrationCapabilityRegistration] = {}

    @staticmethod
    def _registration_key(user_id: int, slug: str) -> str:
        return f"{user_id}:{slug}"

    # ── Capability Registration ─────────────────────────────────

    async def register_capabilities_for_user(
        self,
        user_id: int,
        slug: str,
    ) -> list[str]:
        """
        Register all capabilities for a user's integration in Nexus.

        Called after OAuth callback stores the token.
        """
        capabilities = _INTEGRATION_CAPABILITIES.get(slug)
        if not capabilities:
            logger.debug("No Nexus capabilities defined for integration: %s", slug)
            return []

        try:
            from app.services.nexus.capability_registry import (
                Capability,
                get_capability_registry,
            )

            registry = get_capability_registry()
            registered_ids: list[str] = []

            for cap_def in capabilities:
                cap_id = f"integration:{slug}:{cap_def['id']}"
                try:
                    # Build input schema from params
                    properties = {}
                    for pname, ptype in cap_def.get("params", {}).items():
                        properties[pname] = {"type": ptype}

                    # Create a handler that executes the action via the bridge
                    async def make_handler(uid=user_id, s=slug, action=cap_def["id"]):
                        async def handler(params: dict[str, Any]) -> dict[str, Any]:
                            bridge = get_integration_bridge()
                            result = await bridge.execute_integration_action(uid, s, action, params)
                            if result.success:
                                return {"success": True, "data": result.data}
                            return {"success": False, "error": result.error}

                        return handler

                    capability = Capability(
                        id=cap_id,
                        name=cap_def["name"],
                        description=f"[Integration: {slug}] {cap_def['description']}",
                        category=f"integration:{slug}",
                        handler=await make_handler(),
                        input_schema={
                            "type": "object",
                            "properties": properties,
                        },
                        requires_auth=True,
                        metadata={
                            "user_id": user_id,
                            "integration_slug": slug,
                            "action": cap_def["id"],
                            "source": "integration",
                        },
                    )

                    # Register — this replaces any previous registration
                    registry.register(capability)
                    registered_ids.append(cap_id)
                    logger.debug(
                        "Registered Nexus capability: %s for user %s",
                        cap_id,
                        user_id,
                    )

                except Exception as e:
                    logger.warning(
                        "Failed to register capability %s for user %s: %s",
                        cap_def["id"],
                        user_id,
                        e,
                    )

            # Track the registration
            key = self._registration_key(user_id, slug)
            self._active_registrations[key] = IntegrationCapabilityRegistration(
                user_id=user_id,
                slug=slug,
                capability_ids=registered_ids,
            )

            logger.info(
                "Registered %d Nexus capabilities for user %s integration %s",
                len(registered_ids),
                user_id,
                slug,
            )

            return registered_ids

        except Exception as e:
            logger.warning(
                "Failed to register capabilities for user %s, %s: %s",
                user_id,
                slug,
                e,
            )
            return []

    async def unregister_capabilities_for_user(
        self,
        user_id: int,
        slug: str,
    ) -> int:
        """
        Unregister all Nexus capabilities for a user's integration.

        Called on disconnect.
        """
        key = self._registration_key(user_id, slug)
        reg = self._active_registrations.pop(key, None)

        if not reg or not reg.capability_ids:
            logger.debug("No capabilities to unregister for user %s, %s", user_id, slug)
            return 0

        try:
            from app.services.nexus.capability_registry import get_capability_registry

            registry = get_capability_registry()
            unregistered = 0

            for cap_id in reg.capability_ids:
                if registry.unregister(cap_id):
                    unregistered += 1

            logger.info(
                "Unregistered %d Nexus capabilities for user %s integration %s",
                unregistered,
                user_id,
                slug,
            )

            return unregistered

        except Exception as e:
            logger.warning(
                "Failed to unregister capabilities for user %s, %s: %s",
                user_id,
                slug,
                e,
            )
            return 0

    # ── Non-OAuth Connector Factory ───────────────────────────

    @staticmethod
    async def _get_non_oauth_connector(slug: str):
        """
        Create a connector for non-OAuth integrations (API key, bot token, etc.).

        Looks up slug in _NON_OAUTH_CONFIGS and creates a ConnectorConfig with
        the appropriate auth type. Settings/env vars provide the actual credential.
        """
        from app.services.connectors import AuthType, ConnectorConfig, ConnectorManager

        cfg = _NON_OAUTH_CONFIGS.get(slug)
        if not cfg:
            logger.warning("No non-OAuth config for: %s", slug)
            return None

        manager = ConnectorManager()
        cls = manager.get_connector_class(slug)
        if not cls:
            logger.warning("No connector class for: %s", slug)
            return None

        # Map auth type string to AuthType enum
        try:
            auth_type = getattr(AuthType, cfg["auth_type"].upper())
        except AttributeError:
            logger.error(
                "Non-OAuth config for %s has unknown auth_type: %s",
                slug,
                cfg["auth_type"],
            )
            return None

        config = ConnectorConfig(
            name=cfg["name"],
            connector_type=slug,
            auth_type=auth_type,
            auth_config={},
        )

        connector = cls(config)
        connected = await connector.connect()
        if not connected:
            logger.warning("Failed to connect %s connector (check %s)", slug, cfg["label"])
            return None

        return connector

    # ── Token-Backed Connector Factory ──────────────────────────

    async def get_connector_for_user(
        self,
        user_id: int,
        slug: str,
    ):
        """
        Create a live connector instance backed by the user's encrypted token.

        Automatically refreshes expired Google OAuth tokens before use.
        Returns None if no active connection exists.

        API-key integrations (e.g., Linear) skip the OAuth token flow entirely.
        """
        # ── Non-OAuth integrations (API key / bot token) ──
        if slug in _NON_OAUTH_CONFIGS:
            return await self._get_non_oauth_connector(slug)

        from app.database import AsyncSessionLocal

        async with AsyncSessionLocal() as session:
            return await self._get_connector(session, user_id, slug)

    async def _get_connector(
        self,
        db: AsyncSession,
        user_id: int,
        slug: str,
    ):
        from app.models.phase4_models import IntegrationConnection
        from app.services.connectors import AuthType, ConnectorConfig, ConnectorManager

        result = await db.execute(
            select(IntegrationConnection).where(
                IntegrationConnection.user_id == user_id,
                IntegrationConnection.integration_slug == slug,
                IntegrationConnection.is_active.is_(True),
            )
        )
        conn = result.scalar_one_or_none()

        if not conn or not conn.encrypted_access_token:
            logger.warning("No active token for user %s, integration %s", user_id, slug)
            return None

        # Decrypt the token
        try:
            access_token = decrypt_token(conn.encrypted_access_token)
        except Exception as e:
            logger.error("Failed to decrypt token for user %s, %s: %s", user_id, slug, e)
            return None

        # ── Auto-refresh expired Google OAuth tokens ─────────────
        if slug == "google" and conn.encrypted_refresh_token:
            try:
                new_token = await self._refresh_google_token(decrypt_token(conn.encrypted_refresh_token))
                if new_token:
                    # Encrypt and store the fresh token
                    conn.encrypted_access_token = encrypt_token(new_token["access_token"])
                    if new_token.get("refresh_token"):
                        conn.encrypted_refresh_token = encrypt_token(new_token["refresh_token"])
                    if new_token.get("expires_in"):
                        from datetime import timedelta

                        conn.expires_at = datetime.now(UTC).replace(tzinfo=None) + timedelta(
                            seconds=int(new_token["expires_in"])
                        )
                    await db.commit()
                    access_token = new_token["access_token"]
                    logger.info(
                        "Refreshed Google token for user %s (expires in %ss)",
                        user_id,
                        new_token.get("expires_in", "?"),
                    )
            except Exception as e:
                logger.warning("Failed to refresh Google token for user %s: %s", user_id, e)
                # Fall through — try the existing token anyway in case it's still valid

        # ── Auto-refresh expired Jira (Atlassian) OAuth tokens ──
        if slug == "jira" and conn.encrypted_refresh_token:
            try:
                new_token = await self._refresh_oauth_token("jira", decrypt_token(conn.encrypted_refresh_token))
                if new_token:
                    conn.encrypted_access_token = encrypt_token(new_token["access_token"])
                    if new_token.get("refresh_token"):
                        conn.encrypted_refresh_token = encrypt_token(new_token["refresh_token"])
                    if new_token.get("expires_in"):
                        from datetime import timedelta

                        conn.expires_at = datetime.now(UTC).replace(tzinfo=None) + timedelta(
                            seconds=int(new_token["expires_in"])
                        )
                    await db.commit()
                    access_token = new_token["access_token"]
                    logger.info(
                        "Refreshed Jira token for user %s (expires in %ss)",
                        user_id,
                        new_token.get("expires_in", "?"),
                    )
            except Exception as e:
                logger.warning("Failed to refresh Jira token for user %s: %s", user_id, e)
                # Fall through — try the existing token anyway in case it's still valid

        # ── Auto-refresh expired Confluence (Atlassian) OAuth tokens ──
        if slug == "confluence" and conn.encrypted_refresh_token:
            try:
                new_token = await self._refresh_oauth_token("confluence", decrypt_token(conn.encrypted_refresh_token))
                if new_token:
                    conn.encrypted_access_token = encrypt_token(new_token["access_token"])
                    if new_token.get("refresh_token"):
                        conn.encrypted_refresh_token = encrypt_token(new_token["refresh_token"])
                    if new_token.get("expires_in"):
                        from datetime import timedelta

                        conn.expires_at = datetime.now(UTC).replace(tzinfo=None) + timedelta(
                            seconds=int(new_token["expires_in"])
                        )
                    await db.commit()
                    access_token = new_token["access_token"]
                    logger.info(
                        "Refreshed Confluence token for user %s (expires in %ss)",
                        user_id,
                        new_token.get("expires_in", "?"),
                    )
            except Exception as e:
                logger.warning("Failed to refresh Confluence token for user %s: %s", user_id, e)
                # Fall through — try the existing token anyway in case it's still valid

        # ── Auto-refresh expired Figma OAuth tokens ──────────────
        if slug == "figma" and conn.encrypted_refresh_token:
            try:
                new_token = await self._refresh_oauth_token("figma", decrypt_token(conn.encrypted_refresh_token))
                if new_token:
                    conn.encrypted_access_token = encrypt_token(new_token["access_token"])
                    if new_token.get("refresh_token"):
                        conn.encrypted_refresh_token = encrypt_token(new_token["refresh_token"])
                    if new_token.get("expires_in"):
                        from datetime import timedelta

                        conn.expires_at = datetime.now(UTC).replace(tzinfo=None) + timedelta(
                            seconds=int(new_token["expires_in"])
                        )
                    await db.commit()
                    access_token = new_token["access_token"]
                    logger.info(
                        "Refreshed Figma token for user %s (expires in %ss)",
                        user_id,
                        new_token.get("expires_in", "?"),
                    )
            except Exception as e:
                logger.warning("Failed to refresh Figma token for user %s: %s", user_id, e)
                # Fall through — try the existing token anyway in case it's still valid

        # ── Auto-refresh expired Stripe OAuth tokens ──────────────
        if slug == "stripe" and conn.encrypted_refresh_token:
            try:
                new_token = await self._refresh_oauth_token("stripe", decrypt_token(conn.encrypted_refresh_token))
                if new_token:
                    conn.encrypted_access_token = encrypt_token(new_token["access_token"])
                    if new_token.get("refresh_token"):
                        conn.encrypted_refresh_token = encrypt_token(new_token["refresh_token"])
                    if new_token.get("expires_in"):
                        from datetime import timedelta

                        conn.expires_at = datetime.now(UTC).replace(tzinfo=None) + timedelta(
                            seconds=int(new_token["expires_in"])
                        )
                    await db.commit()
                    access_token = new_token["access_token"]
                    logger.info(
                        "Refreshed Stripe token for user %s (expires in %ss)",
                        user_id,
                        new_token.get("expires_in", "?"),
                    )
            except Exception as e:
                logger.warning("Failed to refresh Stripe token for user %s: %s", user_id, e)
                # Fall through — try the existing token anyway in case it's still valid

        # ── Auto-refresh expired PagerDuty OAuth tokens ────────────
        if slug == "pagerduty" and conn.encrypted_refresh_token:
            try:
                new_token = await self._refresh_oauth_token("pagerduty", decrypt_token(conn.encrypted_refresh_token))
                if new_token:
                    conn.encrypted_access_token = encrypt_token(new_token["access_token"])
                    if new_token.get("refresh_token"):
                        conn.encrypted_refresh_token = encrypt_token(new_token["refresh_token"])
                    if new_token.get("expires_in"):
                        from datetime import timedelta

                        conn.expires_at = datetime.now(UTC).replace(tzinfo=None) + timedelta(
                            seconds=int(new_token["expires_in"])
                        )
                    await db.commit()
                    access_token = new_token["access_token"]
                    logger.info(
                        "Refreshed PagerDuty token for user %s (expires in %ss)",
                        user_id,
                        new_token.get("expires_in", "?"),
                    )
            except Exception as e:
                logger.warning("Failed to refresh PagerDuty token for user %s: %s", user_id, e)
                # Fall through — try the existing token anyway in case it's still valid

        # ── Auto-refresh expired Datadog OAuth tokens ──────────────
        if slug == "datadog" and conn.encrypted_refresh_token:
            try:
                new_token = await self._refresh_oauth_token("datadog", decrypt_token(conn.encrypted_refresh_token))
                if new_token:
                    conn.encrypted_access_token = encrypt_token(new_token["access_token"])
                    if new_token.get("refresh_token"):
                        conn.encrypted_refresh_token = encrypt_token(new_token["refresh_token"])
                    if new_token.get("expires_in"):
                        from datetime import timedelta

                        conn.expires_at = datetime.now(UTC).replace(tzinfo=None) + timedelta(
                            seconds=int(new_token["expires_in"])
                        )
                    await db.commit()
                    access_token = new_token["access_token"]
                    logger.info(
                        "Refreshed Datadog token for user %s (expires in %ss)",
                        user_id,
                        new_token.get("expires_in", "?"),
                    )
            except Exception as e:
                logger.warning("Failed to refresh Datadog token for user %s: %s", user_id, e)
                # Fall through — try the existing token anyway in case it's still valid

        # ── Auto-refresh expired Airtable OAuth tokens ─────────────
        if slug == "airtable" and conn.encrypted_refresh_token:
            try:
                new_token = await self._refresh_oauth_token("airtable", decrypt_token(conn.encrypted_refresh_token))
                if new_token:
                    conn.encrypted_access_token = encrypt_token(new_token["access_token"])
                    if new_token.get("refresh_token"):
                        conn.encrypted_refresh_token = encrypt_token(new_token["refresh_token"])
                    if new_token.get("expires_in"):
                        from datetime import timedelta

                        conn.expires_at = datetime.now(UTC).replace(tzinfo=None) + timedelta(
                            seconds=int(new_token["expires_in"])
                        )
                    await db.commit()
                    access_token = new_token["access_token"]
                    logger.info(
                        "Refreshed Airtable token for user %s (expires in %ss)",
                        user_id,
                        new_token.get("expires_in", "?"),
                    )
            except Exception as e:
                logger.warning("Failed to refresh Airtable token for user %s: %s", user_id, e)
                # Fall through — try the existing token anyway in case it's still valid

        # ── Auto-refresh expired Asana OAuth tokens ──────────────
        if slug == "asana" and conn.encrypted_refresh_token:
            try:
                new_token = await self._refresh_oauth_token("asana", decrypt_token(conn.encrypted_refresh_token))
                if new_token:
                    conn.encrypted_access_token = encrypt_token(new_token["access_token"])
                    if new_token.get("refresh_token"):
                        conn.encrypted_refresh_token = encrypt_token(new_token["refresh_token"])
                    if new_token.get("expires_in"):
                        from datetime import timedelta

                        conn.expires_at = datetime.now(UTC).replace(tzinfo=None) + timedelta(
                            seconds=int(new_token["expires_in"])
                        )
                    await db.commit()
                    access_token = new_token["access_token"]
                    logger.info(
                        "Refreshed Asana token for user %s (expires in %ss)",
                        user_id,
                        new_token.get("expires_in", "?"),
                    )
            except Exception as e:
                logger.warning("Failed to refresh Asana token for user %s: %s", user_id, e)
                # Fall through — try the existing token anyway in case it's still valid

        # ── Auto-refresh expired GitLab OAuth tokens ──────────────
        if slug == "gitlab" and conn.encrypted_refresh_token:
            try:
                new_token = await self._refresh_oauth_token("gitlab", decrypt_token(conn.encrypted_refresh_token))
                if new_token:
                    conn.encrypted_access_token = encrypt_token(new_token["access_token"])
                    if new_token.get("refresh_token"):
                        conn.encrypted_refresh_token = encrypt_token(new_token["refresh_token"])
                    if new_token.get("expires_in"):
                        from datetime import timedelta

                        conn.expires_at = datetime.now(UTC).replace(tzinfo=None) + timedelta(
                            seconds=int(new_token["expires_in"])
                        )
                    await db.commit()
                    access_token = new_token["access_token"]
                    logger.info(
                        "Refreshed GitLab token for user %s (expires in %ss)",
                        user_id,
                        new_token.get("expires_in", "?"),
                    )
            except Exception as e:
                logger.warning("Failed to refresh GitLab token for user %s: %s", user_id, e)
                # Fall through — try the existing token anyway in case it's still valid

        # ── Auto-refresh expired HubSpot OAuth tokens ────────────
        # Critical: HubSpot refresh tokens may rotate on each refresh.
        if slug == "hubspot" and conn.encrypted_refresh_token:
            try:
                new_token = await self._refresh_oauth_token("hubspot", decrypt_token(conn.encrypted_refresh_token))
                if new_token:
                    conn.encrypted_access_token = encrypt_token(new_token["access_token"])
                    if new_token.get("refresh_token"):
                        conn.encrypted_refresh_token = encrypt_token(new_token["refresh_token"])
                    if new_token.get("expires_in"):
                        from datetime import timedelta

                        conn.expires_at = datetime.now(UTC).replace(tzinfo=None) + timedelta(
                            seconds=int(new_token["expires_in"])
                        )
                    await db.commit()
                    access_token = new_token["access_token"]
                    logger.info(
                        "Refreshed HubSpot token for user %s (expires in %ss)",
                        user_id,
                        new_token.get("expires_in", "?"),
                    )
            except Exception as e:
                logger.warning("Failed to refresh HubSpot token for user %s: %s", user_id, e)
                # Fall through — try the existing token anyway in case it's still valid

        # Note: ClickUp tokens do NOT expire — no refresh needed.
        # Note: Twilio uses API Key auth — non-OAuth, skipped above.

        # ── Jira + Confluence: extract cloudId from account_id ──
        extra_auth_config: dict[str, str] = {}
        if slug in ("jira", "confluence"):
            cloud_id = conn.account_id
            if not cloud_id:
                logger.warning("No cloudId for user %s %s connection", user_id, slug)
                return None
            extra_auth_config["cloud_id"] = cloud_id

        # Create connector config with the (possibly refreshed) decrypted token
        auth_config: dict[str, Any] = {"access_token": access_token, **extra_auth_config}
        config = ConnectorConfig(
            name=f"{slug}-user-{user_id}",
            connector_type=slug,
            auth_type=AuthType.OAUTH2,
            auth_config=auth_config,
        )

        manager = ConnectorManager()
        cls = manager.get_connector_class(slug)
        if not cls:
            logger.warning("No connector class for: %s", slug)
            return None

        connector = cls(config)
        connected = await connector.connect()
        if not connected:
            logger.warning("Failed to connect %s connector for user %s", slug, user_id)
            return None

        return connector

    # ── Action Execution ────────────────────────────────────────

    async def execute_integration_action(
        self,
        user_id: int,
        slug: str,
        action: str,
        params: dict[str, Any],
    ) -> Any:
        """
        Execute an integration action on behalf of a user.

        This is called by the Nexus capability handlers registered above.
        """
        connector = await self.get_connector_for_user(user_id, slug)
        if not connector:
            from app.services.connectors.base import ConnectorResponse

            return ConnectorResponse(
                success=False,
                error=f"No active {slug} connection for user {user_id}",
                status_code=401,
            )

        try:
            result = await connector.execute_action(action, params)
            return result
        finally:
            await connector.disconnect()

    # ── Token Refresh ───────────────────────────────────────────

    @staticmethod
    async def _refresh_google_token(refresh_token: str) -> dict[str, Any] | None:
        """
        Exchange a Google refresh token for a fresh access token.

        Returns {'access_token': ..., 'expires_in': ..., 'refresh_token': ...}
        or None on failure.
        """
        provider = OAUTH_PROVIDERS.get("google")
        if not provider or not provider.is_configured:
            logger.warning("Google OAuth provider not configured — cannot refresh token")
            return None

        data = {
            "client_id": provider.client_id,
            "client_secret": provider.client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        }

        async with httpx.AsyncClient() as client:
            resp = await client.post(provider.token_url, data=data)

        if resp.status_code != 200:
            logger.warning(
                "Google token refresh failed: %s %s",
                resp.status_code,
                resp.text[:200],
            )
            return None

        return resp.json()

    @staticmethod
    async def _refresh_oauth_token(slug: str, refresh_token: str) -> dict[str, Any] | None:
        """
        Generic OAuth2 refresh — works for any provider that uses the standard
        `grant_type=refresh_token` flow at the same token_url.

        Used by Jira, Confluence, Figma, and future standard OAuth2 providers.
        Returns {'access_token': ..., 'expires_in': ..., 'refresh_token': ...}
        or None on failure.
        """
        provider = OAUTH_PROVIDERS.get(slug)
        if not provider or not provider.is_configured:
            logger.warning("OAuth provider '%s' not configured — cannot refresh token", slug)
            return None

        data = {
            "client_id": provider.client_id,
            "client_secret": provider.client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        }

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                provider.token_url,
                data=data,
                headers={"Accept": "application/json"},
            )

        if resp.status_code != 200:
            logger.warning(
                "%s token refresh failed: %s %s",
                slug,
                resp.status_code,
                resp.text[:200],
            )
            return None

        return resp.json()

    # ── Startup Re-Registration ────────────────────────────────

    async def register_all_active_connections(self) -> int:
        """
        Re-register Nexus capabilities for all active integration connections.

        Called at application startup.
        """
        from app.database import AsyncSessionLocal
        from app.models.phase4_models import IntegrationConnection

        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(IntegrationConnection).where(
                    IntegrationConnection.is_active.is_(True),
                    IntegrationConnection.encrypted_access_token.is_not(None),
                )
            )
            connections = result.scalars().all()

        total = 0
        for conn in connections:
            try:
                registered = await self.register_capabilities_for_user(
                    user_id=conn.user_id,
                    slug=conn.integration_slug,
                )
                total += len(registered)
            except Exception as e:
                logger.warning(
                    "Failed to re-register capabilities for user %s, %s: %s",
                    conn.user_id,
                    conn.integration_slug,
                    e,
                )

        logger.info(
            "Startup: re-registered %d Nexus capabilities from %d active connections",
            total,
            len(connections),
        )
        return total


# ── Singleton ─────────────────────────────────────────────────────────

_bridge: IntegrationBridge | None = None


def get_integration_bridge() -> IntegrationBridge:
    """Get or create the singleton IntegrationBridge instance."""
    global _bridge
    if _bridge is None:
        _bridge = IntegrationBridge()
    return _bridge
