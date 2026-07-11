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

from typing import TYPE_CHECKING, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select

from app.api.deps import get_current_user, get_db, require_role
from app.models.memory_models import PendingWrite, PendingWriteStatus
from app.models.personal_memory_models import PersonalMemoryClaim

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.models.user import User

router = APIRouter(prefix="/governance", tags=["governance"])


# ── Serialization helpers ──────────────────────────────────────────────────

_DEFAULT_PAGE_SIZE = 50
_MAX_PAGE_SIZE = 200


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
    (retro) sources. Results are ordered by recency (newest first) within
    each source, then merged and paginated across sources.
    """
    offset = (page - 1) * page_size

    rows: list[dict[str, Any]] = []

    if source in ("live", "all"):
        stmt = (
            select(PendingWrite)
            .where(PendingWrite.status == PendingWriteStatus.PENDING)
            .order_by(PendingWrite.created_at.desc())
        )
        result = await db.execute(stmt)
        rows.extend(_pending_row(pw) for pw in result.scalars().all() if _verdict(pw.meta))

    if source in ("retro", "all"):
        stmt = (
            select(PersonalMemoryClaim)
            .where(PersonalMemoryClaim.deleted_at.is_(None))
            .order_by(PersonalMemoryClaim.created_at.desc())
        )
        result = await db.execute(stmt)
        rows.extend(_claim_row(claim) for claim in result.scalars().all() if _verdict(claim.meta))

    # Merge + stable sort by created_at descending (None last).
    rows.sort(
        key=lambda r: (r.get("created_at") is not None, r.get("created_at") or ""),
        reverse=True,
    )

    total = len(rows)
    page_rows = rows[offset : offset + page_size]
    pages = (total + page_size - 1) // page_size if page_size else 1

    return {
        "items": page_rows,
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": pages,
        "source": source,
    }
