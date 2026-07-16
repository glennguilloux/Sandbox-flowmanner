"""Plan generator — produces K plan candidates using different strategies.

Three strategies:
- **heuristic**: Rule-based minimal plan from the user's prompt (no LLM).
- **llm_persona_a**: LLM with "concise engineer" persona.
- **llm_persona_b**: LLM with "thorough strategist" persona.

All LLM calls go through the same ModelRouter / httpx fallback path as
the existing ``MissionPlanner._generate_plan`` method.  Each generator
returns one ``PlanCandidate``.
"""

from __future__ import annotations

import json
import logging
import re
import time
from typing import Any

import httpx

from app.config import settings

from .plan_candidate import PlanCandidate
from .plan_scorer import (
    detect_risk_flags,
    estimate_latency_ms,
    estimate_tokens_for_tasks,
    score_plan,
)

logger = logging.getLogger(__name__)

# ── Persona system prompts ───────────────────────────────────────────────────

_PERSONA_A_SYSTEM = (
    "You are a concise engineer. Break down the mission into the fewest "
    "tasks needed. Prefer simple, direct steps. Avoid redundancy. "
    "Each task should be actionable and self-contained."
)

_PERSONA_B_SYSTEM = (
    "You are a thorough strategist. Break down the mission into detailed "
    "tasks with explicit dependencies, fallback strategies, and risk "
    "mitigation. Prefer resilience over speed. Include review steps."
)

# ── Virtual cost proxy for local models ─────────────────────────────────────
# When all models are local (free), this rate is used as a deterministic
# ranking signal so the scorer can differentiate candidates by resource
# intensity.  It is NOT a real dollar amount.
_LOCAL_MODEL_PROXY_RATE_PER_MILLION = 0.01

# ── Heuristic plan builder ───────────────────────────────────────────────────


def _build_heuristic_plan(
    title: str,
    description: str,
    mission_type: str | None,
) -> list[dict]:
    """Build a minimal linear plan from the mission prompt.

    Uses simple keyword heuristics — no LLM call.  Returns 1–4 tasks
    depending on the mission description complexity.

    This is intentionally simple: the heuristic strategy is the "cheap
    baseline" that the LLM personas should beat on quality.
    """
    tasks: list[dict] = []
    desc_lower = (description or "").lower()

    # Always start with an analysis/research step
    tasks.append(
        {
            "title": "Analyze requirements",
            "description": f"Review and analyze: {description[:200]}",
            "task_type": "llm",
            "dependencies": [],
        }
    )

    # If description mentions code/implementation, add a coding step
    if any(kw in desc_lower for kw in ("build", "create", "implement", "code", "develop", "write")):
        tasks.append(
            {
                "title": "Implement solution",
                "description": f"Implement the core solution for: {title}",
                "task_type": "code",
                "dependencies": [0],
            }
        )

    # If description mentions research/search/analyze, add a tool step
    if any(kw in desc_lower for kw in ("research", "search", "find", "investigate", "compare")):
        tasks.append(
            {
                "title": "Research and gather information",
                "description": f"Search and gather relevant information for: {title}",
                "task_type": "tool",
                "dependencies": [0],
                "fallback": "proceed_with_cached_data",
            }
        )

    # Always end with a review/summary step
    last_idx = len(tasks) - 1
    tasks.append(
        {
            "title": "Review and summarize",
            "description": f"Review the results and produce a summary for: {title}",
            "task_type": "review",
            "dependencies": [last_idx],
        }
    )

    return tasks


# ── LLM plan generation (shared) ─────────────────────────────────────────────


async def _generate_plan_via_llm(
    prompt: str,
    system_prompt: str,
    *,
    get_model_router=None,
    cost_tracker=None,
    db=None,
    user_id: int | None = None,
    mission_id: str | None = None,
    temperature: float = 0.7,
) -> tuple[list[dict], float, int, int]:
    """Generate a plan via LLM with a specific system prompt.

    Returns (tasks, latency_seconds, prompt_tokens, completion_tokens).
    """
    start_time = time.monotonic()
    model_id = "unknown"
    provider = "unknown"
    prompt_tokens = 0
    completion_tokens = 0
    content = ""

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": prompt},
    ]

    try:
        model_router = get_model_router() if get_model_router else None
        if model_router:
            response = await model_router.route_request(
                messages=messages,
                user_id=str(user_id) if user_id else "system",
                db_session=db,
                is_admin=True,
                temperature=temperature,
                max_tokens=settings.MISSION_PLAN_MAX_TOKENS,
            )
            model_id = response.get("model", "deepseek-v4-flash")
            provider = response.get("provider", "unknown")
            cost_info = response.get("cost", {})
            prompt_tokens = cost_info.get("input_tokens", 0)
            completion_tokens = cost_info.get("output_tokens", 0)

            if not response.get("success"):
                logger.warning("LLM plan generation failed: %s", response.get("error"))
                return [], time.monotonic() - start_time, 0, 0

            content = response.get("content", "") if isinstance(response, dict) else str(response)
        else:
            llm_url = getattr(settings, "LLM_BASE_URL", "http://localhost:11434")
            llm_key = getattr(settings, "LLM_API_KEY", "")
            llm_model = getattr(settings, "LLM_DEFAULT_MODEL", "qwen3:14b")
            model_id = llm_model
            provider = "llamacpp"

            headers = {"Content-Type": "application/json"}
            if llm_key:
                headers["Authorization"] = f"Bearer {llm_key}"

            async with httpx.AsyncClient(timeout=settings.MISSION_LLM_REQUEST_TIMEOUT) as client:
                resp = await client.post(
                    f"{llm_url}/v1/chat/completions",
                    headers=headers,
                    json={
                        "model": llm_model,
                        "messages": messages,
                        "temperature": temperature,
                        "max_tokens": settings.MISSION_PLAN_MAX_TOKENS,
                    },
                )
                data = resp.json()
                content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                prompt_tokens = data.get("usage", {}).get("prompt_tokens", 0)
                completion_tokens = data.get("usage", {}).get("completion_tokens", 0)

        # Extract JSON array from response
        content = content.strip()
        json_match = re.search(r"\[.*\]", content, re.DOTALL)
        if json_match:
            tasks = json.loads(json_match.group())
            if isinstance(tasks, list) and len(tasks) > 0:
                return tasks, time.monotonic() - start_time, prompt_tokens, completion_tokens

        logger.warning("Could not parse plan from LLM response: %s", content[:200])
        return [], time.monotonic() - start_time, prompt_tokens, completion_tokens

    except Exception as e:
        logger.error("LLM plan generation error: %s", e)
        return [], time.monotonic() - start_time, prompt_tokens, completion_tokens


# ── Public API ───────────────────────────────────────────────────────────────


async def generate_plan_candidates(
    mission,
    *,
    k: int = 3,
    get_model_router=None,
    cost_tracker=None,
    db=None,
) -> list[PlanCandidate]:
    """Generate K plan candidates using different strategies.

    Strategies:
    - ``heuristic_v1``: Rule-based minimal plan (no LLM).
    - ``llm_persona_a``: LLM with "concise engineer" persona.
    - ``llm_persona_b``: LLM with "thorough strategist" persona.

    Each candidate gets deterministic cost/latency/token estimates and
    a heuristic quality score.

    Args:
        mission: Mission model with ``.title``, ``.description``,
            ``.mission_type``, ``.constraints``, ``.user_id``, ``.id``.
        k: Number of candidates to generate (default 3).
        get_model_router: Late-binding callable returning a ModelRouter.
        cost_tracker: CostTracker instance for pricing.
        db: SQLAlchemy session for LLM calls.

    Returns:
        List of up to K ``PlanCandidate`` instances.
    """
    # Late import to avoid circular dependency (MissionPlanner imports plan_selection)
    from app.services.mission_planner import MissionPlanner

    candidates: list[PlanCandidate] = []

    # Build the base prompt (same as MissionPlanner._build_plan_prompt)
    planner = MissionPlanner()
    base_prompt = planner._build_plan_prompt(mission)

    # ── Strategy 1: Heuristic (always first, no LLM) ─────────────────────
    heuristic_tasks = _build_heuristic_plan(
        title=mission.title or "Untitled",
        description=mission.description or "",
        mission_type=mission.mission_type,
    )
    heuristic_candidate = _finalize_candidate(
        plan_id="heuristic_v1",
        generation_strategy="heuristic",
        tasks=heuristic_tasks,
        rationale="Rule-based minimal plan with no LLM calls. Fastest to generate, lowest cost, but may miss nuance.",
    )
    candidates.append(heuristic_candidate)

    # ── Strategy 2: LLM Persona A (concise engineer) ─────────────────────
    if k >= 2:
        llm_tasks_a, latency_a, prompt_tok_a, comp_tok_a = await _generate_plan_via_llm(
            base_prompt,
            _PERSONA_A_SYSTEM,
            get_model_router=get_model_router,
            cost_tracker=cost_tracker,
            db=db,
            user_id=mission.user_id,
            mission_id=str(mission.id),
            temperature=0.5,  # lower temp for concise output
        )
        if not llm_tasks_a:
            # Fallback: use heuristic if LLM fails — mark degraded so the
            # planner routes this candidate to human review (never auto-ship).
            llm_tasks_a = heuristic_tasks
            persona_a = _finalize_candidate(
                plan_id="llm_persona_a",
                generation_strategy=PlanCandidate.FALLBACK,
                tasks=llm_tasks_a,
                rationale="LLM persona A failed; substituted heuristic plan. DEGRADED — requires human review.",
                latency_override_ms=int(latency_a * 1000),
                token_override=prompt_tok_a + comp_tok_a,
                degraded=True,
            )
        else:
            persona_a = _finalize_candidate(
                plan_id="llm_persona_a",
                generation_strategy="llm_persona",
                tasks=llm_tasks_a,
                rationale="LLM persona: concise engineer. Prefers minimal, "
                "direct steps. Lower temperature for deterministic output.",
                latency_override_ms=int(latency_a * 1000),
                token_override=prompt_tok_a + comp_tok_a,
            )
        candidates.append(persona_a)

    # ── Strategy 3: LLM Persona B (thorough strategist) ──────────────────
    if k >= 3:
        llm_tasks_b, latency_b, prompt_tok_b, comp_tok_b = await _generate_plan_via_llm(
            base_prompt,
            _PERSONA_B_SYSTEM,
            get_model_router=get_model_router,
            cost_tracker=cost_tracker,
            db=db,
            user_id=mission.user_id,
            mission_id=str(mission.id),
            temperature=0.9,  # higher temp for creative/diverse plans
        )
        if not llm_tasks_b:
            # Fallback: use heuristic if LLM fails — mark degraded.
            llm_tasks_b = heuristic_tasks
            persona_b = _finalize_candidate(
                plan_id="llm_persona_b",
                generation_strategy=PlanCandidate.FALLBACK,
                tasks=llm_tasks_b,
                rationale="LLM persona B failed; substituted heuristic plan. DEGRADED — requires human review.",
                latency_override_ms=int(latency_b * 1000),
                token_override=prompt_tok_b + comp_tok_b,
                degraded=True,
            )
        else:
            persona_b = _finalize_candidate(
                plan_id="llm_persona_b",
                generation_strategy="llm_persona",
                tasks=llm_tasks_b,
                rationale="LLM persona: thorough strategist. Prefers detailed, "
                "resilient plans with fallbacks and review steps. "
                "Higher temperature for diverse planning.",
                latency_override_ms=int(latency_b * 1000),
                token_override=prompt_tok_b + comp_tok_b,
            )
        candidates.append(persona_b)

    return candidates


def _finalize_candidate(
    *,
    plan_id: str,
    generation_strategy: str,
    tasks: list[dict],
    rationale: str,
    latency_override_ms: int | None = None,
    token_override: int | None = None,
    degraded: bool = False,
) -> PlanCandidate:
    """Build a PlanCandidate with deterministic cost estimates and score.

    Args:
        degraded: True when this candidate was produced by a forced fallback
            (e.g. an LLM strategy failed and was substituted with heuristic
            tasks). Degraded candidates are NEVER allowed to auto-ship — the
            planner routes them to PLANNED_PENDING_REVIEW. See
            side-effect-safety-and-planner-trust skill.
    """
    estimated_tokens = token_override if token_override is not None else estimate_tokens_for_tasks(tasks)
    estimated_latency_ms = latency_override_ms if latency_override_ms is not None else estimate_latency_ms(tasks)

    # Cost estimation: use BudgetEnforcer pricing table
    # Default to local model (free) for heuristic; LLM callers set actual cost
    estimated_cost_usd = _estimate_cost_usd(estimated_tokens, generation_strategy)

    risk_flags = detect_risk_flags(tasks)

    candidate = PlanCandidate(
        plan_id=plan_id,
        generation_strategy=generation_strategy,
        tasks=tasks,
        estimated_cost_usd=estimated_cost_usd,
        estimated_latency_ms=estimated_latency_ms,
        estimated_tokens=estimated_tokens,
        quality_score=0.0,  # filled by scorer
        risk_flags=risk_flags,
        rationale=rationale,
        degraded=degraded,
    )
    # Score the candidate
    candidate.quality_score = score_plan(candidate)
    return candidate


def _estimate_cost_usd(total_tokens: int, generation_strategy: str) -> float:
    """Estimate cost in USD for a plan candidate.

    For local models (free), uses a token-based proxy so the scorer can
    still differentiate candidates by resource intensity.  The proxy is
    ``tokens / 1_000_000 * 0.01`` (a "virtual" cent-per-million rate)
    — not a real dollar amount, but a deterministic ranking signal.

    For remote models, uses the BudgetEnforcer pricing table.

    Args:
        total_tokens: Estimated total tokens.
        generation_strategy: Strategy name (heuristic is free).

    Returns:
        Estimated cost in USD (or virtual proxy for local models).
    """
    if generation_strategy == "heuristic":
        # Heuristic plans use no LLM → cost is 0
        return 0.0

    try:
        from app.services.budget_enforcer import get_budget_enforcer

        enforcer = get_budget_enforcer()
        cost = enforcer.pricing.estimate("llamacpp-qwen3.6-27b", total_tokens, 0)
        real_cost = float(cost)
        if real_cost > 0:
            return real_cost
        # Local model is free — use token proxy for differentiation
        return (total_tokens / 1_000_000) * _LOCAL_MODEL_PROXY_RATE_PER_MILLION
    except Exception:
        # Fallback: estimate at $0.14/M tokens (deepseek-chat rate)
        return (total_tokens / 1_000_000) * 0.14
