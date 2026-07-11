"""Governance read endpoints — memory poison-scan verdicts (t_9bb4df81).

Exposes poison-scan verdicts (severity + provenance + hits) that the
extraction-time scanner (``PoisonScanResult``) and the retroactive memory
sweep persist into row ``meta``. Two sources are unified:

  - ``live``  — ``pending_writes.meta["poison_scan"]`` rows staged by the
    background review service (GOV-1.3a) that are still PENDING / flagged.
  - ``retro`` — ``personal_memory_claims.meta["poison_scan"]`` rows flagged
    by the one-time retroactive sweep (GOV-1.3c); the FULL verdict is
    persisted there as of this task (previously only a marker was written).

The endpoint returns only flagged rows (``poison_scan.flagged == True``)
with severity, hits, provenance_requirement, the source label, a content
snippet, and created_at. Pagination + an optional ``?source=`` filter
(live|retro) are supported.

Auth: admin role (reuse ``require_role``). The v1 envelope is the native
FastAPI JSONResponse (v1 routes never use the v2 envelope).
"""

from __future__ import annotations

from datetime import UTC, datetime, timezone
from typing import TYPE_CHECKING, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, type_coerce
from sqlalchemy.dialects.postgresql import JSONB

from app.api.deps import get_current_user, get_db, require_role
from app.models.memory_models import PendingWrite, PendingWriteStatus
from app.models.personal_memory_models import PersonalMemoryClaim

if TYPE_CHECKING:
    from collections.abc import Callable

    from sqlalchemy.ext.asyncio import AsyncSession

    from app.models.user import User

router = APIRouter(prefix="/governance", tags=["governance"])


# ── Serialization helpers ──────────────────────────────────────────────────

_DEFAULT_PAGE_SIZE = 50
_MAX_PAGE_SIZE = 200

# JSONB containment filter for flagged poison-scan verdicts. Pushed to the DB
# so we never load full tables into Python (the previous version fetched every
# pending write / claim and filtered in memory).
_FLAGGED_VERDICT = {"poison_scan": {"flagged": True}}


def _verdict(payload_meta: Any) -> dict[str, Any] | None:
    """Extract the ``poison_scan`` verdict dict from a row's meta.

    Returns ``None`` when the row has no meta, no ``poison_scan`` sub-dict,
    or the verdict is not flagged (we only surface flagged rows).
    """
    if not payload_meta or not isinstance(payload_meta, dict):
        return None
    verdict = payload_meta.get("poison_scan")
    if not isinstance(verdict, dict):
        return None
    if not verdict.get("flagged"):
        return None
    return verdict


def _snippet(text: str | None, limit: int = 280) -> str:
    if not text:
        return ""
    text = " ".join(str(text).split())
    return text[:limit]


def _pending_row(pw: PendingWrite) -> dict[str, Any]:
    verdict = _verdict(pw.meta) or {}
    return {
        "id": pw.id,
        "content_snippet": _snippet(pw.content),
        "severity": verdict.get("severity", "none"),
        "hits": list(verdict.get("hits", [])),
        "provenance_requirement": verdict.get("provenance_requirement", "none"),
        "judge_skipped": bool(verdict.get("judge_skipped", False)),
        "source": "live",
        "created_at": pw.created_at.isoformat() if pw.created_at else None,
    }


def _claim_row(claim: PersonalMemoryClaim) -> dict[str, Any]:
    verdict = _verdict(claim.meta) or {}
    # The claim triple is the most representative content for the snippet.
    snippet = " ".join(part for part in (str(claim.subject), str(claim.predicate)) if part)
    return {
        "id": str(claim.id),
        "content_snippet": _snippet(snippet),
        "severity": verdict.get("severity", "none"),
        "hits": list(verdict.get("hits", [])),
        "provenance_requirement": verdict.get("provenance_requirement", "none"),
        "judge_skipped": bool(verdict.get("judge_skipped", False)),
        "source": "retro",
        "created_at": claim.created_at.isoformat() if claim.created_at else None,
    }


# ── Endpoint ───────────────────────────────────────────────────────────────


@router.get("/poison-scans")
async def list_poison_scans(
    source: Literal["live", "retro", "all"] = Query("all", description="Filter by verdict source: live|retro|all"),
    page: int = Query(1, ge=1, description="1-based page number"),
    page_size: int = Query(_DEFAULT_PAGE_SIZE, ge=1, le=_MAX_PAGE_SIZE, description="Rows per page"),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_role("admin")),
) -> dict[str, Any]:
    """Return poison-scan flagged items with severity + provenance.

    Covers BOTH ``pending_writes`` (live) and ``personal_memory_claims``
    (retro) sources. Filtering + pagination are pushed to the database: the
    flagged verdict is matched by JSONB containment (``meta @> {poison_scan:
    {flagged: true}}``) and paging uses real ``LIMIT``/``OFFSET`` so we never
    load the full table into Python.
    """
    offset = (page - 1) * page_size

    # Single-source request: paginate entirely in the DB.
    if source in ("live", "retro"):
        model, transform = (PendingWrite, _pending_row) if source == "live" else (PersonalMemoryClaim, _claim_row)
        stmt = (
            select(model)
            .where(model.meta.op("@>")(type_coerce(_FLAGGED_VERDICT, JSONB)))
            .order_by(model.created_at.desc().nullslast())
            .limit(page_size)
            .offset(offset)
        )
        result = await db.execute(stmt)
        rows = [transform(obj) for obj in result.scalars().all()]
        total = await _count_flagged(db, model)
        pages = (total + page_size - 1) // page_size if page_size else 1
        return {
            "items": rows,
            "total": total,
            "page": page,
            "page_size": page_size,
            "pages": pages,
            "source": source,
        }

    # Cross-source "all": each source is DB-filtered to flagged rows and
    # fetched in full, then merged into one chronological stream and sliced.
    # Flagged poison-scan rows are inherently a small, human-attended
    # governance queue, so fetching all flagged (not all rows) keeps memory
    # bounded while guaranteeing correct page-window slicing — independent
    # per-source offset paging + re-slice would return wrong rows when one
    # source dominates the timeline.
    live_rows, live_total = await _fetch_source(db, PendingWrite, _pending_row, limit=None)
    retro_rows, retro_total = await _fetch_source(db, PersonalMemoryClaim, _claim_row, limit=None)

    rows = [*live_rows, *retro_rows]
    # Stable chronological merge: real datetimes sort correctly; missing
    # timestamps sort last regardless of source.
    rows.sort(
        key=lambda r: (r.get("created_at") is None, _as_sort_dt(r.get("created_at"))),
        reverse=True,
    )
    page_rows = rows[offset : offset + page_size]
    total = live_total + retro_total
    pages = (total + page_size - 1) // page_size if page_size else 1

    return {
        "items": page_rows,
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": pages,
        "source": source,
    }


def _as_sort_dt(value: str | None) -> datetime:
    """Parse an ISO timestamp for correct chronological sorting.

    Falls back to epoch-min for unparseable/empty values so they sort last
    rather than raising — robustness over false precision.
    """
    if not value:
        return datetime.min.replace(tzinfo=UTC)
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return datetime.min.replace(tzinfo=UTC)


async def _count_flagged(
    db: AsyncSession,
    model: type[PendingWrite] | type[PersonalMemoryClaim],
) -> int:
    """Count rows with a flagged poison-scan verdict (DB-side)."""
    from sqlalchemy import func

    stmt = select(func.count()).select_from(model).where(model.meta.op("@>")(type_coerce(_FLAGGED_VERDICT, JSONB)))
    if model is PendingWrite:
        stmt = stmt.where(model.status == PendingWriteStatus.PENDING)
    else:
        stmt = stmt.where(model.deleted_at.is_(None))
    result = await db.execute(stmt)
    return int(result.scalar_one() or 0)


async def _fetch_source(
    db: AsyncSession,
    model: type[PendingWrite] | type[PersonalMemoryClaim],
    transform: Callable[[Any], dict[str, Any]],
    limit: int | None = None,
) -> tuple[list[dict[str, Any]], int]:
    """Fetch DB-filtered flagged rows from one source + its flagged total.

    ``limit=None`` returns every flagged row (used by the cross-source merge,
    where a Python slice produces the final page window). A positive ``limit``
    combined with ``offset`` (handled by the caller) paginates at the DB for a
    single source.
    """
    base = model.meta.op("@>")(type_coerce(_FLAGGED_VERDICT, JSONB))
    if model is PendingWrite:
        base = base & (model.status == PendingWriteStatus.PENDING)
    else:
        base = base & (model.deleted_at.is_(None))

    rows_stmt = select(model).where(base).order_by(model.created_at.desc().nullslast())
    if limit is not None:
        rows_stmt = rows_stmt.limit(limit)
    result = await db.execute(rows_stmt)
    rows = [transform(obj) for obj in result.scalars().all()]

    from sqlalchemy import func

    count_stmt = select(func.count()).select_from(model).where(base)
    total = int((await db.execute(count_stmt)).scalar_one() or 0)
    return rows, total
