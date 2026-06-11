"""Observability API — circuit breaker states, metrics summary, alerting status."""

from fastapi import APIRouter, Request
from pydantic import BaseModel

from app.api.envelope import envelope as _envelope

router = APIRouter(tags=["observability"])


class AuthLoopAlert(BaseModel):
    redirectCount: int
    windowMs: int
    threshold: int
    pathname: str
    sessionError: str
    hasUser: bool


@router.get("/observability/status")
async def observability_status():
    """Return circuit breaker states, dependency health, and alerting config."""
    from app.core.circuit_breaker import get_all_breakers
    from app.services.alerting import get_alerting_status

    breakers = get_all_breakers()
    circuit_states = {}
    for name, breaker in breakers.items():
        status = breaker.get_status()
        circuit_states[name] = status

    return _envelope(
        {
            "circuit_breakers": circuit_states,
            "alerting": get_alerting_status(),
        }
    )


@router.post("/observability/auth-loop-alert")
async def auth_loop_alert(alert: AuthLoopAlert, request: Request):
    """Receive auth redirect loop alerts from the frontend middleware.

    Increments the Prometheus counter and logs via Sentry.
    """
    import logging

    logger = logging.getLogger("flowmanner.auth")

    logger.error(
        "Auth redirect loop detected by middleware: %d redirects in %ds "
        "(threshold=%d) — blocked at %s (session_error=%s, has_user=%s)",
        alert.redirectCount,
        alert.windowMs / 1000,
        alert.threshold,
        alert.pathname,
        alert.sessionError,
        alert.hasUser,
        extra={
            "redirect_count": alert.redirectCount,
            "window_ms": alert.windowMs,
            "threshold": alert.threshold,
            "pathname": alert.pathname,
            "session_error": alert.sessionError,
            "has_user": alert.hasUser,
        },
    )

    # Increment Prometheus counter
    try:
        from app.core.metrics import record_auth_redirect_loop

        record_auth_redirect_loop(source="middleware")
    except Exception:
        logger.debug("auth_loop_metric_failed", exc_info=True)

    return _envelope({"received": True})


@router.get("/observability/metrics-summary")
async def metrics_summary():
    """Return a human-readable summary of key metrics (not Prometheus format)."""
    from prometheus_client import generate_latest

    # Parse the Prometheus text format to extract key metrics
    raw = generate_latest().decode("utf-8")
    lines = raw.strip().split("\n")

    summary = {
        "llm": {"requests": {}, "tokens": {}},
        "missions": {},
        "cache": {"hits": 0, "misses": 0},
        "circuit_breakers": {},
    }

    for line in lines:
        if line.startswith("#"):
            continue
        try:
            parts = line.rsplit(" ", 1)
            if len(parts) != 2:
                continue
            metric_name = parts[0].split("{")[0]
            value = float(parts[1])

            if metric_name == "flowmanner_llm_requests_total":
                label_str = line.split("{")[1].split("}")[0] if "{" in line else ""
                provider = ""
                status = ""
                for label in label_str.split(","):
                    k, v = label.split("=")
                    v = v.strip('"')
                    if k == "provider":
                        provider = v
                    elif k == "status":
                        status = v
                key = f"{provider}_{status}"
                summary["llm"]["requests"][key] = value

            elif metric_name == "flowmanner_missions_total":
                label_str = line.split("{")[1].split("}")[0] if "{" in line else ""
                status = ""
                for label in label_str.split(","):
                    k, v = label.split("=")
                    if k == "status":
                        status = v.strip('"')
                summary["missions"][status] = value

            elif metric_name == "flowmanner_cache_hits_total":
                summary["cache"]["hits"] += value

            elif metric_name == "flowmanner_cache_misses_total":
                summary["cache"]["misses"] += value

            elif metric_name == "circuit_breaker_state":
                dep = line.split('dependency="')[1].split('"')[0]
                state_val = int(value)
                state_name = {0: "closed", 1: "open", 2: "half_open"}.get(state_val, "unknown")
                summary["circuit_breakers"][dep] = state_name

        except (ValueError, IndexError):
            continue

    return summary


@router.get("/observability/slos")
async def slo_status():
    """Return current SLO compliance status (H1.5).

    Provides compliance ratios, burn rates, and error budget
    for all 4 SLOs: SSE latency, mission success, model fallback,
    and deploy success.
    """
    from app.core.slo import refresh_slo_metrics

    # Force a refresh to get current compliance values
    results = refresh_slo_metrics()
    return _envelope(results)


@router.get("/observability/health")
async def health_check():
    """Return overall system health based on SLO compliance (H1.5).

    Includes:
    - SLO compliance overview
    - Circuit breaker states
    - Alerting status
    - Langfuse trace stats
    """
    from app.core.circuit_breaker import get_all_breakers
    from app.core.slo import get_overall_health, refresh_slo_metrics
    from app.services.alerting import get_alerting_status

    # Refresh SLO metrics and get health
    refresh_slo_metrics()
    health = get_overall_health()

    # Circuit breaker states
    try:
        breakers = get_all_breakers()
        circuit_states = {name: breaker.get_status() for name, breaker in breakers.items()}
        health["circuit_breakers"] = circuit_states
    except Exception:
        health["circuit_breakers"] = {}

    # Langfuse trace stats
    try:
        from app.services.langfuse_service import get_langfuse_service

        lf = get_langfuse_service()
        health["langfuse"] = lf.get_trace_stats()
    except Exception:
        health["langfuse"] = {"error": "unavailable"}

    # Alerting status
    health["alerting"] = get_alerting_status()

    return _envelope(health)


@router.get("/observability/dashboard")
async def slo_dashboard():
    """Return the SLO dashboard configuration (H1.5).

    Can be imported into Langfuse or Grafana for SLO visualization.
    """
    from app.core.slo_dashboard import get_slo_dashboard_config

    return _envelope(get_slo_dashboard_config())
