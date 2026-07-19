"""
Reliability Monitoring API

Exposes chaos engineering metrics and LLM reliability assertions.
Used to verify Langfuse failure isolation guarantees.
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict

from app.api.deps import get_current_user, require_role
from app.models.user import User
from app.services.chaos_langfuse import get_chaos, toggle_chaos
from app.services.reliability_assertions import get_reliability_monitor

router = APIRouter(tags=["reliability"])


class ChaosToggleRequest(BaseModel):
    enabled: bool


class ReliabilityReportResponse(BaseModel):
    """Reliability report envelope.

    The underlying report is assembled dynamically (monitor metrics plus
    runtime-enriched ``chaos_stats`` / ``langfuse_trace_stats`` sub-dicts that
    may carry an ``{"error": ...}`` branch), so this model documents the known
    fields while permitting extras rather than silently dropping them.
    """

    model_config = ConfigDict(extra="allow")

    status: str | None = None
    llm_total_calls: int | None = None
    llm_successful: int | None = None
    llm_success_rate: float | None = None
    llm_latency_violations: int | None = None
    langfuse_caused_failures: int | None = None
    langfuse_total_failures: int | None = None
    circuit_transitions: int | None = None
    circuit_transition_log: list[dict] | None = None
    chaos_stats: dict | None = None
    langfuse_trace_stats: dict | None = None
    assertion: str | None = None
    target_llm_success_rate: str | None = None
    actual_llm_success_rate: str | None = None


class ChaosToggleResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    status: str


@router.get("/reliability", response_model=ReliabilityReportResponse)
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


@router.post("/reliability/chaos", response_model=ChaosToggleResponse)
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
