"""Integration Playground Service — executes demo actions for the "Try before you connect" feature.

Uses demo credentials from the vault when available, otherwise returns
high-fidelity mock responses so users can still see what an integration
does without connecting their own account.

All actions are rate-limited (5 req/min/user/integration) and scoped to
sandbox resources only.
"""

from __future__ import annotations

import logging
import time
from typing import Any

import httpx

from app.core.demo_credentials import get_demo_credential, has_real_credentials

logger = logging.getLogger(__name__)

# ── Playground action dispatch ────────────────────────────────────────────


async def execute_playground_action(
    *,
    slug: str,
    action: str,
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Execute a playground demo action for an integration.

    Args:
        slug: Integration slug (e.g., "slack", "github").
        action: Demo action name (e.g., "list_channels", "list_repos").
        params: Optional action parameters (most playground actions need none).

    Returns:
        Dict with ``success``, ``response`` (action output), ``error`` (on failure),
        and ``is_mock`` (bool indicating if the response was simulated).
    """
    params = params or {}
    cred = get_demo_credential(slug)

    # Try real API call if we have credentials
    if cred and cred.token:
        try:
            result = await _dispatch_real(slug, action, params, cred.token)
            result["is_mock"] = False
            return result
        except Exception as exc:
            logger.warning(
                "Playground real call failed for %s/%s: %s",
                slug,
                action,
                exc,
            )
            # Return the error — don't silently show mock data when credentials
            # exist.  The user should know the real call failed.
            return {
                "success": False,
                "is_mock": False,
                "error": f"Live call to {slug} failed: {exc}",
            }

    # No credentials available — return mock response
    return _dispatch_mock(slug, action, params)


# ── Real API dispatch ─────────────────────────────────────────────────────


async def _dispatch_real(
    slug: str,
    action: str,
    params: dict[str, Any],
    token: str,
) -> dict[str, Any]:
    """Execute a playground action against the real API using demo credentials."""
    handler = _REAL_HANDLERS.get((slug, action))
    if not handler:
        return {
            "success": False,
            "error": f"No real handler for {slug}/{action}",
        }
    return await handler(params, token)


async def _slack_list_channels(params: dict[str, Any], token: str) -> dict[str, Any]:
    """List channels in the demo Slack workspace."""
    limit = min(int(params.get("limit", 20)), 50)
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(
            "https://slack.com/api/conversations.list",
            params={"limit": limit, "types": "public_channel"},
            headers={"Authorization": f"Bearer {token}"},
        )
        data = resp.json()
        if not data.get("ok"):
            return {"success": False, "error": data.get("error", "Unknown Slack error")}
        channels = [
            {"id": ch["id"], "name": ch["name"], "members": ch.get("num_members", 0)} for ch in data.get("channels", [])
        ]
        return {"success": True, "response": {"channels": channels, "count": len(channels)}}


async def _slack_send_message(params: dict[str, Any], token: str) -> dict[str, Any]:
    """Send a test message to #flowmanner-playground."""
    text = params.get("text", "Hello from Flowmanner Playground! 👋")
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(
            "https://slack.com/api/chat.postMessage",
            json={"channel": "#flowmanner-playground", "text": text},
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json; charset=utf-8",
            },
        )
        data = resp.json()
        if not data.get("ok"):
            return {"success": False, "error": data.get("error", "Unknown Slack error")}
        return {
            "success": True,
            "response": {
                "channel": data.get("channel"),
                "ts": data.get("ts"),
                "text": text,
            },
        }


async def _github_list_repos(params: dict[str, Any], token: str) -> dict[str, Any]:
    """List repos in the flowmanner-demo GitHub org."""
    limit = min(int(params.get("limit", 10)), 30)
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(
            "https://api.github.com/orgs/flowmanner-demo/repos",
            params={"per_page": limit, "type": "public", "sort": "updated"},
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github.v3+json",
            },
        )
        if resp.status_code >= 400:
            return {"success": False, "error": f"GitHub API error: {resp.status_code}"}
        repos = resp.json()
        return {
            "success": True,
            "response": {
                "repos": [
                    {
                        "name": r["name"],
                        "description": r.get("description", ""),
                        "stars": r.get("stargazers_count", 0),
                        "language": r.get("language"),
                        "url": r["html_url"],
                    }
                    for r in repos
                ],
                "count": len(repos),
            },
        }


async def _github_show_repo(params: dict[str, Any], token: str) -> dict[str, Any]:
    """Show details of a demo repo (first repo in the org if not specified)."""
    repo = params.get("repo", "")
    async with httpx.AsyncClient(timeout=15.0) as client:
        if not repo:
            # Get the first repo
            repos_resp = await client.get(
                "https://api.github.com/orgs/flowmanner-demo/repos",
                params={"per_page": 1, "type": "public"},
                headers={
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/vnd.github.v3+json",
                },
            )
            if repos_resp.status_code >= 400 or not repos_resp.json():
                return {"success": False, "error": "No repos found in flowmanner-demo org"}
            repo = repos_resp.json()[0]["name"]

        resp = await client.get(
            f"https://api.github.com/repos/flowmanner-demo/{repo}",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github.v3+json",
            },
        )
        if resp.status_code >= 400:
            return {"success": False, "error": f"GitHub API error: {resp.status_code}"}
        data = resp.json()
        return {
            "success": True,
            "response": {
                "name": data["name"],
                "description": data.get("description", ""),
                "stars": data.get("stargazers_count", 0),
                "forks": data.get("forks_count", 0),
                "language": data.get("language"),
                "created_at": data.get("created_at"),
                "url": data["html_url"],
            },
        }


async def _notion_list_pages(params: dict[str, Any], token: str) -> dict[str, Any]:
    """List pages in the demo Notion workspace."""
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(
            "https://api.notion.com/v1/search",
            json={"page_size": min(int(params.get("limit", 10)), 20)},
            headers={
                "Authorization": f"Bearer {token}",
                "Notion-Version": "2022-06-28",
                "Content-Type": "application/json",
            },
        )
        if resp.status_code >= 400:
            return {"success": False, "error": f"Notion API error: {resp.status_code}"}
        data = resp.json()
        pages = []
        for result in data.get("results", []):
            title_parts = result.get("properties", {}).get("title", {}).get("title", [])
            title = title_parts[0]["plain_text"] if title_parts else "Untitled"
            pages.append(
                {
                    "id": result["id"],
                    "title": title,
                    "url": result.get("url", ""),
                    "created_at": result.get("created_time", ""),
                }
            )
        return {"success": True, "response": {"pages": pages, "count": len(pages)}}


async def _discord_send_message(params: dict[str, Any], token: str) -> dict[str, Any]:
    """Send a test message to a demo Discord channel."""
    # First get the channel ID for #playground
    async with httpx.AsyncClient(timeout=15.0) as client:
        guilds_resp = await client.get(
            "https://discord.com/api/v10/users/@me/guilds",
            headers={"Authorization": f"Bot {token}"},
        )
        if guilds_resp.status_code >= 400:
            return {"success": False, "error": "Failed to list Discord guilds"}

        guilds = guilds_resp.json()
        if not guilds:
            return {"success": False, "error": "Bot is not in any guilds"}

        guild_id = guilds[0]["id"]
        channels_resp = await client.get(
            f"https://discord.com/api/v10/guilds/{guild_id}/channels",
            headers={"Authorization": f"Bot {token}"},
        )
        if channels_resp.status_code >= 400:
            return {"success": False, "error": "Failed to list Discord channels"}

        # Find a text channel named "playground" or use the first text channel
        channels = channels_resp.json()
        target_channel = None
        for ch in channels:
            if ch.get("type") == 0:  # TEXT channel
                if ch["name"] == "playground":
                    target_channel = ch
                    break
                if target_channel is None:
                    target_channel = ch

        if not target_channel:
            return {"success": False, "error": "No text channels found"}

        text = params.get("text", "Hello from Flowmanner Playground! 👋")
        msg_resp = await client.post(
            f"https://discord.com/api/v10/channels/{target_channel['id']}/messages",
            json={"content": text},
            headers={"Authorization": f"Bot {token}"},
        )
        if msg_resp.status_code >= 400:
            return {"success": False, "error": f"Failed to send message: {msg_resp.status_code}"}

        msg_data = msg_resp.json()
        return {
            "success": True,
            "response": {
                "channel": target_channel["name"],
                "message_id": msg_data["id"],
                "text": text,
            },
        }


async def _discord_list_channels(params: dict[str, Any], token: str) -> dict[str, Any]:
    """List channels in the demo Discord server."""
    async with httpx.AsyncClient(timeout=15.0) as client:
        guilds_resp = await client.get(
            "https://discord.com/api/v10/users/@me/guilds",
            headers={"Authorization": f"Bot {token}"},
        )
        if guilds_resp.status_code >= 400:
            return {"success": False, "error": "Failed to list Discord guilds"}

        guilds = guilds_resp.json()
        if not guilds:
            return {"success": False, "error": "Bot is not in any guilds"}

        guild_id = guilds[0]["id"]
        channels_resp = await client.get(
            f"https://discord.com/api/v10/guilds/{guild_id}/channels",
            headers={"Authorization": f"Bot {token}"},
        )
        if channels_resp.status_code >= 400:
            return {"success": False, "error": "Failed to list Discord channels"}

        channels = [
            {"id": ch["id"], "name": ch["name"], "type": ch["type"]}
            for ch in channels_resp.json()
            if ch.get("type") == 0  # TEXT channels only
        ]
        return {"success": True, "response": {"channels": channels, "count": len(channels)}}


_REAL_HANDLERS: dict[tuple[str, str], Any] = {
    ("slack", "list_channels"): _slack_list_channels,
    ("slack", "send_message"): _slack_send_message,
    ("github", "list_repos"): _github_list_repos,
    ("github", "show_repo"): _github_show_repo,
    ("notion", "list_pages"): _notion_list_pages,
    ("discord", "send_message"): _discord_send_message,
    ("discord", "list_channels"): _discord_list_channels,
}


# ── Mock response dispatch ────────────────────────────────────────────────


def _dispatch_mock(slug: str, action: str, params: dict[str, Any]) -> dict[str, Any]:
    """Return a high-fidelity mock response for a playground action."""
    handler = _MOCK_HANDLERS.get((slug, action))
    if not handler:
        return {
            "success": True,
            "is_mock": True,
            "response": {
                "message": f"This is a preview of the {action} action for {slug}.",
                "note": "Connect your account to see real data.",
            },
        }
    return handler(params)


def _mock_slack_list_channels(params: dict[str, Any]) -> dict[str, Any]:
    return {
        "success": True,
        "is_mock": True,
        "response": {
            "channels": [
                {"id": "C0MOCK001", "name": "general", "members": 42},
                {"id": "C0MOCK002", "name": "engineering", "members": 18},
                {"id": "C0MOCK003", "name": "design", "members": 12},
                {"id": "C0MOCK004", "name": "random", "members": 35},
                {"id": "C0MOCK005", "name": "announcements", "members": 50},
            ],
            "count": 5,
            "_preview": True,
            "_note": "Connect your Slack workspace to see your real channels.",
        },
    }


def _mock_slack_send_message(params: dict[str, Any]) -> dict[str, Any]:
    text = params.get("text", "Hello from Flowmanner Playground! 👋")
    return {
        "success": True,
        "is_mock": True,
        "response": {
            "channel": "#flowmanner-playground",
            "ts": f"{time.time():.6f}",
            "text": text,
            "_preview": True,
            "_note": "Connect Slack to send real messages to your workspace.",
        },
    }


def _mock_github_list_repos(params: dict[str, Any]) -> dict[str, Any]:
    return {
        "success": True,
        "is_mock": True,
        "response": {
            "repos": [
                {
                    "name": "demo-api",
                    "description": "A sample REST API built with FastAPI",
                    "stars": 12,
                    "language": "Python",
                    "url": "https://github.com/flowmanner-demo/demo-api",
                },
                {
                    "name": "demo-frontend",
                    "description": "React frontend for the demo API",
                    "stars": 8,
                    "language": "TypeScript",
                    "url": "https://github.com/flowmanner-demo/demo-frontend",
                },
                {
                    "name": "demo-infra",
                    "description": "Infrastructure as code for the demo project",
                    "stars": 5,
                    "language": "HCL",
                    "url": "https://github.com/flowmanner-demo/demo-infra",
                },
            ],
            "count": 3,
            "_preview": True,
            "_note": "Connect GitHub to see your real repositories.",
        },
    }


def _mock_github_show_repo(params: dict[str, Any]) -> dict[str, Any]:
    return {
        "success": True,
        "is_mock": True,
        "response": {
            "name": "demo-api",
            "description": "A sample REST API built with FastAPI",
            "stars": 12,
            "forks": 3,
            "language": "Python",
            "created_at": "2026-01-15T10:00:00Z",
            "url": "https://github.com/flowmanner-demo/demo-api",
            "_preview": True,
            "_note": "Connect GitHub to explore your own repositories.",
        },
    }


def _mock_notion_list_pages(params: dict[str, Any]) -> dict[str, Any]:
    return {
        "success": True,
        "is_mock": True,
        "response": {
            "pages": [
                {
                    "id": "mock-page-001",
                    "title": "Project Roadmap",
                    "url": "https://notion.so/demo/roadmap",
                    "created_at": "2026-06-01T10:00:00Z",
                },
                {
                    "id": "mock-page-002",
                    "title": "Meeting Notes - June 2026",
                    "url": "https://notion.so/demo/meeting-notes",
                    "created_at": "2026-06-15T14:00:00Z",
                },
                {
                    "id": "mock-page-003",
                    "title": "API Documentation",
                    "url": "https://notion.so/demo/api-docs",
                    "created_at": "2026-05-20T09:00:00Z",
                },
            ],
            "count": 3,
            "_preview": True,
            "_note": "Connect Notion to see your real pages and databases.",
        },
    }


def _mock_discord_send_message(params: dict[str, Any]) -> dict[str, Any]:
    text = params.get("text", "Hello from Flowmanner Playground! 👋")
    return {
        "success": True,
        "is_mock": True,
        "response": {
            "channel": "playground",
            "message_id": "mock-msg-001",
            "text": text,
            "_preview": True,
            "_note": "Connect Discord to send real messages to your server.",
        },
    }


def _mock_discord_list_channels(params: dict[str, Any]) -> dict[str, Any]:
    return {
        "success": True,
        "is_mock": True,
        "response": {
            "channels": [
                {"id": "mock-ch-001", "name": "general", "type": 0},
                {"id": "mock-ch-002", "name": "dev-chat", "type": 0},
                {"id": "mock-ch-003", "name": "playground", "type": 0},
            ],
            "count": 3,
            "_preview": True,
            "_note": "Connect Discord to see your real server channels.",
        },
    }


def _mock_apiflow_ping(params: dict[str, Any]) -> dict[str, Any]:
    return {
        "success": True,
        "is_mock": True,
        "response": {
            "status": "ok",
            "latency_ms": 45,
            "version": "2.1.0",
            "endpoints_available": 12,
            "_preview": True,
            "_note": "Connect Apiflow to interact with your real instance.",
        },
    }


_MOCK_HANDLERS: dict[tuple[str, str], Any] = {
    ("slack", "list_channels"): _mock_slack_list_channels,
    ("slack", "send_message"): _mock_slack_send_message,
    ("github", "list_repos"): _mock_github_list_repos,
    ("github", "show_repo"): _mock_github_show_repo,
    ("notion", "list_pages"): _mock_notion_list_pages,
    ("discord", "send_message"): _mock_discord_send_message,
    ("discord", "list_channels"): _mock_discord_list_channels,
    ("apiflow", "ping"): _mock_apiflow_ping,
}


# ── Playground rate limiting (in-memory, per-user per-integration) ────────

_rate_limit_store: dict[str, list[float]] = {}
_RATE_LIMIT_WINDOW = 60.0  # seconds
_DEFAULT_RATE_LIMIT = 5  # requests per window


def check_playground_rate_limit(
    user_id: str,
    slug: str,
    max_requests: int = _DEFAULT_RATE_LIMIT,
) -> tuple[bool, int]:
    """Check if a user is within the playground rate limit.

    Returns:
        (allowed, remaining) tuple.
    """
    key = f"playground:{user_id}:{slug}"
    now = time.monotonic()
    cutoff = now - _RATE_LIMIT_WINDOW

    # Clean old entries
    if key in _rate_limit_store:
        _rate_limit_store[key] = [t for t in _rate_limit_store[key] if t > cutoff]
    else:
        _rate_limit_store[key] = []

    current = len(_rate_limit_store[key])
    if current >= max_requests:
        return False, 0

    _rate_limit_store[key].append(now)
    return True, max_requests - current - 1
