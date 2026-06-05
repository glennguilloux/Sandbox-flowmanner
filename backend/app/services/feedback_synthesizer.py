"""Feedback synthesizer — analyzes mission execution and generates feedback."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import desc, func, select

from app.models.feedback_models import FeedbackPattern, FeedbackReport
from app.models.mission_models import Mission, MissionTask

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


async def synthesize_feedback(
    db: AsyncSession,
    mission_id: str,
    user_id: int,
    mode: str = "auto",
    include_task_analysis: bool = True,
    include_patterns: bool = True,
) -> FeedbackReport:
    """Synthesize feedback for a completed mission.

    Analyzes task outputs, errors, timing, and token usage to generate
    a structured feedback report.
    """
    # Load mission and tasks
    mission = await db.execute(select(Mission).where(Mission.id == mission_id))
    mission = mission.scalar_one_or_none()
    if not mission:
        raise ValueError("Mission not found")

    tasks = await db.execute(
        select(MissionTask)
        .where(MissionTask.mission_id == mission_id)
        .order_by(MissionTask.order_index)
    )
    tasks = list(tasks.scalars().all())

    # Analyze tasks
    task_analysis = []
    errors = []
    total_tokens = 0
    total_cost = 0.0
    completed_count = 0
    failed_count = 0
    skipped_count = 0

    for task in tasks:
        task_info = {
            "task_id": str(task.id),
            "title": task.title,
            "status": task.status,
            "task_type": task.task_type,
            "tokens_used": task.tokens_used or 0,
            "cost": task.cost or 0.0,
        }

        if task.status == "completed":
            completed_count += 1
            if task.output_data:
                task_info["output_size"] = len(str(task.output_data))
        elif task.status == "failed":
            failed_count += 1
            errors.append({
                "task_id": str(task.id),
                "title": task.title,
                "error": task.error_message or "Unknown error",
                "task_type": task.task_type,
            })
        elif task.status == "skipped":
            skipped_count += 1

        total_tokens += task.tokens_used or 0
        total_cost += task.cost or 0.0

        if include_task_analysis:
            task_analysis.append(task_info)

    # Calculate scores
    total_tasks = len(tasks)
    completion_rate = completed_count / total_tasks if total_tasks > 0 else 0.0

    overall_score = _calculate_overall_score(
        completion_rate, failed_count, total_tasks, mission
    )
    efficiency_score = _calculate_efficiency_score(
        total_tokens, total_cost, completed_count, total_tasks
    )
    quality_score = _calculate_quality_score(mission, tasks)

    # Generate strengths and weaknesses
    strengths = _identify_strengths(mission, tasks, completion_rate)
    weaknesses = _identify_weaknesses(mission, tasks, errors)
    suggestions = _generate_suggestions(mission, tasks, errors, completion_rate)

    # Token efficiency
    token_efficiency = {
        "total_tokens": total_tokens,
        "total_cost": round(total_cost, 6),
        "tokens_per_task": total_tokens // total_tasks if total_tasks > 0 else 0,
        "cost_per_task": round(total_cost / total_tasks, 6) if total_tasks > 0 else 0,
    }

    # Create report
    report = FeedbackReport(
        id=str(uuid.uuid4()),
        mission_id=mission_id,
        user_id=user_id,
        overall_score=round(overall_score, 2),
        efficiency_score=round(efficiency_score, 2),
        quality_score=round(quality_score, 2),
        strengths={"items": strengths},
        weaknesses={"items": weaknesses},
        suggestions={"items": suggestions},
        task_analysis={"tasks": task_analysis} if include_task_analysis else None,
        error_summary={"errors": errors, "total_errors": len(errors)},
        token_efficiency=token_efficiency,
        synthesis_mode=mode,
        status="completed",
    )
    db.add(report)

    # Update mission feedback fields
    mission.feedback_score = int(overall_score * 10)  # 0-100 scale
    mission.feedback_text = "; ".join(suggestions[:3]) if suggestions else None

    # Track patterns if requested
    if include_patterns and errors:
        await _track_patterns(db, user_id, mission_id, errors)

    await db.flush()
    await db.refresh(report)
    return report


async def get_feedback_report(db: AsyncSession, report_id: str) -> FeedbackReport | None:
    result = await db.execute(select(FeedbackReport).where(FeedbackReport.id == report_id))
    return result.scalar_one_or_none()


async def list_feedback_reports(
    db: AsyncSession, mission_id: str, offset: int = 0, limit: int = 20
) -> tuple[list[FeedbackReport], int]:
    total = await db.execute(
        select(func.count()).select_from(FeedbackReport).where(FeedbackReport.mission_id == mission_id)
    )
    total = total.scalar() or 0

    result = await db.execute(
        select(FeedbackReport)
        .where(FeedbackReport.mission_id == mission_id)
        .order_by(desc(FeedbackReport.created_at))
        .offset(offset)
        .limit(limit)
    )
    return list(result.scalars().all()), total


async def list_feedback_patterns(
    db: AsyncSession, user_id: int, pattern_type: str | None = None,
    status: str | None = None, offset: int = 0, limit: int = 20
) -> tuple[list[FeedbackPattern], int]:
    query = select(FeedbackPattern).where(FeedbackPattern.user_id == user_id)
    if pattern_type:
        query = query.where(FeedbackPattern.pattern_type == pattern_type)
    if status:
        query = query.where(FeedbackPattern.status == status)

    total = await db.execute(select(func.count()).select_from(query.subquery()))
    total = total.scalar() or 0

    result = await db.execute(
        query.order_by(desc(FeedbackPattern.frequency)).offset(offset).limit(limit)
    )
    return list(result.scalars().all()), total


async def update_feedback_pattern(
    db: AsyncSession, pattern_id: str, **kwargs
) -> FeedbackPattern | None:
    result = await db.execute(select(FeedbackPattern).where(FeedbackPattern.id == pattern_id))
    pattern = result.scalar_one_or_none()
    if not pattern:
        return None
    for key, value in kwargs.items():
        if value is not None and hasattr(pattern, key):
            setattr(pattern, key, value)
    await db.flush()
    await db.refresh(pattern)
    return pattern


async def get_feedback_analytics(db: AsyncSession, user_id: int) -> dict:
    """Aggregate feedback analytics for a user."""
    reports = await db.execute(
        select(FeedbackReport).where(FeedbackReport.user_id == user_id)
    )
    reports = list(reports.scalars().all())

    if not reports:
        return {
            "total_reports": 0,
            "avg_overall_score": 0.0,
            "avg_efficiency_score": None,
            "avg_quality_score": None,
            "top_patterns": [],
            "score_trend": [],
        }

    scores = [r.overall_score for r in reports]
    eff_scores = [r.efficiency_score for r in reports if r.efficiency_score is not None]
    qual_scores = [r.quality_score for r in reports if r.quality_score is not None]

    # Score trend (last 20)
    recent = sorted(reports, key=lambda r: r.created_at or datetime.min)[:20]
    score_trend = [
        {"date": r.created_at.isoformat() if r.created_at else None, "score": r.overall_score}
        for r in recent
    ]

    # Top patterns
    patterns = await db.execute(
        select(FeedbackPattern)
        .where(FeedbackPattern.user_id == user_id, FeedbackPattern.status == "active")
        .order_by(desc(FeedbackPattern.frequency))
        .limit(5)
    )
    patterns = list(patterns.scalars().all())
    top_patterns = [
        {"type": p.pattern_type, "description": p.description, "frequency": p.frequency, "severity": p.severity}
        for p in patterns
    ]

    return {
        "total_reports": len(reports),
        "avg_overall_score": round(sum(scores) / len(scores), 2),
        "avg_efficiency_score": round(sum(eff_scores) / len(eff_scores), 2) if eff_scores else None,
        "avg_quality_score": round(sum(qual_scores) / len(qual_scores), 2) if qual_scores else None,
        "top_patterns": top_patterns,
        "score_trend": score_trend,
    }


async def compare_feedback(db: AsyncSession, mission_ids: list[str]) -> dict:
    """Compare feedback reports across multiple missions."""
    reports = []
    for mid in mission_ids:
        result = await db.execute(
            select(FeedbackReport)
            .where(FeedbackReport.mission_id == mid)
            .order_by(desc(FeedbackReport.created_at))
            .limit(1)
        )
        report = result.scalar_one_or_none()
        if report:
            reports.append(report)

    if len(reports) < 2:
        return {"missions": [], "score_delta": {}, "improvements": [], "regressions": []}

    summaries = [
        {
            "mission_id": r.mission_id,
            "overall_score": r.overall_score,
            "efficiency_score": r.efficiency_score,
            "quality_score": r.quality_score,
        }
        for r in reports
    ]

    first, last = reports[0], reports[-1]
    score_delta = {
        "overall": round(last.overall_score - first.overall_score, 2),
        "efficiency": round((last.efficiency_score or 0) - (first.efficiency_score or 0), 2),
        "quality": round((last.quality_score or 0) - (first.quality_score or 0), 2),
    }

    improvements = []
    regressions = []
    if score_delta["overall"] > 0:
        improvements.append(f"Overall score improved by {score_delta['overall']}")
    elif score_delta["overall"] < 0:
        regressions.append(f"Overall score decreased by {abs(score_delta['overall'])}")

    return {
        "missions": summaries,
        "score_delta": score_delta,
        "improvements": improvements,
        "regressions": regressions,
    }


async def synthesize_bulk(
    db: AsyncSession, mission_ids: list[str], user_id: int, mode: str = "auto"
) -> list[FeedbackReport]:
    """Synthesize feedback for multiple missions."""
    reports = []
    for mid in mission_ids:
        try:
            report = await synthesize_feedback(db, mid, user_id, mode=mode, include_patterns=False)
            reports.append(report)
        except ValueError:
            continue
    return reports


def _calculate_overall_score(
    completion_rate: float, failed_count: int, total_tasks: int, mission: Mission
) -> float:
    """Score 0.0-1.0 based on completion, failure rate, and timing."""
    base = completion_rate * 0.6
    failure_penalty = (failed_count / total_tasks * 0.3) if total_tasks > 0 else 0
    timing_bonus = 0.1
    if mission.started_at and mission.completed_at:
        duration = (mission.completed_at - mission.started_at).total_seconds()
        if duration < 60:
            timing_bonus = 0.15
        elif duration < 300:
            timing_bonus = 0.1
        else:
            timing_bonus = 0.05
    return max(0.0, min(1.0, base - failure_penalty + timing_bonus))


def _calculate_efficiency_score(
    total_tokens: int, total_cost: float, completed: int, total: int
) -> float:
    """Score based on token/cost efficiency."""
    if total == 0:
        return 0.0
    completion_bonus = (completed / total) * 0.5
    # Penalize high token usage (100k+ tokens = penalty)
    token_efficiency = max(0, 1.0 - (total_tokens / 200000)) * 0.3
    cost_efficiency = max(0, 1.0 - (total_cost / 1.0)) * 0.2
    return min(1.0, completion_bonus + token_efficiency + cost_efficiency)


def _calculate_quality_score(mission: Mission, tasks: list[MissionTask]) -> float:
    """Score based on output quality indicators."""
    if not tasks:
        return 0.0
    completed = [t for t in tasks if t.status == "completed"]
    if not completed:
        return 0.0
    # Check for output data presence
    has_outputs = sum(1 for t in completed if t.output_data)
    output_ratio = has_outputs / len(completed) if completed else 0
    # Check for prior feedback
    prior_bonus = 0.1 if mission.feedback_score and mission.feedback_score > 70 else 0
    return min(1.0, output_ratio * 0.8 + prior_bonus + 0.1)


def _identify_strengths(mission, tasks, completion_rate) -> list[str]:
    strengths = []
    if completion_rate >= 0.9:
        strengths.append("High task completion rate")
    if completion_rate == 1.0:
        strengths.append("All tasks completed successfully")
    completed = [t for t in tasks if t.status == "completed"]
    if completed and all(t.output_data for t in completed):
        strengths.append("All completed tasks produced output")
    if mission.started_at and mission.completed_at:
        duration = (mission.completed_at - mission.started_at).total_seconds()
        if duration < 120:
            strengths.append("Fast execution time")
    return strengths


def _identify_weaknesses(mission, tasks, errors) -> list[str]:
    weaknesses = []
    if errors:
        weaknesses.append(f"{len(errors)} task(s) failed")
    skipped = [t for t in tasks if t.status == "skipped"]
    if skipped:
        weaknesses.append(f"{len(skipped)} task(s) skipped due to dependencies")
    no_output = [t for t in tasks if t.status == "completed" and not t.output_data]
    if no_output:
        weaknesses.append(f"{len(no_output)} completed task(s) produced no output")
    return weaknesses


def _generate_suggestions(mission, tasks, errors, completion_rate) -> list[str]:
    suggestions = []
    if completion_rate < 0.5:
        suggestions.append("Consider breaking mission into smaller, more focused tasks")
    if len(errors) > 2:
        suggestions.append("Multiple failures detected — review error patterns and add retry logic")
    for error in errors[:3]:
        if "timeout" in (error.get("error") or "").lower():
            suggestions.append(f"Task '{error['title']}' timed out — increase timeout or simplify")
        elif "rate limit" in (error.get("error") or "").lower():
            suggestions.append("Rate limiting detected — add delays between API calls")
    if not suggestions:
        suggestions.append("Mission executed within normal parameters")
    return suggestions


async def _track_patterns(db, user_id, mission_id, errors):
    """Track recurring error patterns."""
    for error in errors:
        error_msg = error.get("error", "")
        # Check for existing similar pattern
        existing = await db.execute(
            select(FeedbackPattern).where(
                FeedbackPattern.user_id == user_id,
                FeedbackPattern.pattern_type == "error",
                FeedbackPattern.description.ilike(f"%{error_msg[:50]}%"),
            )
        )
        pattern = existing.scalar_one_or_none()
        if pattern:
            pattern.frequency += 1
            ids = pattern.example_mission_ids or {"mission_ids": []}
            if mission_id not in ids.get("mission_ids", []):
                ids["mission_ids"].append(mission_id)
                pattern.example_mission_ids = ids
        else:
            db.add(FeedbackPattern(
                id=str(uuid.uuid4()),
                user_id=user_id,
                pattern_type="error",
                description=f"Error in task '{error['title']}': {error_msg[:200]}",
                frequency=1,
                severity="high" if "timeout" in error_msg.lower() else "medium",
                example_mission_ids={"mission_ids": [mission_id]},
                suggested_fix=_suggest_fix_for_error(error_msg),
                status="active",
            ))


def _suggest_fix_for_error(error_msg: str) -> str | None:
    error_lower = error_msg.lower()
    if "timeout" in error_lower:
        return "Increase task timeout or break into smaller tasks"
    if "rate limit" in error_lower:
        return "Add rate limiting delays between API calls"
    if "auth" in error_lower or "401" in error_lower:
        return "Check API credentials and token expiration"
    if "not found" in error_lower or "404" in error_lower:
        return "Verify endpoint URLs and resource IDs"
    return None
