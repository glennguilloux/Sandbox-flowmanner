"""Strategy metadata endpoint.

Exposes available workflow execution strategies and their status
(deprecated, experimental) so the frontend can inform users which
strategies are available for the current model.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.services.substrate.strategies import StrategyRegistry

router = APIRouter(prefix="/strategies", tags=["strategies"])


@router.get("")
async def list_strategies():
    """List all registered workflow execution strategies.

    Returns strategy type, deprecated/experimental flags, and a
    short description for each.  The frontend uses this to disable
    strategies that won't work with the current model.
    """
    strategies = StrategyRegistry.available_strategies()
    deprecated = StrategyRegistry.deprecated_strategies()
    return {
        # Primary list: only strategies that actually work. Deprecated
        # strategies (0% success with the 27B model per 2026-07-04
        # profiling) are excluded here so the UI never offers them as
        # selectable — they remain reachable behind STRATEGY_ALLOW_DEPRECATED.
        "strategies": strategies,
        "deprecated": deprecated,
        "total": len(strategies) + len(deprecated),
        "available": len(strategies),
    }
