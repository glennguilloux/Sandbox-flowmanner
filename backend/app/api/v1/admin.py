"""Admin API router — user management, system health, feature flags, maintenance."""

import os
import time
from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_role
from app.database import get_db
from app.models.phase4_models import FeatureFlag as DBFeatureFlag
from app.models.user import User

router = APIRouter(prefix="/admin", tags=["admin"])


# ── Schemas ──────────────────────────────────────────────────────────────────


class AdminUser(BaseModel):
    id: int
    email: str
    username: str | None = None
    full_name: str | None = None
    role: str
    is_admin: bool
    is_active: bool
    created_at: str | None = None


class UserListResponse(BaseModel):
    users: list[AdminUser]
    total: int
    page: int
    page_size: int
    pages: int


class SystemHealth(BaseModel):
    status: str
    components: dict


class ResourceMetrics(BaseModel):
    cpu: dict
    memory: dict
    disk: dict


class ApiStats(BaseModel):
    requests_per_minute: float
    avg_latency_ms: float
    error_rate: float
    slowest_endpoints: list


class FeatureFlag(BaseModel):
    id: int
    key: str
    name: str
    description: str | None = None
    enabled_globally: bool
    created_at: str | None = None
    updated_at: str | None = None


class MaintenanceStatus(BaseModel):
    active: bool
    message: str | None = None
    estimated_duration: str | None = None
    activated_at: str | None = None


# ── In-memory stores ────────────────────────────────────────────────────────

_maintenance = MaintenanceStatus(active=False)


# ── User Management ─────────────────────────────────────────────────────────


@router.get("/users", response_model=UserListResponse)
async def list_users(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    role: str | None = None,
    is_active: bool | None = None,
    search: str | None = None,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_role("admin")),
):
    query = select(User)
    count_query = select(func.count(User.id))

    if role:
        query = query.where(User.role == role)
        count_query = count_query.where(User.role == role)
    if is_active is not None:
        query = query.where(User.is_active == is_active)
        count_query = count_query.where(User.is_active == is_active)
    if search:
        search_filter = User.email.ilike(f"%{search}%")
        query = query.where(search_filter)
        count_query = count_query.where(search_filter)

    total = (await db.execute(count_query)).scalar() or 0
    pages = max(1, (total + page_size - 1) // page_size)

    result = await db.execute(
        query.offset((page - 1) * page_size).limit(page_size).order_by(User.id)
    )
    users = result.scalars().all()

    return UserListResponse(
        users=[
            AdminUser(
                id=u.id,
                email=u.email,
                username=getattr(u, "username", None),
                full_name=getattr(u, "full_name", None),
                role=u.role,
                is_admin=u.is_admin,
                is_active=u.is_active,
                created_at=u.created_at.isoformat() if u.created_at else None,
            )
            for u in users
        ],
        total=total,
        page=page,
        page_size=page_size,
        pages=pages,
    )


@router.get("/users/{user_id}", response_model=AdminUser)
async def get_user(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_role("admin")),
):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalars().first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return AdminUser(
        id=user.id,
        email=user.email,
        username=getattr(user, "username", None),
        full_name=getattr(user, "full_name", None),
        role=user.role,
        is_admin=user.is_admin,
        is_active=user.is_active,
        created_at=user.created_at.isoformat() if user.created_at else None,
    )


@router.patch("/users/{user_id}")
async def update_user(
    user_id: int,
    data: dict,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_role("admin")),
):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalars().first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    for field in ("full_name", "role", "is_active", "is_admin"):
        if field in data:
            setattr(user, field, data[field])

    await db.commit()
    return {"status": "updated"}


@router.delete("/users/{user_id}")
async def delete_user(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_role("admin")),
):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalars().first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    await db.delete(user)
    await db.commit()
    return {"status": "deleted"}


@router.get("/users/{user_id}/activity")
async def get_user_activity(
    user_id: int,
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_role("admin")),
):
    from sqlalchemy import text

    result = await db.execute(
        text(
            """
            SELECT action, action_details, ip_address, endpoint, method, timestamp
            FROM audit_logs
            WHERE user_id = :user_id
            ORDER BY timestamp DESC
            LIMIT :limit
            """
        ),
        {"user_id": str(user_id), "limit": limit},
    )
    rows = result.all()

    return {
        "activity": [
            {
                "action": row[0],
                "details": row[1],
                "ip_address": row[2],
                "endpoint": row[3],
                "method": row[4],
                "timestamp": row[5].isoformat() if row[5] else None,
            }
            for row in rows
        ]
    }


# ── System Health & Metrics ──────────────────────────────────────────────────


@router.get("/system/health", response_model=SystemHealth)
async def get_system_health(
    admin: User = Depends(require_role("admin")),
):
    components = {}
    try:
        import redis as redis_lib

        r = redis_lib.Redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379"))
        start = time.time()
        r.ping()
        components["redis"] = {
            "status": "healthy",
            "latency_ms": round((time.time() - start) * 1000, 1),
        }
    except Exception as e:
        components["redis"] = {"status": "unhealthy", "detail": str(e)}

    components["database"] = {"status": "healthy"}
    return SystemHealth(status="ok", components=components)


@router.get("/system/metrics", response_model=ResourceMetrics)
async def get_system_metrics(
    admin: User = Depends(require_role("admin")),
):
    try:
        import psutil

        cpu = psutil.cpu_percent(interval=0.1)
        mem = psutil.virtual_memory()
        disk = psutil.disk_usage("/")
        return ResourceMetrics(
            cpu={"load_1min": cpu, "load_5min": None, "load_15min": None},
            memory={
                "total_mb": round(mem.total / 1024 / 1024),
                "used_mb": round(mem.used / 1024 / 1024),
                "usage_percent": mem.percent,
            },
            disk={
                "total_gb": round(disk.total / 1024 / 1024 / 1024, 1),
                "used_gb": round(disk.used / 1024 / 1024 / 1024, 1),
                "usage_percent": round(disk.percent, 1),
            },
        )
    except ImportError:
        return ResourceMetrics(
            cpu={"load_1min": None, "load_5min": None, "load_15min": None},
            memory={"total_mb": 0, "used_mb": 0, "usage_percent": 0},
            disk={"total_gb": 0, "used_gb": 0, "usage_percent": 0},
        )


@router.get("/system/api-stats", response_model=ApiStats)
async def get_api_stats(
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_role("admin")),
):
    from sqlalchemy import text

    # Get request stats from audit_logs (last 5 minutes)
    result = await db.execute(
        text(
            """
            SELECT
                COUNT(*) as total,
                EXTRACT(EPOCH FROM (MAX(timestamp) - MIN(timestamp))) / 60.0 as span_minutes
            FROM audit_logs
            WHERE timestamp > NOW() - INTERVAL '5 minutes'
            """
        )
    )
    row = result.first()
    total = row[0] if row else 0
    span = row[1] if row and row[1] and row[1] > 0 else 5.0
    rpm = total / span if span > 0 else 0

    return ApiStats(
        requests_per_minute=round(rpm, 1),
        avg_latency_ms=0,
        error_rate=0,
        slowest_endpoints=[],
    )


@router.get("/system/active-users")
async def get_active_users(
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_role("admin")),
):
    from sqlalchemy import text

    result = await db.execute(
        text(
            """
            SELECT
                COUNT(DISTINCT user_id) FILTER (WHERE timestamp > NOW() - INTERVAL '5 minutes') as last_5min,
                COUNT(DISTINCT user_id) FILTER (WHERE timestamp > NOW() - INTERVAL '1 hour') as last_1hour,
                COUNT(DISTINCT user_id) FILTER (WHERE timestamp > NOW() - INTERVAL '24 hours') as last_24hour
            FROM audit_logs
            WHERE user_id IS NOT NULL
              AND timestamp > NOW() - INTERVAL '24 hours'
            """
        )
    )
    row = result.first()

    return {
        "last_5min": row[0] if row else 0,
        "last_1hour": row[1] if row else 0,
        "last_24hour": row[2] if row else 0,
    }


# ── Feature Flags (DB-backed) ───────────────────────────────────────────────


def _flag_response(f: DBFeatureFlag) -> FeatureFlag:
    return FeatureFlag(
        id=f.id,
        key=f.key,
        name=f.name,
        description=f.description,
        enabled_globally=f.enabled_globally,
        created_at=f.created_at.isoformat() if f.created_at else None,
        updated_at=f.updated_at.isoformat() if f.updated_at else None,
    )


@router.get("/feature-flags", response_model=list[FeatureFlag])
async def list_feature_flags(
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_role("admin")),
):
    result = await db.execute(select(DBFeatureFlag).order_by(DBFeatureFlag.id))
    return [_flag_response(f) for f in result.scalars().all()]


@router.post("/feature-flags", response_model=FeatureFlag)
async def create_feature_flag(
    data: dict,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_role("admin")),
):
    flag = DBFeatureFlag(
        key=data["key"],
        name=data["name"],
        description=data.get("description"),
        enabled_globally=False,
    )
    db.add(flag)
    await db.flush()
    await db.refresh(flag)
    return _flag_response(flag)


@router.patch("/feature-flags/{key}", response_model=FeatureFlag)
async def update_feature_flag(
    key: str,
    data: dict,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_role("admin")),
):
    result = await db.execute(select(DBFeatureFlag).where(DBFeatureFlag.key == key))
    flag = result.scalar_one_or_none()
    if not flag:
        raise HTTPException(status_code=404, detail="Feature flag not found")
    if "name" in data:
        flag.name = data["name"]
    if "description" in data:
        flag.description = data["description"]
    if "enabled_globally" in data:
        flag.enabled_globally = data["enabled_globally"]
    await db.flush()
    await db.refresh(flag)
    return _flag_response(flag)


@router.delete("/feature-flags/{key}")
async def delete_feature_flag(
    key: str,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_role("admin")),
):
    result = await db.execute(select(DBFeatureFlag).where(DBFeatureFlag.key == key))
    flag = result.scalar_one_or_none()
    if not flag:
        raise HTTPException(status_code=404, detail="Feature flag not found")
    await db.delete(flag)
    return {"status": "deleted"}


@router.post("/feature-flags/{key}/toggle", response_model=FeatureFlag)
async def toggle_feature_flag(
    key: str,
    enabled: bool = Query(...),
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_role("admin")),
):
    result = await db.execute(select(DBFeatureFlag).where(DBFeatureFlag.key == key))
    flag = result.scalar_one_or_none()
    if not flag:
        raise HTTPException(status_code=404, detail="Feature flag not found")
    flag.enabled_globally = enabled
    await db.flush()
    await db.refresh(flag)
    return _flag_response(flag)


# ── Reindex (Phase 2.5) ─────────────────────────────────────────────────────


class ReindexResponse(BaseModel):
    tools_indexed: int
    capabilities_indexed: int
    total: int
    source: str


@router.post("/reindex", response_model=ReindexResponse)
async def reindex_qdrant(
    source: Literal["db", "registry"] = Query(
        "db",
        description="'db' to rebuild from Postgres tables, 'registry' to rebuild from in-memory ToolRegistry",
    ),
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_role("admin")),
):
    """Rebuild the Qdrant vector index from the canonical data source.

    - ``source=db`` (default): reads tools + capabilities directly from
      ``tools_catalog`` and ``capabilities_catalog`` tables.
    - ``source=registry``: reads from the in-memory ``ToolRegistry``
      (same as startup hydration).
    """
    from app.services.tool_discovery_service import get_discovery_service

    service = get_discovery_service()

    if source == "registry":
        count = service.reindex()
        return ReindexResponse(
            tools_indexed=count,
            capabilities_indexed=0,
            total=count,
            source="registry",
        )

    # Default: rebuild from DB
    result = await service.reindex_from_db(db)
    return ReindexResponse(
        tools_indexed=result["tools_indexed"],
        capabilities_indexed=result["capabilities_indexed"],
        total=result["total"],
        source="db",
    )


# ── Maintenance Mode ────────────────────────────────────────────────────────


@router.get("/maintenance", response_model=MaintenanceStatus)
async def get_maintenance_status(
    admin: User = Depends(require_role("admin")),
):
    return _maintenance


@router.post("/maintenance/activate", response_model=MaintenanceStatus)
async def activate_maintenance(
    data: dict,
    admin: User = Depends(require_role("admin")),
):
    global _maintenance
    _maintenance = MaintenanceStatus(
        active=True,
        message=data.get("message", "System maintenance in progress"),
        estimated_duration=data.get("estimated_duration"),
        activated_at=datetime.now(UTC).isoformat(),
    )
    return _maintenance


@router.post("/maintenance/deactivate")
async def deactivate_maintenance(
    admin: User = Depends(require_role("admin")),
):
    global _maintenance
    _maintenance = MaintenanceStatus(active=False)
    return {"active": False}
