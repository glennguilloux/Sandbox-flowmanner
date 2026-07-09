"""Celery task: retrieval-lifecycle decay for personal memory + memory entries.

Epic 3.3 — "decay job". A single periodic task, ``decay_memory_entries``,
runs the three lifecycle operations for the durable memory stores:

1. **Soft-archive** claims/entries not recalled within ``MEMORY_DECAY_TTL_DAYS``
   (``last_used_at`` older than the TTL, or never used and ``created_at``
   older than the TTL). Sets ``deleted_at``; never hard-deletes.
2. **Importance decay** weighted by recency, computed in Python over the
   non-archived rows: ``new = importance * (1 - rate * days_since_last_use)``,
   floored at ``MEMORY_DECAY_MIN_IMPORTANCE``. ``days_since_last_use`` uses
   ``last_used_at`` if present, else ``created_at`` (a row never used is
   only ever decayed after it crosses the TTL, at which point it is archived
   first — see ordering note below).
3. **Hard-delete** of expired *sensitive* personal-memory claims only
   (``claim_type = sensitive`` AND ``expires_at < now()``). No other row is
   ever hard-deleted by this job.

Schema mapping (the merged ``PersonalMemoryClaim`` has no ``scope =
'constraint'`` / ``scope = 'sensitive'`` — see personal_memory_models.py):
- "immortal" claims = ``sensitivity = 'restricted'`` — NEVER archived or
  decayed (negative constraints / do-not-forget rule from the backlog).
- "sensitive + expired" = ``claim_type = 'sensitive'`` AND ``expires_at``
  in the past — the only rows this job hard-deletes.
- ``MemoryEntry`` has no scope/constraint/sensitivity concept: only
  soft-archive + decay apply; the hard-delete rule is skipped.

Operation ordering per row is why these are computed in Python:
- A row is **archived** first if it is past the TTL (and not immortal).
  Archived rows are then skipped by the decay pass.
- A row is **decayed** only if it is still live and has a usable recency
  anchor (``last_used_at``, else ``created_at``) and is not immortal.
- A sensitive claim is **hard-deleted** only if expired.

The async core, ``run_decay_job``, is decoupled from Celery: it accepts an
injectable ``open_session`` async-context-manager factory (defaulting to
``app.database.fresh_session``) so callers/tests can run it inside their own
event loop against any database. The Celery task simply wraps it in
``asyncio.run``. The job is idempotent and safe to re-run.
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from sqlalchemy import select

from app.config import settings
from app.database import fresh_session
from app.models.memory_models import MemoryEntry
from app.models.personal_memory_models import PersonalMemoryClaim
from app.tasks.celery_app import celery_app

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Callable

logger = logging.getLogger(__name__)

# Defaults mirror app.config so a unit test can call the pure helpers without
# needing the full Settings object; run_decay_job reads settings at call time.
DEFAULT_TTL_DAYS = 90
DEFAULT_DECAY_RATE_PER_DAY = 0.01
DEFAULT_MIN_IMPORTANCE = 0.0
DEFAULT_IMMORTAL_SENSITIVITY = "restricted"
DEFAULT_SENSITIVE_CLAIM_TYPE = "sensitive"


def _now() -> datetime:
    return datetime.now(UTC)


def _days_since(anchor: datetime | None, now: datetime) -> float | None:
    """Whole + fractional days between ``anchor`` and ``now``.

    Returns ``None`` when there is no usable anchor (the row has neither
    ``last_used_at`` nor ``created_at``), signalling "do not decay".
    """
    if anchor is None:
        return None
    # Normalise naive datetimes to UTC-aware for a correct delta.
    if anchor.tzinfo is None:
        anchor = anchor.replace(tzinfo=UTC)
    return max(0.0, (now - anchor).total_seconds() / 86400.0)


def decay_importance(
    importance: float,
    days_since_last_use: float,
    *,
    decay_rate: float = DEFAULT_DECAY_RATE_PER_DAY,
    min_importance: float = DEFAULT_MIN_IMPORTANCE,
) -> float:
    """Compute the decayed importance for a single row. Pure function.

    new = importance * (1 - decay_rate * days_since_last_use), floored at
    ``min_importance``. If the factor would go negative, the floor wins
    (importance never becomes negative).
    """
    factor = 1.0 - decay_rate * days_since_last_use
    if factor < 0:
        factor = 0.0
    new = importance * factor
    return max(min_importance, new)


@asynccontextmanager
async def _default_open_session() -> AsyncIterator:
    async with fresh_session() as session:
        yield session


async def _soft_archive_claims(
    open_session: Callable,
    ttl_days: int,
    now: datetime,
    immortal_sensitivity: str,
) -> int:
    """Soft-archive personal-memory claims past the recall TTL (immortal ones
    excluded). Returns the number archived."""
    cutoff = now - timedelta(days=ttl_days)
    archived = 0
    async with open_session() as db:
        rows = (
            (
                await db.execute(
                    select(PersonalMemoryClaim)
                    .where(PersonalMemoryClaim.deleted_at.is_(None))
                    .where(PersonalMemoryClaim.sensitivity != immortal_sensitivity)
                    .where(
                        (PersonalMemoryClaim.last_used_at < cutoff)
                        | (PersonalMemoryClaim.last_used_at.is_(None) & (PersonalMemoryClaim.created_at < cutoff))
                    )
                )
            )
            .scalars()
            .all()
        )
        for claim in rows:
            claim.deleted_at = now
            archived += 1
        if archived:
            await db.commit()
    logger.info("decay: soft-archived %d personal-memory claims", archived)
    return archived


async def _decay_claim_importance(
    open_session: Callable,
    now: datetime,
    decay_rate: float,
    min_importance: float,
    immortal_sensitivity: str,
) -> int:
    """Apply importance decay to live, non-immortal claims. Returns count."""
    updated = 0
    async with open_session() as db:
        rows = (
            (
                await db.execute(
                    select(PersonalMemoryClaim)
                    .where(PersonalMemoryClaim.deleted_at.is_(None))
                    .where(PersonalMemoryClaim.sensitivity != immortal_sensitivity)
                )
            )
            .scalars()
            .all()
        )
        for claim in rows:
            anchor = claim.last_used_at or claim.created_at
            days = _days_since(anchor, now)
            if days is None:
                continue
            new_imp = decay_importance(claim.importance, days, decay_rate=decay_rate, min_importance=min_importance)
            if new_imp != claim.importance:
                claim.importance = new_imp
                updated += 1
        if updated:
            await db.commit()
    logger.info("decay: decayed importance on %d personal-memory claims", updated)
    return updated


async def _hard_delete_expired_sensitive_claims(
    open_session: Callable,
    now: datetime,
    sensitive_claim_type: str,
) -> int:
    """Hard-delete sensitive claims whose expires_at is in the past.

    This is the ONLY hard-delete path in the job. Returns the number deleted.
    """
    deleted = 0
    async with open_session() as db:
        rows = (
            (
                await db.execute(
                    select(PersonalMemoryClaim)
                    .where(PersonalMemoryClaim.claim_type == sensitive_claim_type)
                    .where(PersonalMemoryClaim.expires_at < now)
                )
            )
            .scalars()
            .all()
        )
        for claim in rows:
            await db.delete(claim)
            deleted += 1
        if deleted:
            await db.commit()
    logger.info("decay: hard-deleted %d expired sensitive claims", deleted)
    return deleted


async def _soft_archive_entries(open_session: Callable, ttl_days: int, now: datetime) -> int:
    """Soft-archive memory entries past the recall TTL. Returns count."""
    cutoff = now - timedelta(days=ttl_days)
    archived = 0
    async with open_session() as db:
        rows = (
            (
                await db.execute(
                    select(MemoryEntry)
                    .where(MemoryEntry.deleted_at.is_(None))
                    .where(
                        (MemoryEntry.last_used_at < cutoff)
                        | (MemoryEntry.last_used_at.is_(None) & (MemoryEntry.created_at < cutoff))
                    )
                )
            )
            .scalars()
            .all()
        )
        for entry in rows:
            entry.deleted_at = now
            archived += 1
        if archived:
            await db.commit()
    logger.info("decay: soft-archived %d memory entries", archived)
    return archived


async def _decay_entry_importance(
    open_session: Callable, now: datetime, decay_rate: float, min_importance: float
) -> int:
    """Apply importance decay to live memory entries. Returns count updated."""
    updated = 0
    async with open_session() as db:
        rows = (await db.execute(select(MemoryEntry).where(MemoryEntry.deleted_at.is_(None)))).scalars().all()
        for entry in rows:
            anchor = entry.last_used_at or entry.created_at
            days = _days_since(anchor, now)
            if days is None:
                continue
            new_imp = decay_importance(entry.importance, days, decay_rate=decay_rate, min_importance=min_importance)
            if new_imp != entry.importance:
                entry.importance = new_imp
                updated += 1
        if updated:
            await db.commit()
    logger.info("decay: decayed importance on %d memory entries", updated)
    return updated


async def run_decay_job(
    open_session: Callable | None = None,
    *,
    now: datetime | None = None,
    ttl_days: int | None = None,
    decay_rate: float | None = None,
    min_importance: float | None = None,
    immortal_sensitivity: str | None = None,
    sensitive_claim_type: str | None = None,
) -> dict[str, int]:
    """Run the full decay job in the caller's event loop.

    ``open_session`` must be an async-context-manager factory yielding an
    ``AsyncSession`` (e.g. ``fresh_session`` or an ``async_sessionmaker()``).
    When ``None``, ``app.database.fresh_session`` is used.

    Any of ``ttl_days``, ``decay_rate``, ``min_importance``,
    ``immortal_sensitivity``, ``sensitive_claim_type`` may be passed to tune
    behaviour for tests without touching settings; ``None`` falls back to the
    corresponding ``settings.MEMORY_DECAY_*`` value.

    Returns a summary dict of how many rows each operation touched.
    """
    open_session = open_session or _default_open_session
    now = now or _now()
    ttl_days = ttl_days if ttl_days is not None else settings.MEMORY_DECAY_TTL_DAYS
    decay_rate = decay_rate if decay_rate is not None else settings.MEMORY_DECAY_RATE_PER_DAY
    min_importance = min_importance if min_importance is not None else settings.MEMORY_DECAY_MIN_IMPORTANCE
    immortal_sensitivity = (
        immortal_sensitivity if immortal_sensitivity is not None else settings.MEMORY_DECAY_IMMORTAL_SENSITIVITY
    )
    sensitive_claim_type = (
        sensitive_claim_type if sensitive_claim_type is not None else settings.MEMORY_DECAY_SENSITIVE_CLAIM_TYPE
    )

    # ── Personal-memory claims ──────────────────────────────────────
    # Order matters: archive first, then decay (archived rows skipped),
    # then hard-delete expired sensitive (a separate rule).
    claims_soft_archived = await _soft_archive_claims(open_session, ttl_days, now, immortal_sensitivity)
    claims_decayed = await _decay_claim_importance(open_session, now, decay_rate, min_importance, immortal_sensitivity)
    claims_hard_deleted = await _hard_delete_expired_sensitive_claims(open_session, now, sensitive_claim_type)

    # ── Memory entries (no scope/constraint; skip hard-delete rule) ──
    entries_soft_archived = await _soft_archive_entries(open_session, ttl_days, now)
    entries_decayed = await _decay_entry_importance(open_session, now, decay_rate, min_importance)

    summary = {
        "claims_soft_archived": claims_soft_archived,
        "claims_decayed": claims_decayed,
        "claims_hard_deleted_expired_sensitive": claims_hard_deleted,
        "entries_soft_archived": entries_soft_archived,
        "entries_decayed": entries_decayed,
    }
    logger.info("decay_memory_entries summary: %s", summary)
    return summary


@celery_app.task(
    bind=True,
    name="memory.decay_entries",
    max_retries=1,
    default_retry_delay=60,
    acks_late=True,
)
def decay_memory_entries(self) -> dict[str, int]:
    """Periodic Celery entry point for the retrieval-lifecycle decay job.

    Runs ``run_decay_job`` in its own event loop (Celery workers are
    synchronous by default) against the production DB via ``fresh_session``.
    """
    try:
        return asyncio.run(run_decay_job())
    except Exception as exc:  # pragma: no cover - surfaced to Celery retry
        logger.exception("decay_memory_entries failed: %s", exc)
        raise self.retry(exc=exc) from exc
