import json
from datetime import UTC, datetime, timedelta

from redis.asyncio import Redis
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.mission_models import Mission, MissionTask

redis_client = Redis.from_url(settings.REDIS_URL, decode_responses=True)


async def get_dashboard_analytics(db: AsyncSession) -> dict:
    seven_days_ago = datetime.now(UTC) - timedelta(days=7)

    total_stmt = select(func.count(Mission.id)).where(
        Mission.created_at >= seven_days_ago
    )
    total = (await db.execute(total_stmt)).scalar() or 0

    success_stmt = select(func.count(Mission.id)).where(
        Mission.created_at >= seven_days_ago, Mission.status == "completed"
    )
    success_count = (await db.execute(success_stmt)).scalar() or 0
    success_rate = (success_count / total * 100) if total > 0 else 0.0

    avg_stmt = select(
        func.avg(
            func.extract("epoch", Mission.completed_at)
            - func.extract("epoch", Mission.started_at)
        )
    ).where(
        Mission.created_at >= seven_days_ago,
        Mission.started_at.isnot(None),
        Mission.completed_at.isnot(None),
    )
    avg_runtime = (await db.execute(avg_stmt)).scalar() or 0.0

    queue_stmt = select(func.count(Mission.id)).where(Mission.status == "queued")
    queue_depth = (await db.execute(queue_stmt)).scalar() or 0

    failed_stmt = (
        select(
            Mission.title.label("mission_name"),
            func.count(Mission.id).label("failure_count"),
        )
        .where(Mission.status == "failed", Mission.created_at >= seven_days_ago)
        .group_by(Mission.title)
        .order_by(func.count(Mission.id).desc())
        .limit(5)
    )
    failed_result = await db.execute(failed_stmt)
    top_failed = [
        {"mission_name": row.mission_name, "failure_count": row.failure_count}
        for row in failed_result
    ]

    return {
        "seven_day_success_rate": round(success_rate, 2),
        "avg_runtime_seconds": round(avg_runtime, 2),
        "current_queue_depth": queue_depth,
        "top_failed_missions": top_failed,
    }


async def get_firefighting_metrics(db: AsyncSession, hours: int = 24) -> dict:
    """Retrieve firefighting metrics for failed missions in the last `hours` period.
    Satisfies: AC-1 (failed mission count), AC-2 (avg retry count),
             AC-3 (top 3 error codes), AC-4 (manual intervention missions)
    """
    now = datetime.now(UTC)
    since = now - timedelta(hours=hours)

    # H-4: Redis caching with 5min TTL (300 seconds)
    cache_key = f"firefighting_metrics:{hours}"
    cached = await redis_client.get(cache_key)
    if cached:
        return json.loads(cached)

    # AC-1: Total failed mission count in period
    failed_count_stmt = select(func.count(Mission.id)).where(
        Mission.status == "failed", Mission.created_at >= since
    )
    failed_mission_count = (await db.execute(failed_count_stmt)).scalar() or 0

    # AC-2: Avg retry count per failed mission
    avg_retry = 0.0
    if failed_mission_count > 0:
        retry_stmt = (
            select(func.sum(MissionTask.retry_count))
            .join(Mission, MissionTask.mission_id == Mission.id)
            .where(
                Mission.status == "failed",
                Mission.created_at >= since,
                MissionTask.retry_count.isnot(None),
            )
        )
        total_retries = (await db.execute(retry_stmt)).scalar() or 0
        avg_retry = total_retries / failed_mission_count

    # AC-3: Top 3 error codes by frequency (H-3 fix: group by error_message which stores the error code)
    error_code_stmt = (
        select(
            Mission.error_message.label("error_code"),
            func.count(Mission.id).label("count"),
        )
        .where(
            Mission.status == "failed",
            Mission.created_at >= since,
            Mission.error_message.isnot(None),
        )
        .group_by(Mission.error_message)
        .order_by(func.count(Mission.id).desc())
        .limit(3)
    )
    error_code_result = await db.execute(error_code_stmt)
    top_error_codes = [
        {"code": row.error_code, "count": row.count} for row in error_code_result
    ]

    # AC-4: Manual intervention missions (H-2 fix: max retries exceeded)
    manual_intervention_stmt = (
        select(
            Mission.id.label("missionId"),
            Mission.error_message.label("errorCode"),
            Mission.updated_at.label("lastUpdateTimestamp"),
        )
        .join(MissionTask, MissionTask.mission_id == Mission.id)
        .where(
            Mission.status == "failed",
            Mission.created_at >= since,
            MissionTask.retry_count >= MissionTask.max_retries,
            MissionTask.retry_count.isnot(None),
            MissionTask.max_retries.isnot(None),
        )
        .distinct(Mission.id)
        .order_by(Mission.updated_at.desc())
    )
    manual_intervention_result = await db.execute(manual_intervention_stmt)
    manual_intervention_missions = [
        {
            "missionId": str(row.missionId),
            "errorCode": row.errorCode or "UNKNOWN",
            "lastUpdateTimestamp": (
                row.lastUpdateTimestamp.isoformat() if row.lastUpdateTimestamp else ""
            ),
        }
        for row in manual_intervention_result
    ]

    result = {
        "failedMissionCount": failed_mission_count,
        "avgRetryCount": round(avg_retry, 2),
        "topErrorCodes": top_error_codes,
        "manualInterventionMissions": manual_intervention_missions,
    }

    # Cache for 5 minutes (300 seconds) per Architecture Decision 12
    await redis_client.setex(cache_key, 300, json.dumps(result))
    return result
