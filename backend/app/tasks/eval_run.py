"""Eval Suite Celery task — run golden datasets asynchronously.

Phase 6: wraps the existing EvaluationRunner in a Celery task for
non-blocking eval execution.  Reuses the existing evaluation/LLM-as-judge
module — does NOT reinvent the judge loop.
"""

from __future__ import annotations

import asyncio
import logging

from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(
    name="evaluation.run_suite",
    bind=True,
    max_retries=2,
    default_retry_delay=60,
    acks_late=True,
)
def run_eval_suite(
    self,
    dataset_id: str,
    model_name: str | None = None,
    system_prompt: str | None = None,
    temperature: float = 0.7,
    judge_model: str | None = None,
) -> dict:
    """Run an evaluation suite (GoldenDataset) against a model asynchronously.

    Args:
        dataset_id: UUID of the GoldenDataset to run.
        model_name: Override model name (defaults to settings.LLM_MODEL_NAME).
        system_prompt: Optional system prompt for the evaluation calls.
        temperature: LLM temperature for the evaluation calls.

    Returns:
        dict with keys: eval_run_id, status, aggregate_score, scores_by_category.

    Reuses the existing EvaluationRunner + LLMJudge — no parallel scorer.
    """
    logger.info("eval_suite_start dataset_id=%s model=%s", dataset_id, model_name)

    try:
        result = asyncio.run(_run_eval_async(dataset_id, model_name, system_prompt, temperature, judge_model))
        logger.info(
            "eval_suite_complete dataset_id=%s status=%s score=%s",
            dataset_id,
            result.get("status"),
            result.get("aggregate_score"),
        )
        return result
    except Exception as exc:
        logger.exception("eval_suite_failed dataset_id=%s", dataset_id)
        # Retry on transient errors (DB connection, LLM timeout)
        if self.request.retries < self.max_retries:
            raise self.retry(exc=exc)
        return {
            "eval_run_id": None,
            "status": "failed",
            "error": str(exc),
            "aggregate_score": 0.0,
            "scores_by_category": {},
        }


async def _run_eval_async(
    dataset_id: str,
    model_name: str | None,
    system_prompt: str | None,
    temperature: float,
    judge_model: str | None = None,
) -> dict:
    """Async helper: open a fresh DB session and run the evaluation."""
    from app.database import AsyncSessionLocal
    from app.services.evaluation.eval_runner import EvaluationRunner

    async with AsyncSessionLocal() as db:
        runner = EvaluationRunner(db)
        eval_run = await runner.run_evaluation(
            dataset_id=dataset_id,
            model_name=model_name,
            system_prompt=system_prompt,
            temperature=temperature,
            judge_model=judge_model,
        )
        await db.commit()

        return {
            "eval_run_id": eval_run.id,
            "status": eval_run.status,
            "aggregate_score": eval_run.aggregate_score,
            "scores_by_category": eval_run.scores_by_category or {},
            "per_case_count": len(eval_run.per_case_scores or []),
        }


@celery_app.task(
    name="evaluation.run_candidate_comparison",
    bind=True,
    max_retries=1,
    default_retry_delay=120,
    acks_late=True,
)
def run_candidate_comparison(
    self,
    dataset_id: str,
    candidate_models: list[str],
    system_prompt: str | None = None,
    temperature: float = 0.7,
    judge_model: str | None = None,
) -> dict:
    """Comment 10: run a dataset against several candidate models and rank
    them by quality and cost efficiency.  Reuses EvaluationRunner.compare_candidates.
    """
    logger.info(
        "eval_candidate_comparison_start dataset_id=%s candidates=%s",
        dataset_id,
        candidate_models,
    )
    try:
        result = asyncio.run(
            _run_comparison_async(dataset_id, candidate_models, system_prompt, temperature, judge_model)
        )
        return result
    except Exception as exc:
        logger.exception("eval_candidate_comparison_failed dataset_id=%s", dataset_id)
        if self.request.retries < self.max_retries:
            raise self.retry(exc=exc)
        return {"status": "failed", "error": str(exc)}


async def _run_comparison_async(
    dataset_id: str,
    candidate_models: list[str],
    system_prompt: str | None,
    temperature: float,
    judge_model: str | None,
) -> dict:
    from app.database import AsyncSessionLocal
    from app.services.evaluation.eval_runner import EvaluationRunner

    async with AsyncSessionLocal() as db:
        runner = EvaluationRunner(db)
        comparison = await runner.compare_candidates(
            dataset_id,
            candidate_models,
            system_prompt=system_prompt,
            temperature=temperature,
            judge_model=judge_model,
        )
        await db.commit()
        return comparison
