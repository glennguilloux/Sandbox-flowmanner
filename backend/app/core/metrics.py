"""Business metrics for Prometheus export.

Provides counters, histograms, and gauges for:
- Mission execution (success/fail, duration)
- LLM requests (latency, token usage, provider)
- Cache operations (hits, misses)
- Active requests
- Circuit breaker states (delegated to circuit_breaker module)
"""

from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram

# ─── Mission Metrics ────────────────────────────────────────────────────────

mission_total = Counter(
    "flowmanner_missions_total",
    "Total missions executed",
    ["status"],  # success, failure
)

mission_duration = Histogram(
    "flowmanner_mission_duration_seconds",
    "Mission execution duration",
    buckets=[0.5, 1, 2, 5, 10, 30, 60, 120, 300, 600],
)

mission_tokens = Histogram(
    "flowmanner_mission_tokens",
    "Tokens consumed per mission",
    buckets=[10, 50, 100, 500, 1000, 5000, 10000, 50000],
)

# ─── LLM Metrics ────────────────────────────────────────────────────────────

llm_request_total = Counter(
    "flowmanner_llm_requests_total",
    "Total LLM API requests",
    ["provider", "status"],  # provider: deepseek, llamacpp; status: success, failure
)

llm_request_duration = Histogram(
    "flowmanner_llm_request_duration_seconds",
    "LLM request latency",
    ["provider"],
    buckets=[0.1, 0.25, 0.5, 1, 2, 5, 10, 30, 60],
)

llm_tokens_used = Counter(
    "flowmanner_llm_tokens_total",
    "Total LLM tokens consumed",
    ["provider", "type"],  # values: prompt, completion
)

llm_active_requests = Gauge(
    "flowmanner_llm_active_requests",
    "Currently in-flight LLM requests",
    ["provider"],
)

# ─── Cache Metrics ──────────────────────────────────────────────────────────

cache_hits = Counter(
    "flowmanner_cache_hits_total",
    "Cache hit count",
    ["cache"],  # cache name: response, session, etc.
)

cache_misses = Counter(
    "flowmanner_cache_misses_total",
    "Cache miss count",
    ["cache"],
)

cache_size = Gauge(
    "flowmanner_cache_size",
    "Current cache entry count",
    ["cache"],
)

# ─── HTTP Metrics (extended from middleware) ─────────────────────────────────

active_requests = Gauge(
    "flowmanner_active_requests",
    "Currently active HTTP requests",
)

# ─── Dependency Health ──────────────────────────────────────────────────────

dependency_healthy = Gauge(
    "flowmanner_dependency_healthy",
    "Dependency health status (1=healthy, 0=unhealthy)",
    ["dependency"],
)

# ─── Evaluation Metrics ────────────────────────────────────────────────────

eval_runs_total = Counter(
    "flowmanner_eval_runs_total",
    "Total evaluation runs executed",
    ["model", "status"],  # status: completed, failed
)

eval_score = Histogram(
    "flowmanner_eval_score",
    "Aggregate evaluation score distribution",
    ["model", "category"],  # category: code, rag, agent, creative
    buckets=[1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0],
)

eval_duration_seconds = Histogram(
    "flowmanner_eval_duration_seconds",
    "Evaluation run duration",
    buckets=[5, 10, 30, 60, 120, 300, 600],
)

eval_test_cases_total = Counter(
    "flowmanner_eval_test_cases_total",
    "Total test cases evaluated",
    ["model", "task_type", "result"],  # result: pass, fail
)

# ─── Deploy Tracking (H1.5) ─────────────────────────────────────────────────

deploy_total = Gauge(
    "flowmanner_deploy_total",
    "Total deployment attempts",
)

deploy_success_total = Gauge(
    "flowmanner_deploy_success_total",
    "Successful deployment attempts",
)

# ─── Dual-Write Metrics ────────────────────────────────────────────────────

dual_write_failures_total = Counter(
    "flowmanner_dual_write_failures_total",
    "Dual-write failures after all retry attempts exhausted",
    ["site"],  # site: create_blueprint, sync_run_status, sync_blueprint, soft_delete_blueprint
)

# ─── Helpers ────────────────────────────────────────────────────────────────


# --- Auth Redirect Loop Detection -------------------------------------------

auth_redirect_loops_total = Counter(
    "flowmanner_auth_redirect_loops_total",
    "Auth redirect loops detected (rapid signin/dashboard redirects)",
    ["source"],
)

# --- SSE Token Latency (H1.5) ------------------------------------------------

sse_token_latency = Histogram(
    "flowmanner_sse_token_latency_seconds",
    "SSE token delivery latency in seconds",
    buckets=[0.01, 0.05, 0.1, 0.2, 0.3, 0.5, 1, 2, 5],
)

# --- Model Fallback Tracking (H1.5) ------------------------------------------

model_fallback_total = Counter(
    "flowmanner_model_fallback_total",
    "Total model fallback attempts",
    ["provider"],
)

model_fallback_success = Counter(
    "flowmanner_model_fallback_success_total",
    "Successful model fallback attempts",
    ["provider"],
)


def record_auth_redirect_loop(source: str = "middleware") -> None:
    auth_redirect_loops_total.labels(source=source).inc()


def record_sse_token_latency(seconds: float) -> None:
    """Record an SSE token delivery latency measurement (H1.5)."""
    sse_token_latency.observe(seconds)


def record_model_fallback(success: bool, provider: str = "unknown") -> None:
    """Record a model fallback attempt (H1.5)."""
    model_fallback_total.labels(provider=provider).inc()
    if success:
        model_fallback_success.labels(provider=provider).inc()


def record_mission_success(duration_seconds: float, tokens: int = 0) -> None:
    mission_total.labels(status="success").inc()
    mission_duration.observe(duration_seconds)
    if tokens > 0:
        mission_tokens.observe(tokens)


def record_mission_failure(duration_seconds: float) -> None:
    mission_total.labels(status="failure").inc()
    mission_duration.observe(duration_seconds)


def record_llm_request(
    provider: str,
    duration_seconds: float,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    success: bool = True,
) -> None:
    status = "success" if success else "failure"
    llm_request_total.labels(provider=provider, status=status).inc()
    llm_request_duration.labels(provider=provider).observe(duration_seconds)
    if prompt_tokens > 0:
        llm_tokens_used.labels(provider=provider, type="prompt").inc(prompt_tokens)
    if completion_tokens > 0:
        llm_tokens_used.labels(provider=provider, type="completion").inc(completion_tokens)


def record_cache_hit(cache_name: str = "default") -> None:
    cache_hits.labels(cache=cache_name).inc()


def record_cache_miss(cache_name: str = "default") -> None:
    cache_misses.labels(cache=cache_name).inc()


def record_eval_run(
    model: str,
    duration_seconds: float,
    aggregate_score: float,
    category_scores: dict[str, float] | None = None,
    status: str = "completed",
) -> None:
    """Record metrics for an evaluation run."""
    eval_runs_total.labels(model=model, status=status).inc()
    eval_duration_seconds.observe(duration_seconds)
    if aggregate_score > 0:
        eval_score.labels(model=model, category="overall").observe(aggregate_score)
    if category_scores:
        for cat, score in category_scores.items():
            eval_score.labels(model=model, category=cat).observe(score)


def record_eval_test_case(model: str, task_type: str, passed: bool) -> None:
    """Record a single test case result."""
    result = "pass" if passed else "fail"
    eval_test_cases_total.labels(model=model, task_type=task_type, result=result).inc()
