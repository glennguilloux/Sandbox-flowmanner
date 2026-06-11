"""SLO definitions and Prometheus compliance gauges (H1.5).

Defines 4 Service Level Objectives with:
- Target compliance percentages
- Prometheus gauges for real-time compliance tracking
- Error budget calculation (burn rate, remaining budget)
- Calculation functions that derive compliance from existing metrics
- Background periodic refresh via asyncio task

SLOs:
1. p99 SSE token latency   < 300ms  (target: 99.9%)
2. Mission success rate    > 95%    (target: 95.0%)
3. Model fallback success  > 99%    (target: 99.0%)
4. Deploy success rate     > 99%    (target: 99.0%)

All SLO calculations read from the canonical metrics in app.core.metrics.
No duplicate metric registrations — single source of truth.
"""

from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass

from prometheus_client import Gauge

logger = logging.getLogger(__name__)

# ── SLO configuration ───────────────────────────────────────────────────────

SLO_REFRESH_INTERVAL_SECONDS = int(os.getenv("SLO_REFRESH_INTERVAL_SECONDS", "60"))

# ── SLO Prometheus gauges (outputs only — inputs are in app.core.metrics) ───

slo_compliance = Gauge(
    "flowmanner_slo_compliance_ratio",
    "Current SLO compliance ratio (0.0–1.0)",
    ["slo_name"],
)

slo_error_budget_remaining = Gauge(
    "flowmanner_slo_error_budget_remaining",
    "Remaining error budget as fraction (0.0–1.0)",
    ["slo_name"],
)

slo_burn_rate = Gauge(
    "flowmanner_slo_burn_rate",
    "Current burn rate multiplier (1.0 = on track, >1 = burning budget)",
    ["slo_name"],
)


# ── SLO data model ──────────────────────────────────────────────────────────


@dataclass
class SLO:
    """Definition of a Service Level Objective."""

    name: str
    description: str
    target: float  # target compliance ratio (e.g. 0.95 = 95%)


# ── SLO definitions ─────────────────────────────────────────────────────────

SLOS: dict[str, SLO] = {
    "sse_token_latency_p99": SLO(
        name="sse_token_latency_p99",
        description="p99 SSE token delivery latency < 300ms",
        target=0.999,  # 99.9% of tokens under 300ms
    ),
    "mission_success_rate": SLO(
        name="mission_success_rate",
        description="Mission execution success rate > 95%",
        target=0.95,
    ),
    "model_fallback_success": SLO(
        name="model_fallback_success",
        description="Model fallback success rate > 99%",
        target=0.99,
    ),
    "deploy_success_rate": SLO(
        name="deploy_success_rate",
        description="Deployment success rate > 99%",
        target=0.99,
    ),
}


# ── Record helpers (delegate to canonical metrics in app.core.metrics) ──────


def record_sse_token_latency(latency_ms: float) -> None:
    """Record an SSE token delivery latency measurement (H1.5)."""
    try:
        from app.core.metrics import record_sse_token_latency as _rec

        _rec(latency_ms / 1000.0)  # convert ms to seconds for Histogram
    except Exception as e:
        logger.debug("slo_record_sse_latency_failed error=%s", str(e))


def record_model_fallback(success: bool, provider: str = "unknown") -> None:
    """Record a model fallback attempt (H1.5)."""
    try:
        from app.core.metrics import record_model_fallback as _rec

        _rec(provider=provider, success=success)
    except Exception as e:
        logger.debug("slo_record_fallback_failed error=%s", str(e))


def record_deploy(success: bool) -> None:
    """Record a deployment attempt (H1.5).

    Note: This needs to be called from deploy scripts / CI/CD.
    Until wired, the deploy SLO will show 100% from zero data.
    """
    try:
        from app.core.metrics import deploy_success_total, deploy_total

        # These are Gauge-type counters incremented manually
        deploy_total.inc()
        if success:
            deploy_success_total.inc()
    except Exception as e:
        logger.debug("slo_record_deploy_failed error=%s", str(e))


# ── SLO calculation helpers ─────────────────────────────────────────────────


def _read_histogram_p99(histogram) -> float:
    """Approximate p99 from a Prometheus Histogram's bucket samples.

    Uses linear interpolation between the two buckets that bracket the 99th
    percentile. This is an approximation; exact quantiles require server-side
    PromQL `histogram_quantile(0.99, ...)`.
    """
    try:
        samples = list(histogram.collect())
        if not samples:
            return 0.0
        metric = samples[0]

        # Collect bucket boundaries and cumulative counts
        buckets = []
        total_count = 0
        for s in metric.samples:
            if s.name.endswith("_bucket") and s.labels.get("le") != "+Inf":
                le = float(s.labels["le"])
                buckets.append((le, s.value))
                total_count = max(total_count, s.value)
            elif s.name.endswith("_count"):
                total_count = max(total_count, s.value)

        if total_count == 0:
            return 0.0

        buckets.sort(key=lambda x: x[0])
        target = total_count * 0.99

        for i, (le, count) in enumerate(buckets):
            if count >= target:
                if i == 0:
                    return le
                prev_le, prev_count = buckets[i - 1]
                if count == prev_count:
                    return le
                fraction = (target - prev_count) / (count - prev_count)
                return prev_le + fraction * (le - prev_le)

        # Fallback: return the largest bucket
        return buckets[-1][0] if buckets else 0.0
    except Exception as e:
        logger.debug("Failed to compute p99 from histogram: %s", e)
        return 0.0


def _read_counter_total(counter, label_filter: dict | None = None) -> float:
    """Read the current total from a Prometheus Counter.

    Optionally filter by label values.
    """
    try:
        for sample in counter.collect():
            for s in sample.samples:
                if s.name.endswith("_total"):
                    if label_filter:
                        match = all(s.labels.get(k) == v for k, v in label_filter.items())
                        if not match:
                            continue
                    return s.value
    except Exception as e:
        logger.debug("slo_read_counter_failed error=%s", str(e))
    return 0.0


def _read_gauge_value(gauge: Gauge) -> float:
    """Safely read the current value of a Prometheus gauge."""
    try:
        for sample in gauge.collect():
            for s in sample.samples:
                if s.name == gauge._name:
                    return s.value
    except Exception as e:
        logger.debug("slo_read_gauge_failed error=%s", str(e))
    return 0.0


def _compute_compliance_ratio(slo: SLO) -> float:
    """Derive current compliance ratio from Prometheus metrics.

    Each SLO reads from the canonical metrics in app.core.metrics:
    - sse_token_latency_p99: reads histogram buckets from sse_token_latency
    - mission_success_rate: reads labeled counter mission_total
    - model_fallback_success: reads labeled counters model_fallback_total/_success
    - deploy_success_rate: reads gauges deploy_total/deploy_success_total
    """
    from app.core import metrics as m

    if slo.name == "sse_token_latency_p99":
        p99_seconds = _read_histogram_p99(m.sse_token_latency)
        if p99_seconds == 0.0:
            return 1.0  # no data = assume compliant
        p99_ms = p99_seconds * 1000.0
        if p99_ms <= 300.0:
            return 1.0
        # Linear degradation: 300ms target, 600ms = 0.5 compliance
        return max(0.0, 300.0 / p99_ms)

    elif slo.name == "mission_success_rate":
        good = _read_counter_total(m.mission_total, {"status": "success"})
        bad = _read_counter_total(m.mission_total, {"status": "failure"})
        total = good + bad
        return good / total if total > 0 else 1.0

    elif slo.name == "model_fallback_success":
        total = _read_counter_total(m.model_fallback_total)
        success = _read_counter_total(m.model_fallback_success)
        return success / total if total > 0 else 1.0

    elif slo.name == "deploy_success_rate":
        total = _read_gauge_value(m.deploy_total)
        success = _read_gauge_value(m.deploy_success_total)
        return success / total if total > 0 else 1.0

    return 1.0


def _compute_burn_rate(compliance: float, slo: SLO) -> float:
    """Compute the error budget burn rate.

    Burn rate = (1 - compliance) / (1 - target)

    - 1.0 = on track (consuming budget at planned rate)
    - > 1.0 = burning budget faster than allowed
    - < 1.0 = ahead of plan
    """
    error_rate = max(0.0, 1.0 - compliance)
    error_budget = max(0.001, 1.0 - slo.target)  # avoid div by zero
    return error_rate / error_budget


def _compute_error_budget_remaining(compliance: float, slo: SLO) -> float:
    """Compute remaining error budget as a fraction.

    1.0 = full budget intact
    0.0 = budget exhausted
    < 0.0 = budget blown
    """
    error_budget = 1.0 - slo.target
    if error_budget <= 0:
        return 0.0
    error_spent = max(0.0, 1.0 - compliance)
    remaining = 1.0 - (error_spent / error_budget)
    return max(0.0, min(1.0, remaining))


def refresh_slo_metrics() -> dict:
    """Refresh all SLO Prometheus gauges and return a status summary."""
    results = {}
    for slo_name, slo in SLOS.items():
        compliance = _compute_compliance_ratio(slo)
        burn_rate = _compute_burn_rate(compliance, slo)
        budget = _compute_error_budget_remaining(compliance, slo)

        slo_compliance.labels(slo_name=slo_name).set(compliance)
        slo_burn_rate.labels(slo_name=slo_name).set(burn_rate)
        slo_error_budget_remaining.labels(slo_name=slo_name).set(budget)

        results[slo_name] = {
            "description": slo.description,
            "target": slo.target,
            "compliance": round(compliance, 4),
            "burn_rate": round(burn_rate, 2),
            "error_budget_remaining": round(budget, 4),
            "status": "healthy" if compliance >= slo.target else "at_risk",
        }

    return results


def get_slo_status() -> dict:
    """Return current SLO status from Prometheus gauges (fast, no recalculation)."""
    status = {}
    for slo_name, slo in SLOS.items():
        try:
            compliance = _read_gauge_value(slo_compliance.labels(slo_name=slo_name))
            burn_rate = _read_gauge_value(slo_burn_rate.labels(slo_name=slo_name))
            budget = _read_gauge_value(slo_error_budget_remaining.labels(slo_name=slo_name))
        except Exception:
            compliance = 1.0
            burn_rate = 0.0
            budget = 1.0

        status[slo_name] = {
            "description": slo.description,
            "target": slo.target,
            "compliance": round(compliance, 4),
            "burn_rate": round(burn_rate, 2),
            "error_budget_remaining": round(budget, 4),
            "status": "healthy" if compliance >= slo.target else "at_risk",
        }
    return status


def get_overall_health() -> dict:
    """Return an overall health score based on SLO compliance."""
    slo_status = get_slo_status()
    healthy_count = sum(1 for s in slo_status.values() if s["status"] == "healthy")
    total = len(slo_status)

    return {
        "healthy_slos": healthy_count,
        "total_slos": total,
        "health_score": round(healthy_count / max(total, 1), 2),
        "status": (
            "healthy" if healthy_count == total else ("degraded" if healthy_count >= total / 2 else "unhealthy")
        ),
        "slos": slo_status,
    }


# ── Periodic background refresh ─────────────────────────────────────────────

_refresh_task: asyncio.Task | None = None


async def _periodic_slo_refresh(interval_seconds: int = SLO_REFRESH_INTERVAL_SECONDS):
    """Background task that periodically refreshes SLO metrics."""
    logger.info(
        "SLO periodic refresh started (interval=%ds)",
        interval_seconds,
    )
    while True:
        try:
            await asyncio.sleep(interval_seconds)
            results = refresh_slo_metrics()
            at_risk = [k for k, v in results.items() if v["status"] == "at_risk"]
            if at_risk:
                logger.warning("SLOs at risk: %s", at_risk)
                # Trigger SLO alerts for at-risk SLOs
                try:
                    from app.services.alerting import send_slo_alert

                    for slo_name in at_risk:
                        r = results[slo_name]
                        await send_slo_alert(
                            slo_name=slo_name,
                            description=r["description"],
                            compliance=r["compliance"],
                            burn_rate=r["burn_rate"],
                            error_budget_remaining=r["error_budget_remaining"],
                            target=r["target"],
                        )
                except Exception as e:
                    logger.debug("SLO alert dispatch failed: %s", e)
        except asyncio.CancelledError:
            logger.info("SLO periodic refresh stopped")
            break
        except Exception as e:
            logger.error("SLO periodic refresh error: %s", e)


def start_slo_refresh() -> None:
    """Start the background SLO metric refresh task.

    Called once at application startup. Idempotent.
    """
    global _refresh_task
    if _refresh_task is not None and not _refresh_task.done():
        return

    _refresh_task = asyncio.ensure_future(_periodic_slo_refresh(SLO_REFRESH_INTERVAL_SECONDS))
    logger.info("SLO background refresh task created")


def stop_slo_refresh() -> None:
    """Stop the background SLO metric refresh task."""
    global _refresh_task
    if _refresh_task and not _refresh_task.done():
        _refresh_task.cancel()
        _refresh_task = None
