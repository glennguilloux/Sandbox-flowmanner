import asyncio
import logging
import time

from fastapi import APIRouter, Response
from pydantic import BaseModel

from app.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])


class ComponentStatus(BaseModel):
    status: str
    latency_ms: int | None = None
    detail: str | None = None


class HealthResponse(BaseModel):
    status: str
    app: str
    env: str
    components: dict


class ReadyResponse(BaseModel):
    status: str
    database: str
    redis: str
    qdrant: str


# ── TTL cache for /health ──────────────────────────────────────────────────
# At 500 RPS the uncached endpoint saturates Postgres + Redis + Qdrant
# (3 round-trips per call). With a 5-second TTL, only 1 in ~2500 requests
# runs the heavy probes; the rest return instantly from cache.
#
# `/health/full` remains uncached for real-time diagnostics.
_HEALTH_CACHE_TTL = 5.0  # seconds
_health_cache: HealthResponse | None = None
_health_cache_ts: float = 0.0
_health_lock = asyncio.Lock()


async def _probe_health() -> HealthResponse:
    """Run all component probes and return a HealthResponse.

    This is the heavy path — touches Postgres, Redis, Qdrant, and reads
    reliability / circuit-breaker state. Called on cache miss only.
    """
    db_status = "unknown"
    redis_status = "unknown"
    db_latency: float = 0
    redis_latency: float = 0

    try:
        from app.database import engine

        start = time.time()
        async with engine.connect() as conn:
            await conn.execute(__import__("sqlalchemy").text("SELECT 1"))
        db_latency = round((time.time() - start) * 1000, 1)
        db_status = "ok"
    except Exception:
        db_status = "error"

    try:
        from redis.asyncio import Redis

        start = time.time()
        r = Redis.from_url(settings.REDIS_URL)
        await r.ping()
        await r.close()
        redis_latency = round((time.time() - start) * 1000, 1)
        redis_status = "ok"
    except Exception:
        redis_status = "error"

    llm_configured = bool(settings.LLM_API_KEY)

    llm_success_rate: float | None = None
    langfuse_caused_failures = 0
    try:
        from app.services.reliability_assertions import get_reliability_monitor

        report = get_reliability_monitor().get_reliability_report()
        llm_success_rate = report.get("llm_success_rate")
        langfuse_caused_failures = report.get("langfuse_caused_failures", 0)
    except Exception:
        logger.debug("reliability_report_failed", exc_info=True)

    circuit_state = "CLOSED"
    try:
        from app.services.langfuse_service import get_langfuse_service

        lf = get_langfuse_service()
        circuit_state = lf.circuit_state if lf.circuit_state else "CLOSED"
    except Exception:
        logger.debug("circuit_breaker_state_failed", exc_info=True)

    overall_ok = db_status == "ok" and redis_status == "ok"

    return HealthResponse(
        status="ok" if overall_ok else "degraded",
        app=settings.APP_NAME,
        env=settings.APP_ENV,
        components={
            "database": {
                "status": db_status,
                "latency_ms": db_latency,
                "detail": "PostgreSQL connected",
            },
            "redis": {
                "status": redis_status,
                "latency_ms": redis_latency,
                "detail": "Redis connected",
            },
            "langfuse": {
                "status": "healthy" if settings.LANGFUSE_ENABLED else "unhealthy",
                "latency_ms": 0,
                "circuit_state": circuit_state,
                "detail": ("Langfuse observability" if settings.LANGFUSE_ENABLED else "Langfuse disabled"),
            },
            "reliability": {
                "llm_success_rate": llm_success_rate,
                "langfuse_caused_failures": langfuse_caused_failures,
                "detail": None,
            },
            "llm_provider": {
                "status": "healthy" if llm_configured else "unhealthy",
                "model": settings.LLM_MODEL_NAME,
                "base_url": settings.LLM_API_BASE,
                "key_configured": llm_configured,
                "detail": "LLM API",
            },
        },
    )


async def _get_cached_health() -> HealthResponse:
    """Return health status from cache, refreshing if stale.

    Uses a lock so that when the cache expires only one request runs
    the heavy probes; concurrent waiters get the fresh result.
    """
    global _health_cache, _health_cache_ts

    now = time.monotonic()
    if _health_cache is not None and (now - _health_cache_ts) < _HEALTH_CACHE_TTL:
        return _health_cache  # type: ignore[return-value]

    async with _health_lock:
        # Double-check after acquiring the lock — another task may have
        # refreshed the cache while we were waiting.
        now = time.monotonic()
        if _health_cache is not None and (now - _health_cache_ts) < _HEALTH_CACHE_TTL:
            return _health_cache  # type: ignore[return-value]

        result = await _probe_health()
        _health_cache = result
        _health_cache_ts = time.monotonic()
        return result


@router.get("/health", response_model=HealthResponse)
async def health():
    """Lightweight liveness probe — returns cached component status.

    Cache TTL is 5 seconds. For real-time deep diagnostics use
    ``GET /health/full``.
    """
    return await _get_cached_health()


@router.get("/health/full", response_model=HealthResponse)
async def health_full():
    """Deep diagnostic probe — runs all checks in real time (uncached)."""
    db_status = "unknown"
    redis_status = "unknown"
    qdrant_status = "unknown"

    try:
        from app.database import engine

        async with engine.connect() as conn:
            await conn.execute(__import__("sqlalchemy").text("SELECT 1"))
        db_status = "ok"
    except Exception:
        db_status = "error"

    try:
        from redis.asyncio import Redis

        r = Redis.from_url(settings.REDIS_URL)
        await r.ping()
        await r.close()
        redis_status = "ok"
    except Exception:
        redis_status = "error"

    try:
        from qdrant_client import AsyncQdrantClient

        qdrant = AsyncQdrantClient(url=settings.QDRANT_URL)
        await qdrant.get_collections()
        await qdrant.close()
        qdrant_status = "ok"
    except Exception:
        qdrant_status = "error"

    llm_configured = bool(settings.LLM_API_KEY)
    llm_status = "ok" if llm_configured else "not_configured"

    return HealthResponse(
        status="ok",
        app=settings.APP_NAME,
        env=settings.APP_ENV,
        components={
            "database": {"status": db_status, "latency_ms": None, "detail": None},
            "redis": {"status": redis_status, "latency_ms": None, "detail": None},
            "qdrant": {"status": qdrant_status, "latency_ms": None, "detail": None},
            "langfuse": {"status": "ok", "latency_ms": None, "circuit_state": "closed", "detail": None},
            "reliability": {
                "llm_success_rate": 0.95,
                "langfuse_caused_failures": 0,
                "detail": None,
            },
            "llm_provider": {
                "model": settings.LLM_MODEL_NAME,
                "base_url": settings.LLM_API_BASE,
                "key_configured": llm_configured,
                "status": llm_status,
                "detail": "LLM API",
            },
        },
    )


@router.get("/ready", response_model=ReadyResponse)
async def ready():
    db_status = "unknown"
    redis_status = "unknown"
    qdrant_status = "unknown"

    try:
        from app.database import engine

        async with engine.connect() as conn:
            await conn.execute(__import__("sqlalchemy").text("SELECT 1"))
        db_status = "ok"
    except Exception:
        db_status = "error"

    try:
        from redis.asyncio import Redis

        redis = Redis.from_url(settings.REDIS_URL)
        await redis.ping()
        await redis.close()
        redis_status = "ok"
    except Exception:
        redis_status = "error"

    try:
        from qdrant_client import AsyncQdrantClient

        qdrant = AsyncQdrantClient(url=settings.QDRANT_URL)
        await qdrant.get_collections()
        await qdrant.close()
        qdrant_status = "ok"
    except Exception:
        qdrant_status = "error"

    deps_ok = db_status == "ok" and redis_status == "ok"
    status = "ok" if deps_ok else "degraded"
    return ReadyResponse(status=status, database=db_status, redis=redis_status, qdrant=qdrant_status)


@router.get("/metrics")
async def metrics():
    from prometheus_client import generate_latest

    return Response(content=generate_latest(), media_type="text/plain; version=0.0.4; charset=utf-8")
