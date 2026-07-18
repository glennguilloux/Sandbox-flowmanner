"""Chat cost summary — minimal per-user aggregation for the v2 chat surface.

This service backs ``GET /api/v2/chat/costs`` (re-map of the FE's legacy
``/api/chat/costs`` call). It returns the FE ``CostSummary`` shape:

    {
      "period_days": int,
      "total_cost": float,
      "total_tokens": int,
      "total_requests": int,
      "by_model": [{"model", "cost", "tokens", "requests"}],
      "pricing": {"<model>": {"input": float, "output": float}}
    }

Data sources:
- ``pricing`` is derived from the authoritative model catalog
  (``app/config/models_catalog.json`` via ``app.services.model_catalog``) — a
  reference table the FE uses to render per-model cost breakdown.
- ``by_model`` / totals are aggregated from ``LLMCallRecord``, scoped to the
  authenticated user's workspaces and to the "chat/standalone" bucket
  (``mission_id IS NULL``) within the look-back window.

NOTE (flagged data gap): chat LLM calls are NOT currently persisted to
``LLMCallRecord`` — only mission-execution paths write that table (with
``mission_id`` populated). Until chat-cost persistence is wired, ``by_model``
and the totals will be empty for real chat traffic. The endpoint still returns
a schema-faithful ``CostSummary`` (real pricing + correct empty aggregation).
Wiring chat → ``LLMCallRecord`` is a separate card, intentionally out of scope
here (see task SCOPE GUARD).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from sqlalchemy import func, select

from app.models.llm_call_record import LLMCallRecord
from app.services.cross_workspace_service import find_user_workspaces

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.models.user import User


async def get_chat_cost_summary(
    user: User,
    db: AsyncSession,
    days: int = 30,
) -> dict:
    """Return a FE ``CostSummary`` for the given user's chat/standalone usage.

    Args:
        user: Authenticated user (provides ``user.id`` for workspace scoping).
        db: Async DB session.
        days: Look-back window in days.

    Returns:
        Dict matching the FE ``CostSummary`` shape.
    """
    now = datetime.now(UTC)
    since = now - timedelta(days=days)

    # Pricing reference table from the authoritative catalog.
    pricing = _build_pricing_reference()

    # Scope to the user's workspaces. Chat rows that carry no workspace are
    # excluded from the per-user aggregate (they cannot be attributed).
    workspace_ids = await find_user_workspaces(db, user.id)

    if not workspace_ids:
        # No workspace membership → nothing attributable to this user.
        return {
            "period_days": days,
            "total_cost": 0.0,
            "total_tokens": 0,
            "total_requests": 0,
            "by_model": [],
            "pricing": pricing,
        }

    rows = await db.execute(
        select(
            LLMCallRecord.model_id,
            func.coalesce(func.sum(LLMCallRecord.prompt_tokens), 0),
            func.coalesce(func.sum(LLMCallRecord.completion_tokens), 0),
            func.coalesce(func.sum(LLMCallRecord.cost_usd), 0.0),
            func.count(LLMCallRecord.id),
        )
        .where(
            LLMCallRecord.mission_id.is_(None),
            LLMCallRecord.timestamp >= since,
            LLMCallRecord.workspace_id.in_(workspace_ids),
        )
        .group_by(LLMCallRecord.model_id)
    )

    by_model: list[dict] = []
    total_cost = 0.0
    total_tokens = 0
    total_requests = 0
    for model_id, prompt_tokens, completion_tokens, cost_usd, requests in rows.all():
        tokens = int(prompt_tokens) + int(completion_tokens)
        by_model.append(
            {
                "model": model_id,
                "cost": round(float(cost_usd), 6),
                "tokens": tokens,
                "requests": int(requests),
            }
        )
        total_cost += float(cost_usd)
        total_tokens += tokens
        total_requests += int(requests)

    by_model.sort(key=lambda item: item["cost"], reverse=True)

    return {
        "period_days": days,
        "total_cost": round(total_cost, 6),
        "total_tokens": total_tokens,
        "total_requests": total_requests,
        "by_model": by_model,
        "pricing": pricing,
    }


def _build_pricing_reference() -> dict[str, dict[str, float]]:
    """Build the ``{model: {input, output}}`` pricing reference from the catalog."""
    try:
        from app.services.model_catalog import get_model_catalog

        catalog = get_model_catalog()
        specs = catalog.all_specs  # type: ignore[attr-defined]
    except Exception:
        return {}

    pricing: dict[str, dict[str, float]] = {}
    for spec in specs:
        if not spec.enabled:
            continue
        pricing[spec.model_id] = {
            "input": float(spec.input_per_1m),
            "output": float(spec.output_per_1m),
        }
    return pricing
