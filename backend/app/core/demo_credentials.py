"""Demo credential vault for the integration playground.

Stores restricted demo credentials per integration, loaded from environment
variables.  These credentials are used by the playground endpoint so users
can try integrations without connecting their own accounts.

Security requirements:
    - Demo tokens MUST be scoped to sandbox workspaces/orgs only.
    - Rotate demo tokens monthly; document rotation runbook.
    - Never allow playground to act on user-owned resources.
    - Rate-limited to 5 requests/minute per user per integration.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DemoCredential:
    """Configuration for a single integration's demo credentials."""

    slug: str
    token: str | None = None
    allowed_resources: list[str] = field(default_factory=list)
    rate_limit: int = 5  # per minute per user
    workspace_name: str = "flowmanner-playground"
    notes: str = ""


def _env(key: str) -> str | None:
    """Return the env var value or None if unset/empty."""
    val = os.environ.get(key, "")
    return val if val else None


# ── Registry ──────────────────────────────────────────────────────────────

DEMO_CREDENTIALS: dict[str, DemoCredential] = {}


def _register(cred: DemoCredential) -> None:
    """Register a demo credential if its token is available."""
    if cred.token:
        DEMO_CREDENTIALS[cred.slug] = cred
        logger.info("Playground demo credentials loaded for %s", cred.slug)
    else:
        logger.debug(
            "No demo credentials for %s — playground will use mock responses",
            cred.slug,
        )


# Slack — uses a bot token scoped to the #flowmanner-playground channel
_register(
    DemoCredential(
        slug="slack",
        token=_env("SLACK_DEMO_BOT_TOKEN"),
        allowed_resources=["#flowmanner-playground"],
        rate_limit=5,
        workspace_name="Flowmanner Playground",
        notes="Bot token scoped to #flowmanner-playground only",
    )
)

# GitHub — uses a PAT scoped to the flowmanner-demo org
_register(
    DemoCredential(
        slug="github",
        token=_env("GITHUB_DEMO_TOKEN"),
        allowed_resources=["flowmanner-demo"],
        rate_limit=10,
        workspace_name="flowmanner-demo",
        notes="PAT with read-only access to flowmanner-demo org",
    )
)

# Discord — uses a bot token for a demo server
_register(
    DemoCredential(
        slug="discord",
        token=_env("DISCORD_DEMO_BOT_TOKEN"),
        allowed_resources=["flowmanner-playground"],
        rate_limit=5,
        workspace_name="Flowmanner Playground",
        notes="Bot token for the Flowmanner Playground Discord server",
    )
)

# Notion — uses an integration token for a demo workspace
_register(
    DemoCredential(
        slug="notion",
        token=_env("NOTION_DEMO_TOKEN"),
        allowed_resources=[],
        rate_limit=5,
        workspace_name="Flowmanner Demo",
        notes="Integration token for the Flowmanner Demo Notion workspace",
    )
)

# Google — no demo tenant available; playground uses mock responses
# Google Drive — same
_register(DemoCredential(slug="google"))
_register(DemoCredential(slug="google_drive"))

# Apiflow — uses a demo API key for a sandbox instance
_register(
    DemoCredential(
        slug="apiflow",
        token=_env("APIFLOW_DEMO_API_KEY"),
        allowed_resources=[],
        rate_limit=5,
        workspace_name="flowmanner-demo",
        notes="API key for a sandbox Apiflow instance",
    )
)


def get_demo_credential(slug: str) -> DemoCredential | None:
    """Return the demo credential for an integration, or None."""
    return DEMO_CREDENTIALS.get(slug)


def has_real_credentials(slug: str) -> bool:
    """Return True if the integration has real demo credentials (not just mock)."""
    cred = DEMO_CREDENTIALS.get(slug)
    return cred is not None and cred.token is not None
