"""Provider fallback chain resolution (Q1-A chunk 5).

Resolves which LLM provider to call, walking a fallback chain when the
primary provider's circuit breaker is OPEN.

Design:
- Workspace-specific fallbacks take precedence over global (NULL workspace_id) ones.
- Within each scope, fallbacks are ordered by priority (lower = tried first).
- The circuit breaker is checked for each provider in the chain.
- When a fallback is actually used, a `provider.fallback_invoked` event is emitted.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from sqlalchemy import select, text

from app.services.substrate.circuit_breaker import (
    CircuitBreakerOpen,
    check_and_allow,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession
    from uuid import UUID

logger = logging.getLogger(__name__)


class AllProvidersOpen(Exception):
    """Raised when all providers in the fallback chain have open circuit breakers."""

    def __init__(self, tried: list[str]) -> None:
        self.tried = tried
        super().__init__(
            f"All providers in fallback chain have open circuit breakers: {tried}"
        )


# ── SQL ──────────────────────────────────────────────────────────────

_FALLBACK_CHAIN_SQL = text("""
    SELECT fallback_provider
    FROM provider_fallbacks
    WHERE primary_provider = :primary_provider
      AND (workspace_id = :ws_id OR workspace_id IS NULL)
    ORDER BY workspace_id NULLS LAST, priority ASC
""")


async def get_fallback_chain(
    db: AsyncSession,
    workspace_id: str | UUID | None,
    primary_provider: str,
) -> list[str]:
    """Get the ordered fallback chain for a provider.

    Workspace-specific fallbacks come first (user overrides win),
    then global (NULL workspace_id) fallbacks, both ordered by priority ASC.

    Returns:
        Ordered list of fallback provider IDs (may be empty).
    """
    ws_id_str = str(workspace_id) if workspace_id is not None else None
    result = await db.execute(
        _FALLBACK_CHAIN_SQL,
        {"primary_provider": primary_provider, "ws_id": ws_id_str},
    )
    rows = result.fetchall()

    # Deduplicate (workspace-specific entries shadow global ones with same
    # fallback_provider). We keep the first occurrence (workspace-specific
    # due to NULLS LAST ordering).
    seen: set[str] = set()
    chain: list[str] = []
    for row in rows:
        provider = row[0]
        if provider not in seen:
            seen.add(provider)
            chain.append(provider)

    return chain


async def resolve_provider(
    db: AsyncSession,
    workspace_id: str | UUID | None,
    primary_provider: str,
    *,
    check_circuit_breaker: bool = True,
) -> str:
    """Resolve which provider to call, walking the fallback chain if needed.

    1. Check the primary provider's circuit breaker.
    2. If allowed, return primary_provider.
    3. If denied, walk the fallback chain. For each fallback, check its CB.
    4. Return the first allowed provider.
    5. If all are denied, raise AllProvidersOpen.

    When check_circuit_breaker is False (feature disabled), returns
    primary_provider unchanged.

    Args:
        db: Async database session.
        workspace_id: Workspace ID (or None for global).
        primary_provider: The preferred provider to try first.
        check_circuit_breaker: Whether to check CB state (disabled by feature flag).

    Returns:
        The provider ID to call.

    Raises:
        AllProvidersOpen: If all providers in the chain have open breakers.
    """
    if not check_circuit_breaker:
        return primary_provider

    # Check primary
    primary_check = await check_and_allow(db, workspace_id, primary_provider)
    if primary_check.allowed:
        return primary_provider

    # Primary denied — walk fallback chain
    chain = await get_fallback_chain(db, workspace_id, primary_provider)
    tried = [primary_provider]

    for fallback in chain:
        fb_check = await check_and_allow(db, workspace_id, fallback)
        if fb_check.allowed:
            # Emit fallback event (import here to avoid circular deps)
            await _emit_fallback_event(
                db, workspace_id, primary_provider, fallback, primary_check.reason
            )
            return fallback
        tried.append(fallback)

    # All providers denied
    raise AllProvidersOpen(tried)


async def _emit_fallback_event(
    db: AsyncSession,
    workspace_id: str | UUID | None,
    primary_provider: str,
    fallback_provider: str,
    reason: str,
) -> None:
    """Emit a provider.fallback_invoked event to the substrate event log."""
    try:
        from app.models.substrate_models import SubstrateEventType
        from app.services.substrate.event_log import get_event_log

        event_log = get_event_log()
        # We don't have a run_id here — the event is workspace-scoped.
        # Use a synthetic run_id based on workspace for the event log.
        # This is acceptable because fallback events are informational,
        # not part of a mission's event stream.
        ws_str = str(workspace_id) if workspace_id else "global"
        await event_log.append(
            db,
            run_id=f"cb-{ws_str}",
            events=[
                {
                    "type": SubstrateEventType.PROVIDER_FALLBACK_INVOKED,
                    "payload": {
                        "workspace_id": str(workspace_id) if workspace_id else None,
                        "primary_provider": primary_provider,
                        "fallback_provider": fallback_provider,
                        "reason": reason,
                    },
                    "actor": "circuit_breaker",
                }
            ],
        )
    except Exception as e:
        logger.debug("Failed to emit fallback event: %s", e)
