"""Feedback synthesis API routes — 12 endpoints."""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select

from app.api.deps import get_current_user
from app.database import get_db
from app.models.feedback_models import FeedbackReport
from app.schemas.feedback import (
    BulkSynthesizeRequest,
    FeedbackAnalyticsResponse,
    FeedbackCompareResponse,
    FeedbackPatternResponse,
    FeedbackPatternUpdate,
    FeedbackReportResponse,
    SynthesizeRequest,
)
from app.services.feedback_synthesizer import (
    compare_feedback,
    get_feedback_analytics,
    get_feedback_report,
    list_feedback_patterns,
    list_feedback_reports,
    synthesize_bulk,
    synthesize_feedback,
    update_feedback_pattern,
)
from app.services.mission_service import get_mission

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.models.user import User

router = APIRouter(prefix="/feedback", tags=["feedback"])


@router.get("")
async def list_feedback(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """List feedback reports for the current user."""
    offset = (page - 1) * per_page

    count_q = select(func.count(FeedbackReport.id)).where(FeedbackReport.user_id == user.id)
    total = (await db.execute(count_q)).scalar() or 0

    q = (
        select(FeedbackReport)
        .where(FeedbackReport.user_id == user.id)
        .order_by(FeedbackReport.created_at.desc())
        .offset(offset)
        .limit(per_page)
    )
    result = await db.execute(q)
    reports = result.scalars().all()

    return {
        "feedback": [
            {
                "id": str(r.id),
                "mission_id": str(r.mission_id),
                "overall_score": r.overall_score,
                "efficiency_score": r.efficiency_score,
                "quality_score": r.quality_score,
                "synthesis_mode": r.synthesis_mode,
                "status": r.status,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in reports
        ],
        "total": total,
    }


@router.get("/stats")
async def get_feedback_stats(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Get feedback statistics for the current user."""
    base = select(FeedbackReport).where(FeedbackReport.user_id == user.id)
    total_q = select(func.count(FeedbackReport.id)).where(FeedbackReport.user_id == user.id)
    total = (await db.execute(total_q)).scalar() or 0

    # Score-based sentiment
    avg_q = select(func.avg(FeedbackReport.overall_score)).where(FeedbackReport.user_id == user.id)
    avg_score = (await db.execute(avg_q)).scalar() or 0

    positive_q = select(func.count(FeedbackReport.id)).where(
        FeedbackReport.user_id == user.id,
        FeedbackReport.overall_score >= 0.7,
    )
    positive = (await db.execute(positive_q)).scalar() or 0

    negative_q = select(func.count(FeedbackReport.id)).where(
        FeedbackReport.user_id == user.id,
        FeedbackReport.overall_score < 0.4,
    )
    negative = (await db.execute(negative_q)).scalar() or 0

    neutral = total - positive - negative

    return {
        "total": total,
        "positive": positive,
        "negative": negative,
        "neutral": neutral,
        "avg_score": round(avg_score, 2),
    }


def _not_found() -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")


def _bad_request(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)


# --- Synthesis ---

@router.post("/missions/{mission_id}/synthesize", response_model=FeedbackReportResponse)
async def synthesize_endpoint(
    mission_id: str,
    payload: SynthesizeRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Synthesize feedback for a completed mission."""
    mission = await get_mission(db, mission_id)
    if mission is None or mission.user_id != user.id:
        raise _not_found()

    try:
        report = await synthesize_feedback(
            db, mission_id, user.id,
            mode=payload.mode,
            include_task_analysis=payload.include_task_analysis,
            include_patterns=payload.include_patterns,
        )
    except ValueError as e:
        raise _bad_request(str(e))

    return report


@router.post("/missions/bulk-synthesize", response_model=list[FeedbackReportResponse])
async def bulk_synthesize_endpoint(
    payload: BulkSynthesizeRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Synthesize feedback for multiple missions."""
    reports = await synthesize_bulk(db, payload.mission_ids, user.id, mode=payload.mode)
    return reports


# --- Reports ---

@router.get("/reports/{report_id}", response_model=FeedbackReportResponse)
async def get_report_endpoint(
    report_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Get a specific feedback report."""
    report = await get_feedback_report(db, report_id)
    if report is None or report.user_id != user.id:
        raise _not_found()
    return report


@router.get("/missions/{mission_id}/reports", response_model=list[FeedbackReportResponse])
async def list_reports_endpoint(
    mission_id: str,
    offset: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """List feedback reports for a mission."""
    mission = await get_mission(db, mission_id)
    if mission is None or mission.user_id != user.id:
        raise _not_found()

    reports, _ = await list_feedback_reports(db, mission_id, offset=offset, limit=limit)
    return reports


@router.delete("/reports/{report_id}")
async def delete_report_endpoint(
    report_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Delete a feedback report."""
    from sqlalchemy import delete as sa_delete
    report = await get_feedback_report(db, report_id)
    if report is None or report.user_id != user.id:
        raise _not_found()
    await db.execute(sa_delete(FeedbackReport).where(FeedbackReport.id == report_id))
    await db.flush()
    return {"deleted": True}


# --- Patterns ---

@router.get("/patterns", response_model=list[FeedbackPatternResponse])
async def list_patterns_endpoint(
    pattern_type: str | None = Query(None),
    status: str | None = Query(None),
    offset: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """List feedback patterns for the current user."""
    patterns, _ = await list_feedback_patterns(
        db, user.id, pattern_type=pattern_type, status=status, offset=offset, limit=limit
    )
    return patterns


@router.patch("/patterns/{pattern_id}", response_model=FeedbackPatternResponse)
async def update_pattern_endpoint(
    pattern_id: str,
    payload: FeedbackPatternUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Update a feedback pattern (status, suggested_fix)."""
    pattern = await update_feedback_pattern(
        db, pattern_id,
        status=payload.status,
        suggested_fix=payload.suggested_fix,
    )
    if pattern is None or pattern.user_id != user.id:
        raise _not_found()
    return pattern


@router.delete("/patterns/{pattern_id}")
async def delete_pattern_endpoint(
    pattern_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Delete a feedback pattern."""
    from sqlalchemy import delete as sa_delete

    from app.models.feedback_models import FeedbackPattern
    pattern = await db.execute(select(FeedbackPattern).where(FeedbackPattern.id == pattern_id))
    pattern = pattern.scalar_one_or_none()
    if pattern is None or pattern.user_id != user.id:
        raise _not_found()
    await db.execute(sa_delete(FeedbackPattern).where(FeedbackPattern.id == pattern_id))
    await db.flush()
    return {"deleted": True}


# --- Analytics ---

@router.get("/analytics", response_model=FeedbackAnalyticsResponse)
async def analytics_endpoint(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Get aggregated feedback analytics for the current user."""
    return await get_feedback_analytics(db, user.id)


# --- Compare ---

@router.post("/compare", response_model=FeedbackCompareResponse)
async def compare_endpoint(
    mission_ids: list[str],
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Compare feedback reports across multiple missions."""
    if len(mission_ids) < 2:
        raise _bad_request("At least 2 mission IDs required for comparison")
    return await compare_feedback(db, mission_ids)


# --- Improvements Integration ---

@router.get("/missions/{mission_id}/improvements")
async def list_mission_improvements(
    mission_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """List improvement suggestions for a mission (from feedback synthesis)."""
    from sqlalchemy import select

    from app.models.mission_models import MissionImprovement

    mission = await get_mission(db, mission_id)
    if mission is None or mission.user_id != user.id:
        raise _not_found()

    result = await db.execute(
        select(MissionImprovement)
        .where(MissionImprovement.mission_id == mission_id)
        .order_by(MissionImprovement.created_at.desc())
    )
    return list(result.scalars().all())


@router.post("/missions/{mission_id}/improvements/{improvement_id}/apply")
async def apply_improvement_endpoint(
    mission_id: str,
    improvement_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Mark an improvement suggestion as applied."""
    from sqlalchemy import select

    from app.models.mission_models import MissionImprovement

    mission = await get_mission(db, mission_id)
    if mission is None or mission.user_id != user.id:
        raise _not_found()

    result = await db.execute(
        select(MissionImprovement).where(MissionImprovement.id == improvement_id)
    )
    improvement = result.scalar_one_or_none()
    if improvement is None:
        raise _not_found()

    improvement.status = "applied"
    await db.flush()
    return {"applied": True, "improvement_id": improvement_id}
