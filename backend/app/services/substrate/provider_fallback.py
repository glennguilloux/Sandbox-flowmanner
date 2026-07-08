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
from dataclasses import dataclass
from typing import TYPE_CHECKING

from sqlalchemy import select, text

from app.services.substrate.circuit_breaker import (
    CircuitBreakerOpen,
    check_and_allow,
)

if TYPE_CHECKING:
    from uuid import UUID

    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ProviderProvenance:
    """Provenance metadata returned alongside provider resolution.

    Every LLM call carries this so callers know which provider was requested
    vs. which one actually served the request.

    Attributes:
        requested_provider: The provider that was originally requested.
        served_provider: The provider that will actually serve the call.
        degraded: True when a fallback (local or cross-provider) resulted in
            a different provider than requested.  Cloud→local is always degraded.
        substituted_from: When a model-level substitution happened (e.g.
            cloud/BYOK → local llama.cpp), this is the originally requested
            model_id.  ``None`` when no model-level substitution occurred.
        fallback_reason: Why the primary provider was denied (circuit breaker
            reason).  ``None`` when the primary was used.
    """

    requested_provider: str
    served_provider: str
    degraded: bool = False
    substituted_from: str | None = None
    fallback_reason: str | None = None


# Provider class constants for cross-class-fallback detection.
_LOCAL_PROVIDER_PREFIXES = ("llamacpp", "local", "ollama")


def _is_local_provider(provider_id: str) -> bool:
    """Return True if *provider_id* denotes a local/self-hosted provider."""
    pid = provider_id.lower()
    return any(pid.startswith(p) or pid == p for p in _LOCAL_PROVIDER_PREFIXES)


class AllProvidersOpen(Exception):
    """Raised when all providers in the fallback chain have open circuit breakers."""

    def __init__(
        self,
        tried: list[str],
        provenance: ProviderProvenance | None = None,
    ) -> None:
        self.tried = tried
        self.provenance = provenance
        super().__init__(f"All providers in fallback chain have open circuit breakers: {tried}")


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
) -> ProviderProvenance:
    """Resolve which provider to call, walking the fallback chain if needed.

    1. Check the primary provider's circuit breaker.
    2. If allowed, return a non-degraded provenance.
    3. If denied, walk the fallback chain. For each fallback, check its CB.
    4. Return a degraded provenance for the first allowed fallback.
    5. If all are denied, raise AllProvidersOpen.

    When check_circuit_breaker is False (feature disabled), returns
    a non-degraded provenance for the primary provider.

    Args:
        db: Async database session.
        workspace_id: Workspace ID (or None for global).
        primary_provider: The preferred provider to try first.
        check_circuit_breaker: Whether to check CB state (disabled by feature flag).

    Returns:
        A ``ProviderProvenance`` dataclass carrying the resolved provider
        and provenance metadata.

    Raises:
        AllProvidersOpen: If all providers in the chain have open breakers.
    """
    if not check_circuit_breaker:
        return ProviderProvenance(
            requested_provider=primary_provider,
            served_provider=primary_provider,
        )

    # Check primary
    primary_check = await check_and_allow(db, workspace_id, primary_provider)
    if primary_check.allowed:
        return ProviderProvenance(
            requested_provider=primary_provider,
            served_provider=primary_provider,
        )

    # Primary denied — walk fallback chain
    chain = await get_fallback_chain(db, workspace_id, primary_provider)
    tried = [primary_provider]

    for fallback in chain:
        fb_check = await check_and_allow(db, workspace_id, fallback)
        if fb_check.allowed:
            # Emit fallback event (import here to avoid circular deps)
            await _emit_fallback_event(db, workspace_id, primary_provider, fallback, primary_check.reason)
            # Cross-class fallback (cloud→local) is always degraded.
            primary_is_local = _is_local_provider(primary_provider)
            fallback_is_local = _is_local_provider(fallback)
            is_degraded = not primary_is_local and fallback_is_local

            return ProviderProvenance(
                requested_provider=primary_provider,
                served_provider=fallback,
                degraded=is_degraded,
                fallback_reason=primary_check.reason,
            )
        tried.append(fallback)

    # All providers denied
    provenance = ProviderProvenance(
        requested_provider=primary_provider,
        served_provider=primary_provider,  # will never actually be used
        degraded=True,
        fallback_reason=primary_check.reason,
    )
    raise AllProvidersOpen(tried, provenance=provenance)


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
