"""Meta review Celery task — scaffold improvement proposals (AutoMem Phase 2).

Single task: ``review_scaffold(agent_id)``. Invoked by
``services/improvement/improvement_loop_v2.on_mission_complete`` via
fire-and-forget (periodic or threshold-triggered).

Best-effort semantics: a runtime failure MUST NOT propagate — the task
returns a structured error dict and logs the failure.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

import structlog

from .celery_app import celery_app

logger = structlog.get_logger(__name__)

# Minimum number of missions with memory actions before we review scaffold.
# Too few traces = noisy signal = wasted LLM call.
MIN_MISSIONS_FOR_SCAFFOLD_REVIEW = 10


@celery_app.task(
    name="app.tasks.meta_review_tasks.review_scaffold",
    bind=True,
    max_retries=1,
    default_retry_delay=60,
    acks_late=True,
)
def review_scaffold(self, agent_id: str, workspace_id: str | None = None) -> dict[str, Any]:
    """Review an agent's scaffold and propose improvements if warranted.

    Best-effort: never raises. Returns a structured summary dict.
    """
    started = time.perf_counter()
    summary: dict[str, Any] = {
        "agent_id": agent_id,
        "outcome": "skipped",
        "reason": "",
        "proposal_id": None,
        "confidence": 0.0,
        "soundness": 0.0,
        "duration_ms": 0,
        "error": "",
    }

    try:
        asyncio.run(_review_scaffold_async(agent_id, workspace_id, summary))
    except Exception as exc:
        logger.exception("review_scaffold crashed for agent=%s", agent_id)
        summary["outcome"] = "error"
        summary["error"] = str(exc)
    finally:
        summary["duration_ms"] = int((time.perf_counter() - started) * 1000)
        logger.info("review_scaffold summary: %s", summary)

    return summary


async def _review_scaffold_async(
    agent_id: str,
    workspace_id: str | None,
    summary: dict[str, Any],
) -> None:
    """Async body of review_scaffold."""
    from app.database import AsyncSessionLocal
    from app.services.memory.meta_review_service import MetaReviewService
    from app.services.memory.trace_export_service import TraceExportService
    from app.services.memory.validation_harness import ValidationHarness

    # ── 1. Read the current agent prompt ──────────────────────────────
    current_prompt = await _read_agent_prompt(agent_id)
    if not current_prompt:
        summary["outcome"] = "skipped"
        summary["reason"] = "agent_prompt_not_found"
        return

    async with AsyncSessionLocal() as db:
        # ── 2. Export traces ──────────────────────────────────────────
        export_service = TraceExportService(db)
        traces = await export_service.export_episode_traces(
            workspace_id=workspace_id,
            limit=20,
        )

        if len(traces) < 5:
            summary["outcome"] = "skipped"
            summary["reason"] = f"insufficient_traces ({len(traces)}/5)"
            return

        # ── 3. Call meta-LLM ──────────────────────────────────────────
        meta_service = MetaReviewService(db)
        result = await meta_service.review_scaffold(
            agent_id=agent_id,
            current_prompt=current_prompt,
            episode_traces=traces,
        )

        if not result.success:
            summary["outcome"] = "meta_review_failed"
            summary["error"] = result.error
            return

        if not result.proposed_prompt:
            summary["outcome"] = "no_changes_proposed"
            summary["reason"] = result.reasoning
            return

        # ── 4. Validate proposal ──────────────────────────────────────
        harness = ValidationHarness()
        metrics = await harness.validate_proposal(
            current_prompt=current_prompt,
            proposed_prompt=result.proposed_prompt,
            reasoning=result.reasoning,
            episode_traces=traces,
        )

        summary["confidence"] = metrics.confidence_score
        summary["soundness"] = metrics.soundness_score

        if not metrics.approved:
            summary["outcome"] = "validation_rejected"
            summary["reason"] = metrics.reasoning
            # Update the proposal status to rejected
            if result.proposal_id:
                from sqlalchemy import select as sa_select

                from app.models.scaffold_models import ScaffoldProposal, ScaffoldProposalStatus

                proposal = (
                    await db.execute(sa_select(ScaffoldProposal).where(ScaffoldProposal.id == result.proposal_id))
                ).scalar_one_or_none()
                if proposal is not None:
                    proposal.status = ScaffoldProposalStatus.REJECTED
                    proposal.validation_metrics = metrics.to_dict()
                    await db.commit()
            return

        # ── 5. Stage proposal for approval ────────────────────────────
        # The proposal was already created by MetaReviewService.review_scaffold().
        # Update its validation metrics.
        if result.proposal_id:
            from sqlalchemy import select as sa_select

            from app.models.scaffold_models import ScaffoldProposal

            proposal = (
                await db.execute(sa_select(ScaffoldProposal).where(ScaffoldProposal.id == result.proposal_id))
            ).scalar_one_or_none()
            if proposal is not None:
                proposal.validation_metrics = metrics.to_dict()
                await db.commit()

        summary["outcome"] = "proposal_staged"
        summary["proposal_id"] = result.proposal_id


async def _read_agent_prompt(agent_id: str) -> str:
    """Read an agent's current prompt from the .md file in agent_definitions/."""
    import os
    from pathlib import Path

    # Search for the agent definition file
    base = Path("/opt/flowmanner/backend/agent_definitions")
    if not base.exists():
        return ""

    for md_file in base.rglob("*.md"):
        # Match by filename pattern: division/agent-name.md
        stem = md_file.stem.lower()
        if agent_id.lower() in stem or stem in agent_id.lower():
            try:
                return md_file.read_text(encoding="utf-8")
            except Exception:
                continue

    return ""
