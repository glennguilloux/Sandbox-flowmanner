"""Epic 2.2 — agent-side frozen snapshot of canonical memory (Option A).

Thin in-memory *snapshot seam* sitting on top of the now-canonical
``personal_memory_claims`` read path (``recall_for_chat``). Captures ONE
recall result per chat session (per ``thread_id``), freezes it, and
re-injects the same frozen set into every message in that session instead
of re-calling recall per message.

Design constraints (see docs/EPIC-2.2-FROZEN-SNAPSHOT-DESIGN.md):

* In-memory ONLY. No table, no Alembic migration, no schema change.
* Single seam (``get_snapshot`` / ``store_snapshot`` / ``get_or_capture_snapshot``)
  so the backing store could later be swapped to a persisted table
  (deferred Option B) without touching call sites.
* Lazy capture at first access for a ``thread_id`` (seed query ``""`` → the
  top-``top_k`` *standing* claim set, query-agnostic).
* Dual invalidation, neither of which blocks the write path:
    1. Write-invalidation via a ``(user_id, workspace_id) -> generation``
       counter. A new reviewer write bumps the counter; the next snapshot
       access re-captures if the counter moved (scales to many threads
       without a thread registry).
    2. Bounded TTL: if ``now - captured_at`` exceeds the session length,
       re-capture on next access.
* On invalidation the entry is simply DROPPED from the in-memory cache
  (not a flag + branch); the next access re-captures via the lazy path.
  This avoids serving a half-stale frozen set.

This module must NOT import ``personal_memory_service`` at the top level
(memory_citation_service → personal_memory_service would create a cycle).
It imports ``recall_for_chat`` from ``memory_citation_service`` only, which
is cycle-safe at module load. ``personal_memory_service`` imports
``bump_generation`` lazily *inside* its ``create`` method for the same reason.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from app.config import settings

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.models.personal_memory_models import PersonalMemoryClaim

logger = logging.getLogger(__name__)


# ── Snapshot staleness / TTL ───────────────────────────────────────────────
#
# Per the design doc §3.3/§4.5 we REUSE an existing session-length config
# value rather than invent a new knob. The project has no dedicated
# "chat session idle timeout", so we bind the snapshot TTL to the JWT /
# session lifetime (``JWT_ACCESS_TOKEN_EXPIRES`` = 900s, i.e. 15 min). A
# frozen snapshot is therefore at most ~one session stale before it is
# force-re-captured, which matches the intended "stable within a
# conversation, refreshable across sessions" semantics.
SNAPSHOT_TTL_SECONDS: int = int(getattr(settings, "JWT_ACCESS_TOKEN_EXPIRES", 900))


# The seed-capture uses the standing-context query (empty string). The
# top_k / min_confidence defaults are inherited from recall_for_chat's own
# defaults (CHAT_RECALL_TOP_K = 5 / CHAT_RECALL_MIN_CONFIDENCE = 0.7), so we
# call recall_for_chat without overriding them — keeping a single source of
# truth for the token-cost ceiling.
SEED_QUERY: str = ""


@dataclass
class FrozenMemorySnapshot:
    """A frozen capture of a user's standing personal-memory claim set.

    Captured exactly once per session (per ``thread_id``) and re-injected
    verbatim into every message in that session.
    """

    thread_id: int
    user_id: int
    workspace_id: str
    captured_at: datetime
    query_used: str
    claims: list[PersonalMemoryClaim] = field(default_factory=list)
    # The generation counter of (user_id, workspace_id) at capture time.
    # If the live counter has moved, the snapshot is stale and re-captured.
    generation: int = 0


# ── In-memory backing store ────────────────────────────────────────────────
#
# Module-level singletons. Lifetime = backend process lifetime. On restart
# the caches are simply empty; the next message in a thread re-captures
# (acceptable: the snapshot is a cache, not the source of truth).
_snapshots: dict[int, FrozenMemorySnapshot] = {}
_generations: dict[tuple[int, str], int] = {}


# ── Generation counter (write-invalidation, non-blocking) ──────────────────


def bump_generation(user_id: int, workspace_id: str) -> int:
    """Bump the generation counter for ``(user_id, workspace_id)``.

    Called from the canonical ``PersonalMemoryService.create`` write surface
    (direct writes *and* reviewer ``create_from_proposal`` writes). It only
    mutates an in-memory counter — it intentionally does NOT touch the
    snapshot cache, so the write path is never blocked on cache eviction.
    The next snapshot access for any thread in that user+workspace will see
    the counter moved and re-capture lazily.

    Returns the new generation value.
    """
    key = (user_id, workspace_id)
    _generations[key] = _generations.get(key, 0) + 1
    return _generations[key]


def get_generation(user_id: int, workspace_id: str) -> int:
    """Read the current generation counter for ``(user_id, workspace_id)``."""
    return _generations.get((user_id, workspace_id), 0)


# ── Seam: get / store (explicit) ───────────────────────────────────────────


def get_snapshot(thread_id: int) -> FrozenMemorySnapshot | None:
    """Return the current frozen snapshot for ``thread_id`` (or None).

    This does NOT validate staleness — it returns whatever is cached. Use
    ``get_or_capture_snapshot`` for the lazy-capture + invalidation path.
    """
    return _snapshots.get(thread_id)


def store_snapshot(thread_id: int, snapshot: FrozenMemorySnapshot) -> None:
    """Write a snapshot into the cache for ``thread_id``.

    Replaces any existing entry. Used by ``get_or_capture_snapshot`` after a
    (re-)capture, and available for tests.
    """
    if snapshot.thread_id != thread_id:
        # Defensive: keep the dict key authoritative.
        snapshot.thread_id = thread_id
    _snapshots[thread_id] = snapshot


def drop_snapshot(thread_id: int) -> None:
    """Remove a single thread's snapshot from the cache (if present)."""
    _snapshots.pop(thread_id, None)


def invalidate_user_workspace(user_id: int, workspace_id: str) -> None:
    """Drop every cached snapshot for a ``(user_id, workspace_id)``.

    Provided as an explicit alternative to the generation-counter path; the
    recommended production invalidation is ``bump_generation`` (lazy drop on
    next access). Kept for callers/tests that want immediate eviction.
    """
    for tid, snap in list(_snapshots.items()):
        if snap.user_id == user_id and snap.workspace_id == workspace_id:
            _snapshots.pop(tid, None)


# ── Seam: lazy capture + dual invalidation ─────────────────────────────────


async def get_or_capture_snapshot(
    db: AsyncSession,
    *,
    thread_id: int,
    user_id: int,
    workspace_id: str,
    ttl_seconds: int | None = None,
) -> list[PersonalMemoryClaim]:
    """Return the frozen claim list for ``thread_id``, capturing it once.

    * Cache miss → exactly ONE ``recall_for_chat(query="")`` using the
      standing-context defaults, stored, returned.
    * Cache hit AND generation unchanged AND within TTL → reuse frozen claims.
    * Cache hit but generation moved (a write happened) OR TTL exceeded →
      DROP the entry and re-capture once (lazy invalidation).

    ``ttl_seconds`` overrides the module ``SNAPSHOT_TTL_SECONDS`` default and
    exists primarily for tests; production callers should omit it so the
    snapshot TTL binds to the session-length config.
    """
    from app.services.memory_citation_service import recall_for_chat

    ttl = SNAPSHOT_TTL_SECONDS if ttl_seconds is None else int(ttl_seconds)
    now = datetime.now(UTC)
    generation = get_generation(user_id, workspace_id)

    existing = _snapshots.get(thread_id)
    if existing is not None:
        within_ttl = (now - existing.captured_at).total_seconds() <= ttl
        if existing.generation == generation and within_ttl:
            return existing.claims
        # Stale (write invalidation or TTL) → drop and re-capture.
        _snapshots.pop(thread_id, None)

    # Lazy capture: one recall_for_chat with the empty/seed query.
    claims = await recall_for_chat(
        db,
        user_id=user_id,
        workspace_id=workspace_id,
        query=SEED_QUERY,
    )
    snapshot = FrozenMemorySnapshot(
        thread_id=thread_id,
        user_id=user_id,
        workspace_id=workspace_id,
        captured_at=now,
        query_used=SEED_QUERY,
        claims=claims,
        generation=generation,
    )
    _snapshots[thread_id] = snapshot
    return claims


def clear_snapshots() -> None:
    """Reset all in-memory caches.

    Test helper — not used in production. Prevents cross-test leakage of the
    module-level singletons.
    """
    _snapshots.clear()
    _generations.clear()
