"""
Reliability Monitoring API

Exposes chaos engineering metrics and LLM reliability assertions.
Used to verify Langfuse failure isolation guarantees.
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.api.deps import get_current_user, require_role
from app.models.user import User
from app.services.chaos_langfuse import get_chaos, toggle_chaos
from app.services.reliability_assertions import get_reliability_monitor

router = APIRouter(tags=["reliability"])


class ChaosToggleRequest(BaseModel):
    enabled: bool


@router.get("/reliability")
async def get_reliability_report(
    user: User = Depends(get_current_user),
):
    """
    Get the reliability report showing LLM health during chaos testing.

    Key metrics:
    - LLM success rate while Langfuse is failing (target: ~100%)
    - Latency violations
    - Circuit breaker transitions
    - Chaos injection statistics
    """
    monitor = get_reliability_monitor()
    report = monitor.get_reliability_report()

    # Enrich with chaos stats
    try:
        chaos = get_chaos()
        report["chaos_stats"] = chaos.get_stats()
    except Exception as e:
        report["chaos_stats"] = {"error": str(e)}

    # Enrich with Langfuse trace stats
    try:
        from app.services.langfuse_service import get_langfuse_service

        langfuse = get_langfuse_service()
        report["langfuse_trace_stats"] = langfuse.get_trace_stats()
    except Exception as e:
        report["langfuse_trace_stats"] = {"error": str(e)}

    return report


@router.post("/reliability/chaos")
async def toggle_chaos_mode(
    request: ChaosToggleRequest,
    user: User = Depends(require_role("admin")),
):
    """
    Toggle chaos mode at runtime without container restart.

    When enabled, randomly injects failures into Langfuse SDK calls
    to verify LLM responses remain unaffected.
    """
    result = toggle_chaos(request.enabled)
    return {"status": "ok", **result}
