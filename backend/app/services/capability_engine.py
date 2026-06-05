"""CapabilityEngine — OCap token management (H3.2).

The single source of truth for capability tokens.  No other code creates tokens.

Per Ω spec VII.9:
- issue():     Create a new root capability token (kernel-only).
- verify():    Check if a token authorizes a given action.
- revoke():    Revoke a token (and all its children transitively).
- attenuate(): Create a weaker child token from a parent.

Invariants enforced:
- I.1  (Unforgeability):   Only CapabilityEngine.issue() creates tokens.
- I.2  (Attenuation):      Child token's actions ⊆ parent's actions.
- I.3  (No ambient auth):  Every tool invocation requires a valid token.
- I.13 (Central issuance): Tokens are issued by the engine, and only the engine.

Integration:
- Wraps all tool handlers: dispatcher checks for a valid token before invoking.
- RBAC remains as a coarser outer layer (e.g., "only Pro users can issue tokens for tool:run_command").
- Token lifecycle events are recorded to the substrate event log for audit.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from app.models.capability_models import (
    Action,
    CapabilityToken,
    ResourceRef,
)

logger = logging.getLogger(__name__)


class TokenStorage:
    """In-memory token storage with audit trail.

    In production, this would be backed by a PostgreSQL table with
    the same append-only guarantees as the substrate event log.
    """

    def __init__(self):
        self._tokens: dict[UUID, CapabilityToken] = {}
        self._revocation_log: list[dict[str, Any]] = []

    def persist(self, token: CapabilityToken) -> None:
        """Store a token."""
        self._tokens[token.id] = token
        logger.debug("Persisted token %s for resource %s", token.id, token.resource)

    def get(self, token_id: UUID) -> CapabilityToken | None:
        """Retrieve a token by ID."""
        return self._tokens.get(token_id)

    def mark_revoked(self, token_id: UUID, reason: str, revoked_at: datetime) -> None:
        """Mark a token as revoked."""
        token = self._tokens.get(token_id)
        if token is None:
            logger.warning("Cannot revoke unknown token %s", token_id)
            return

        token.revoked = True
        self._revocation_log.append(
            {
                "token_id": str(token_id),
                "reason": reason,
                "revoked_at": revoked_at.isoformat(),
            }
        )
        logger.info("Revoked token %s: %s", token_id, reason)

    def get_children(self, parent_id: UUID) -> list[CapabilityToken]:
        """Get all tokens that have the given parent (for cascading revoke)."""
        return [t for t in self._tokens.values() if t.parent == parent_id]

    def all(self) -> list[CapabilityToken]:
        """Get all tokens (for audit)."""
        return list(self._tokens.values())

    def all_active(self) -> list[CapabilityToken]:
        """Get all active (non-revoked, non-expired) tokens."""
        now = datetime.now(UTC)
        return [
            t
            for t in self._tokens.values()
            if not t.revoked and (t.expires_at is None or t.expires_at > now)
        ]


class CapabilityEngine:
    """The single source of truth for capability tokens.

    No other code creates CapabilityToken instances.  The kernel calls
    issue(); tool dispatchers call verify(); revoke() cascades to children.

    Usage:
        engine = CapabilityEngine()
        token = engine.issue(
            resource=ResourceRef(kind="tool", name="web_search"),
            actions={Action.EXECUTE},
            to=agent_id,
        )
        if engine.verify(token, Action.EXECUTE):
            await run_tool(token, params)
        engine.revoke(token.id, "mission complete")
    """

    def __init__(self, storage: TokenStorage | None = None):
        self.storage = storage or TokenStorage()

    # ── Token lifecycle ────────────────────────────────────────────

    def issue(
        self,
        *,
        resource: ResourceRef,
        actions: set[Action],
        to: UUID,
        expires_at: datetime | None = None,
        parent: UUID | None = None,
    ) -> CapabilityToken:
        """Issue a new capability token.

        This is the ONLY code path that creates CapabilityToken instances.
        Enforces Invariant I.1 (Unforgeability) and I.13 (Central issuance).

        Args:
            resource: What is being granted (tool, table, file, etc.).
            actions: What may be done (subset of {read, write, execute, delegate}).
            to: The principal (AgentId or UserId) receiving this token.
            expires_at: Optional expiry time.
            parent: Optional parent token ID (for delegation chains).

        Returns:
            A new CapabilityToken, already persisted.

        Raises:
            ValueError: If actions is empty.
        """
        if not actions:
            raise ValueError("Cannot issue a token with no actions")

        token = CapabilityToken(
            id=uuid4(),
            resource=resource,
            actions=actions,
            parent=parent,
            attenuation_proof="issued_by=capability_engine;actions="
            + ",".join(sorted(a.value for a in actions)),
            issued_to=to,
            issued_at=datetime.now(UTC),
            expires_at=expires_at,
        )

        self.storage.persist(token)
        logger.info(
            "Issued token %s: resource=%s actions=%s to=%s",
            token.id,
            resource,
            [a.value for a in actions],
            to,
        )
        return token

    def verify(self, token: CapabilityToken, required: Action) -> bool:
        """Verify that a token authorizes the given action.

        Checks: not revoked, not expired, action is authorized.
        Enforces Invariant I.3 (No ambient authority).
        """
        return token.can(required)

    def verify_and_require(
        self, token: CapabilityToken | None, required: Action
    ) -> CapabilityToken:
        """Verify a token and raise if not authorized.

        Returns the token for chaining.

        Raises:
            PermissionError: If token is None, revoked, expired, or lacks the action.
        """
        if token is None:
            raise PermissionError(
                f"No capability token provided. "
                f"Action '{required.value}' requires a valid token."
            )

        if not token.can(required):
            if token.revoked:
                raise PermissionError(
                    f"Token {token.id} has been revoked. "
                    f"Action '{required.value}' denied."
                )
            if token.expires_at and datetime.now(UTC) > token.expires_at:
                raise PermissionError(
                    f"Token {token.id} expired at {token.expires_at}. "
                    f"Action '{required.value}' denied."
                )
            raise PermissionError(
                f"Token {token.id} does not authorize '{required.value}'. "
                f"Authorized actions: {[a.value for a in token.actions]}"
            )

        return token

    def revoke(self, token_id: UUID, reason: str, *, cascade: bool = True) -> int:
        """Revoke a token and optionally all its children.

        Args:
            token_id: The token to revoke.
            reason: Human-readable revocation reason.
            cascade: If True, recursively revoke all descendant tokens.

        Returns:
            Number of tokens revoked.
        """
        count = 0

        token = self.storage.get(token_id)
        if token is None:
            logger.warning("Cannot revoke unknown token %s", token_id)
            return 0

        # Revoke this token
        self.storage.mark_revoked(token_id, reason, datetime.now(UTC))
        count += 1

        # Cascade to children
        if cascade:
            children = self.storage.get_children(token_id)
            for child in children:
                count += self.revoke(
                    child.id,
                    f"Cascaded from parent {token_id}: {reason}",
                    cascade=True,
                )

        logger.info("Revoked %d tokens starting from %s: %s", count, token_id, reason)
        return count

    def attenuate(
        self,
        parent: CapabilityToken,
        *,
        remove_actions: set[Action] | None = None,
        expires_at: datetime | None = None,
    ) -> CapabilityToken:
        """Create an attenuated child token from a parent.

        The child's actions MUST be a strict subset of the parent's.
        Enforces Invariant I.2 (Attenuation-only).

        This method delegates to the CapabilityToken.attenuate() method
        and additionally persists the new token.

        Args:
            parent: The parent token to attenuate from.
            remove_actions: Actions to remove from the child.
            expires_at: Optional expiry for the child token.

        Returns:
            A new CapabilityToken that is a weaker version of the parent.

        Raises:
            ValueError: If the attenuated actions are not a subset.
        """
        child = parent.attenuate(
            remove_actions=remove_actions or set(),
            expires_at=expires_at,
        )
        self.storage.persist(child)
        logger.info(
            "Attenuated token %s → %s (actions: %s → %s)",
            parent.id,
            child.id,
            [a.value for a in parent.actions],
            [a.value for a in child.actions],
        )
        return child

    # ── Queries ────────────────────────────────────────────────────

    def get_token(self, token_id: UUID) -> CapabilityToken | None:
        """Get a token by ID."""
        return self.storage.get(token_id)

    def get_active_tokens(self, principal_id: UUID) -> list[CapabilityToken]:
        """Get all active tokens held by a principal."""
        return [t for t in self.storage.all_active() if t.issued_to == principal_id]

    def get_authorized_actions(
        self, principal_id: UUID, resource: ResourceRef
    ) -> set[Action]:
        """Get all actions a principal is authorized for on a resource."""
        tokens = [
            t
            for t in self.storage.all_active()
            if t.issued_to == principal_id and t.resource == resource
        ]
        if not tokens:
            return set()
        return set().union(*(t.actions for t in tokens))

    def audit_log(self, principal_id: UUID) -> list[dict[str, Any]]:
        """Get the full audit trail for a principal's tokens."""
        tokens = [t for t in self.storage.all() if t.issued_to == principal_id]
        return [t.to_dict() for t in tokens]

    def stats(self) -> dict[str, Any]:
        """Get engine statistics."""
        all_tokens = self.storage.all()
        active = self.storage.all_active()
        return {
            "total_tokens": len(all_tokens),
            "active_tokens": len(active),
            "revoked_tokens": len([t for t in all_tokens if t.revoked]),
            "expired_tokens": len(
                [
                    t
                    for t in all_tokens
                    if t.expires_at and t.expires_at <= datetime.now(UTC)
                ]
            ),
            "revocation_count": len(self.storage._revocation_log),
        }


# ── Singleton ──────────────────────────────────────────────────────

_capability_engine: CapabilityEngine | None = None


def get_capability_engine() -> CapabilityEngine:
    """Get or create the CapabilityEngine singleton."""
    global _capability_engine
    if _capability_engine is None:
        _capability_engine = CapabilityEngine()
    return _capability_engine


def reset_capability_engine() -> None:
    """Reset the singleton (for testing)."""
    global _capability_engine
    _capability_engine = None
