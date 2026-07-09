"""One-time retroactive store sweep — GOV-1.3c (GOV Epic-1 retrospective).

GOV-1.3a's ``scan_for_poison`` only protects *future* writes (it runs at
``stage_pending_write``). The durable stores may already contain poison
from before 1.3a shipped — ``personal_memory_claims`` and ``memory_entries``
were historically written with no extraction-time scan. This module clears
that historical exposure window:

  Run the 1.3a scanner over EXISTING ``personal_memory_claims`` +
  ``memory_entries`` (never scan-protected in the past), flag hits, and
  route each flagged row into the existing HITL inbox as a separate
  ``MEMORY_APPROVAL`` review item (GOV-1.1's drain). A simple report is
  emitted regardless, so the operator sees the exposure window even before
  human review is wired.

Design constraints (inherited from the Epic-1 standing decisions):
  - ESCALATE-ONLY, like 1.3a: the scanner never de-escalates or auto-applies.
    We only surface hits for human review; we never mutate/delete the stored
    rows. (1.6 owns the attach-to-durable-memory loop; this sweep must not
    pre-empt it by editing data.)
  - Memory review items must NEVER pause/abort a mission (C4): the routed
    inbox items carry ``mission_id=None`` and the inbox expiry path
    auto-rejects WITHOUT executor dispatch (verified in GOV-1.1).
  - Idempotent: re-running the sweep must not duplicate inbox items for rows
    already surfaced. We persist a ``retro_sweep_flagged`` marker in the row's
    ``meta`` so a second run skips previously-flagged rows. (This is a
    non-destructive annotation, not a schema change.)
"""

from __future__ import annotations

import contextlib
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

from sqlalchemy import select

from app.models.hitl_models import HumanInterruptType
from app.services.hitl_service import HITLService
from app.services.memory.poison_scan import PoisonScanResult, scan_for_poison

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# Sweep provenance marker written into the stored row's ``meta`` so the
# sweep is idempotent. Value = sweep run id.
RETRO_SWEEP_META_KEY = "retro_sweep_flagged"

# Default TTL for the routed review items (mirrors 1.1's staging TTL so the
# audited auto-reject (C4) behaves identically).
RETRO_SWEEP_DEFAULT_TTL_DAYS = 7


@dataclass
class SweepFindings:
    """Aggregate result of a retroactive sweep run."""

    scanned_claims: int = 0
    scanned_entries: int = 0
    flagged_claims: int = 0
    flagged_entries: int = 0
    routed_items: int = 0
    skipped_already_flagged: int = 0
    hits_by_category: dict[str, int] = field(default_factory=dict)
    severity_high: int = 0

    @property
    def total_scanned(self) -> int:
        return self.scanned_claims + self.scanned_entries

    @property
    def total_flagged(self) -> int:
        return self.flagged_claims + self.flagged_entries


def _extract_claim_text(claim: Any) -> list[str]:
    """Pull scannable text out of a ``PersonalMemoryClaim``.

    The triple is ``(subject, predicate, object)`` where ``object`` is JSONB.
    We scan the subject, predicate, and a normalized JSON rendering of the
    object — an injected instruction hiding in any of them is poison.
    """
    texts: list[str] = []
    subject = getattr(claim, "subject", None)
    predicate = getattr(claim, "predicate", None)
    obj = getattr(claim, "object", None)
    if subject:
        texts.append(str(subject))
    if predicate:
        texts.append(str(predicate))
    if obj:
        with contextlib.suppress(Exception):  # pragma: no cover - defensive
            texts.append(_json_safe_str(obj))
    return texts


def _extract_entry_text(entry: Any) -> list[str]:
    """Pull scannable text out of a ``MemoryEntry`` (the ``content`` field)."""
    content = getattr(entry, "content", None)
    if content:
        return [str(content)]
    return []


def _json_safe_str(obj: Any) -> str:
    """Serialize a JSONB object to a stable single-line string for scanning.

    Uses ``orjson`` if available (fast, matches the rest of the stack), else
    stdlib ``json``. Either way we must NOT raise on non-serializable input.
    """
    try:
        import orjson  # type: ignore[import-not-found]

        return orjson.dumps(obj, option=orjson.OPT_SORT_KEYS).decode("utf-8")
    except Exception:
        import json

        try:
            return json.dumps(obj, sort_keys=True, default=str)
        except Exception:
            return str(obj)


def _already_flagged(meta: Any) -> bool:
    """True if this row was already surfaced by a previous sweep run."""
    if not meta or not isinstance(meta, dict):
        return False
    return RETRO_SWEEP_META_KEY in meta


def _annotate_meta(meta: Any, sweep_run_id: str) -> dict[str, Any]:
    """Return a new meta dict carrying the retro-sweep marker."""
    base = dict(meta) if isinstance(meta, dict) else {}
    base[RETRO_SWEEP_META_KEY] = sweep_run_id
    return base


def _scan_many(texts: list[str]) -> PoisonScanResult:
    """Scan several fields and merge their findings into one result.

    ``scan_for_poison`` only takes ``content`` + ``old_text``; a claim's
    triple spans subject/predicate/object. We scan each field and union the
    hits/severity so no poison hides in a field the function didn't reach.
    """
    merged = PoisonScanResult()
    for text in texts:
        res = scan_for_poison(text)
        if res.flagged:
            merged.flagged = True
            for hit in res.hits:
                if hit not in merged.hits:
                    merged.hits.append(hit)
            if res.severity == "high":
                merged.severity = "high"
    return merged


def _merge_hits(findings: SweepFindings, scan: PoisonScanResult) -> None:
    for hit in scan.hits:
        findings.hits_by_category[hit] = findings.hits_by_category.get(hit, 0) + 1
    if scan.severity == "high":
        findings.severity_high += 1


async def _route_review_item(
    db: AsyncSession,
    *,
    workspace_id: str | None,
    user_id: int,
    source_table: str,
    source_id: str,
    sample_text: str,
    scan: PoisonScanResult,
    expires_at: datetime,
) -> str | None:
    """Create a MEMORY_APPROVAL inbox item for a flagged historical row (GOV-1.1 drain).

    Returns the new inbox item id, or ``None`` on failure (best-effort — the
    durable row is never touched, so a routing failure just means the row was
    not surfaced this run; it will be retried next run and NOT duplicated
    because we only mark ``meta`` on success).
    """
    try:
        service = HITLService(db)
        preview = sample_text[:280]
        item = await service.create_interrupt(
            mission_id=None,  # memory review must never bind to / pause a mission (C4)
            user_id=user_id,
            interrupt_type=HumanInterruptType.MEMORY_APPROVAL,
            title=f"Retroactive scan hit: {source_table} {source_id}",
            description=(
                f"[retroactive-sweep] {source_table} row scanned clean by 1.3a only at "
                f"write time, flagged on historical sweep.\n\n{preview}"
            ),
            proposed_action={
                "retro_sweep": True,
                "source_table": source_table,
                "source_id": source_id,
                "scan": scan.to_metadata()["poison_scan"],
            },
            context={
                "retro_sweep": True,
                "source_table": source_table,
                "source_id": source_id,
                "is_memory_write": True,
            },
            workspace_id=workspace_id,
            expires_at=expires_at,
        )
        return str(item.id) if item is not None else None
    except Exception as exc:  # best-effort: never raise out of the sweep
        logger.warning(
            "retroactive sweep: routing %s %s to inbox failed: %s",
            source_table,
            source_id,
            exc,
        )
        return None


async def retroactive_memory_sweep(
    db: AsyncSession,
    *,
    workspace_id: str | None = None,
    batch_size: int = 200,
    dry_run: bool = False,
) -> SweepFindings:
    """Scan existing memory stores for poison and route hits to the inbox.

    By default scans ALL workspaces; pass ``workspace_id`` to scope to one.
    ``dry_run=True`` performs the full scan + report but does NOT create inbox
    items or annotate rows (safe preview). ``batch_size`` bounds each query
    page.

    Idempotent: rows already carrying the retro-sweep marker are skipped and
    counted in ``skipped_already_flagged``.

    NOTE: this is a one-time historical sweep. It does NOT mutate stored
    content — flagged rows are surfaced for human review and left in place.
    """
    from app.models.memory_models import MemoryEntry
    from app.models.personal_memory_models import PersonalMemoryClaim

    findings = SweepFindings()
    sweep_run_id = (
        f"{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}-{abs(hash((workspace_id or 'all', batch_size))) % 10_000:04d}"
    )
    expires_at = datetime.now(UTC) + timedelta(days=RETRO_SWEEP_DEFAULT_TTL_DAYS)

    # ── 1. personal_memory_claims ──────────────────────────────────────
    claim_base = select(PersonalMemoryClaim).where(PersonalMemoryClaim.deleted_at.is_(None))
    if workspace_id is not None:
        claim_base = claim_base.where(PersonalMemoryClaim.workspace_id == workspace_id)
    claim_stmt = claim_base.order_by(PersonalMemoryClaim.created_at.asc()).limit(batch_size)
    claims = list((await db.execute(claim_stmt)).scalars().all())
    findings.scanned_claims = len(claims)

    for claim in claims:
        meta = getattr(claim, "meta", None)
        if _already_flagged(meta):
            findings.skipped_already_flagged += 1
            continue
        texts = _extract_claim_text(claim)
        scan = _scan_many(texts) if texts else PoisonScanResult()
        if not scan.flagged:
            continue
        findings.flagged_claims += 1
        _merge_hits(findings, scan)
        if dry_run:
            continue
        item_id = await _route_review_item(
            db,
            workspace_id=getattr(claim, "workspace_id", None),
            user_id=getattr(claim, "user_id", 0),
            source_table="personal_memory_claims",
            source_id=str(getattr(claim, "id", "?")),
            sample_text=texts[0] if texts else "",
            scan=scan,
            expires_at=expires_at,
        )
        if item_id is not None:
            findings.routed_items += 1
            try:
                claim.meta = _annotate_meta(meta, sweep_run_id)  # type: ignore[attr-defined]
                await db.flush()
            except Exception as exc:  # pragma: no cover - defensive
                logger.warning("retroactive sweep: annotate claim failed: %s", exc)

    # ── 2. memory_entries (canonical store) ─────────────────────────────
    entry_base = select(MemoryEntry)
    if workspace_id is not None:
        entry_base = entry_base.where(MemoryEntry.workspace_id == workspace_id)
    entry_stmt = entry_base.order_by(MemoryEntry.created_at.asc()).limit(batch_size)
    entries = list((await db.execute(entry_stmt)).scalars().all())
    findings.scanned_entries = len(entries)

    for entry in entries:
        meta = getattr(entry, "meta", None)
        if _already_flagged(meta):
            findings.skipped_already_flagged += 1
            continue
        texts = _extract_entry_text(entry)
        scan = _scan_many(texts) if texts else PoisonScanResult()
        if not scan.flagged:
            continue
        findings.flagged_entries += 1
        _merge_hits(findings, scan)
        if dry_run:
            continue
        item_id = await _route_review_item(
            db,
            workspace_id=getattr(entry, "workspace_id", None),
            user_id=getattr(entry, "user_id", 0) or 0,
            source_table="memory_entries",
            source_id=str(getattr(entry, "id", "?")),
            sample_text=texts[0] if texts else "",
            scan=scan,
            expires_at=expires_at,
        )
        if item_id is not None:
            findings.routed_items += 1
            try:
                entry.meta = _annotate_meta(meta, sweep_run_id)  # type: ignore[attr-defined]
                await db.flush()
            except Exception as exc:  # pragma: no cover - defensive
                logger.warning("retroactive sweep: annotate entry failed: %s", exc)

    if not dry_run:
        try:
            await db.commit()
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("retroactive sweep: commit failed (rolled back): %s", exc)
            await db.rollback()
    else:
        logger.info("retroactive sweep: dry-run — no items created, no rows annotated")

    _log_report(findings)
    return findings


def _log_report(findings: SweepFindings) -> None:
    logger.info(
        "Retroactive memory sweep complete: scanned=%d (claims=%d, entries=%d) "
        "flagged=%d (claims=%d, entries=%d) routed=%d already_flagged=%d "
        "severity_high=%d categories=%s",
        findings.total_scanned,
        findings.scanned_claims,
        findings.scanned_entries,
        findings.total_flagged,
        findings.flagged_claims,
        findings.flagged_entries,
        findings.routed_items,
        findings.skipped_already_flagged,
        findings.severity_high,
        dict(findings.hits_by_category),
    )
