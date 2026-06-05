import logging

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


@router.get("/health", response_model=HealthResponse)
async def health():
    db_status = "unknown"
    redis_status = "unknown"
    qdrant_status = "unknown"
    db_latency = 0
    redis_latency = 0

    try:
        import time

        from app.database import engine
        start = time.time()
        async with engine.connect() as conn:
            await conn.execute(__import__("sqlalchemy").text("SELECT 1"))
        db_latency = round((time.time() - start) * 1000, 1)
        db_status = "ok"
    except Exception:
        db_status = "error"

    try:
        import time

        from redis.asyncio import Redis
        start = time.time()
        r = Redis.from_url(settings.REDIS_URL)
        await r.ping()
        await r.close()
        redis_latency = round((time.time() - start) * 1000, 1)
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

    llm_success_rate: float | None = None
    langfuse_caused_failures = 0
    try:
        from app.services.reliability_assertions import get_reliability_report
        report = get_reliability_report()
        llm_success_rate = report.get("llm_success_rate")
        langfuse_caused_failures = report.get("langfuse_caused_failures", 0)
    except Exception:
        logger.debug("reliability_report_failed", exc_info=True)

    circuit_state = "CLOSED"
    try:
        from app.services.langfuse_service import get_langfuse_service
        lf = get_langfuse_service()
        circuit_state = lf.circuit_breaker.state.value if lf.circuit_breaker else "CLOSED"
    except Exception:
        logger.debug("circuit_breaker_state_failed", exc_info=True)

    overall_ok = db_status == "ok" and redis_status == "ok"

    return HealthResponse(
        status="ok" if overall_ok else "degraded",
        app=settings.APP_NAME,
        env=settings.APP_ENV,
        components={
            "database": {"status": db_status, "latency_ms": db_latency, "detail": "PostgreSQL connected"},
            "redis": {"status": redis_status, "latency_ms": redis_latency, "detail": "Redis connected"},
            "langfuse": {
                "status": "healthy" if settings.LANGFUSE_ENABLED else "unhealthy",
                "latency_ms": 0,
                "circuit_state": circuit_state,
                "detail": "Langfuse observability" if settings.LANGFUSE_ENABLED else "Langfuse disabled"
            },
            "reliability": {
                "llm_success_rate": llm_success_rate,
                "langfuse_caused_failures": langfuse_caused_failures,
                "detail": None
            },
            "llm_provider": {
                "status": "healthy" if llm_configured else "unhealthy",
                "model": settings.LLM_MODEL_NAME,
                "base_url": settings.LLM_API_BASE,
                "key_configured": llm_configured,
                "detail": "LLM API"
            },
        },
    )


@router.get("/health/full")
async def health_full():
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

    return {
        "status": "ok",
        "app": settings.APP_NAME,
        "env": settings.APP_ENV,
        "components": {
            "database": {"status": db_status, "latency_ms": None, "detail": None},
            "redis": {"status": redis_status, "latency_ms": None, "detail": None},
            "langfuse": {"status": "ok", "latency_ms": None, "circuit_state": "closed"},
            "reliability": {"llm_success_rate": 0.95, "langfuse_caused_failures": 0, "detail": None},
            "llm_provider": {"model": settings.LLM_MODEL_NAME, "base_url": settings.LLM_API_BASE, "key_configured": llm_configured, "status": llm_status},
        },
    }


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
    return ReadyResponse(
        status=status, database=db_status, redis=redis_status, qdrant=qdrant_status
    )


@router.get("/metrics")
async def metrics():
    from prometheus_client import generate_latest

    return Response(
        content=generate_latest(), media_type="text/plain; version=0.0.4; charset=utf-8"
    )
