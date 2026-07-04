#!/usr/bin/env python3
"""
Improvement Loop v2 — Slim dispatch layer.

The original 900-line autonomous self-improvement orchestrator has been
gutted.  Phases 3–6 (hypothesis testing, knob management, success learning,
strategy evolution, metrics collection, alerting) were never wired into
production — 107 missions ran with zero improvement data recorded.

What remains:
- ``on_mission_complete`` hook that dispatches the background review
  Celery task (``review_mission``).  This is the one live component —
  an LLM-based memory writer that reviews completed missions and
  proposes memory writes.
- Singleton lifecycle (``get_improvement_loop``, ``initialize_improvement_loop``).

The failure-type and causal-decomposer libraries (Phases 1–2) are
preserved in sibling modules for reuse by the strategy profiling harness.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class ImprovementLoopV2:
    """Slim dispatch layer for post-mission hooks.

    Only responsibility: fire the background review Celery task after
    every mission completion.  All autonomous self-improvement logic
    (failure analysis, hypothesis testing, knob tuning) has been removed.
    """

    def __init__(self, db_session: Any = None, **kwargs: Any) -> None:
        self.db_session = db_session

    async def on_mission_complete(
        self,
        mission_id: str,
        agent_id: str | None,
        success: bool,
        metrics: dict[str, float] | None = None,
    ) -> None:
        """Hook called when a mission completes.

        Dispatches the background review Celery task (fire-and-forget).
        All other improvement analysis has been removed.
        """
        logger.info(
            "Mission complete hook: mission=%s, success=%s",
            mission_id,
            success,
        )

        # Background self-improvement review — fires for every mission
        # completion (subject to the skip rules inside the Celery task).
        # Fire-and-forget: never blocks the caller.  The Celery task is
        # best-effort — a failure inside ``review_mission`` is logged
        # but does NOT propagate here.
        try:
            import asyncio

            from app.tasks.background_review_tasks import review_mission

            asyncio.create_task(self._dispatch_background_review(review_mission, mission_id))
        except Exception as exc:
            logger.debug(
                "Background review dispatch unavailable for mission=%s: %s",
                mission_id,
                exc,
            )

        # AutoMem Phase 2: scaffold review (fire-and-forget, best-effort)
        # Triggered after every mission completion. The task itself checks
        # whether enough traces have accumulated before calling the meta-LLM.
        try:
            import os

            agent_id = os.environ.get("FLOWMANNER_DEFAULT_AGENT", "")
            if agent_id:
                from app.tasks.meta_review_tasks import review_scaffold

                asyncio.create_task(self._dispatch_scaffold_review(review_scaffold, agent_id, mission_id))
        except Exception as exc:
            logger.debug(
                "Scaffold review dispatch unavailable for mission=%s: %s",
                mission_id,
                exc,
            )

    async def _dispatch_background_review(
        self,
        review_mission: Any,
        mission_id: str,
    ) -> None:
        """Fire-and-forget wrapper for ``review_mission.delay``."""
        try:
            review_mission.delay(mission_id)
        except Exception as exc:
            logger.debug(
                "Background review enqueue failed for mission=%s: %s",
                mission_id,
                exc,
            )

    async def _dispatch_scaffold_review(
        self,
        review_scaffold: Any,
        agent_id: str,
        mission_id: str,
    ) -> None:
        """Fire-and-forget wrapper for ``review_scaffold.delay``."""
        try:
            review_scaffold.delay(agent_id)
        except Exception as exc:
            logger.debug(
                "Scaffold review enqueue failed for mission=%s: %s",
                mission_id,
                exc,
            )


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_improvement_loop: ImprovementLoopV2 | None = None


def get_improvement_loop(
    db_session: Any = None,
    **kwargs: Any,
) -> ImprovementLoopV2:
    """Get or create the improvement loop singleton."""
    global _improvement_loop
    if _improvement_loop is None:
        _improvement_loop = ImprovementLoopV2(db_session=db_session, **kwargs)
    return _improvement_loop


async def initialize_improvement_loop(
    db_session: Any,
    enable_auto_improve: bool = True,
) -> ImprovementLoopV2:
    """Initialize the improvement loop (no-op beyond creating the singleton).

    Kept for backward compatibility — callers in main.py or lifespan can
    still call this without error.
    """
    loop = get_improvement_loop(db_session=db_session)
    logger.info("Improvement loop v2 initialized (slim dispatch layer)")
    return loop


__all__ = [
    "ImprovementLoopV2",
    "get_improvement_loop",
    "initialize_improvement_loop",
]
