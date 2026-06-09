"""Evaluation runner — execute golden datasets against models and score results."""

import asyncio
import hashlib
import json
import logging
import time
import uuid
from datetime import UTC, datetime
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.metrics import record_eval_run, record_eval_test_case
from app.models.evaluation_models import EvalRun, GoldenDataset, GoldenTestCase
from app.services.evaluation.llm_judge import LLMJudge

logger = logging.getLogger(__name__)


class EvaluationRunner:
    """Run golden test cases against a model and score with LLM-as-judge."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def run_evaluation(
        self,
        dataset_id: str,
        model_name: str | None = None,
        model_config: dict[str, Any] | None = None,
        system_prompt: str | None = None,
        temperature: float = 0.7,
        max_concurrency: int = 5,
    ) -> EvalRun:
        model_name = model_name or settings.LLM_MODEL_NAME
        config = model_config or {}
        if system_prompt:
            config["system_prompt"] = system_prompt
        config["temperature"] = temperature
        config_hash = self._compute_config_hash(config)

        # Validate dataset exists before creating run
        ds_result = await self.db.execute(
            select(GoldenDataset).where(GoldenDataset.id == dataset_id)
        )
        if not ds_result.scalar_one_or_none():
            raise ValueError(f"Dataset {dataset_id} not found")

        # Create eval run record
        eval_run = EvalRun(
            dataset_id=dataset_id,
            model_name=model_name,
            model_config_hash=config_hash,
            status="running",
            started_at=datetime.now(UTC),
        )
        self.db.add(eval_run)
        await self.db.flush()

        # Load test cases
        result = await self.db.execute(
            select(GoldenTestCase).where(GoldenTestCase.dataset_id == dataset_id)
        )
        test_cases = list(result.scalars().all())

        if not test_cases:
            eval_run.status = "failed"
            eval_run.error_message = "No test cases found in dataset"
            eval_run.completed_at = datetime.now(UTC)
            await self.db.flush()
            return eval_run

        # Create Langfuse trace for this eval run
        langfuse_trace_id = str(uuid.uuid4())
        eval_run.langfuse_trace_id = langfuse_trace_id

        run_start = time.perf_counter()

        try:
            from app.services.langfuse_service import get_langfuse_service

            langfuse = get_langfuse_service()
            if langfuse.enabled:
                langfuse.trace(
                    trace_id=langfuse_trace_id,
                    name=f"eval_run:{model_name}",
                    user_id="system",
                    metadata={
                        "dataset_id": dataset_id,
                        "model_name": model_name,
                        "config_hash": config_hash,
                        "test_case_count": len(test_cases),
                    },
                    tags=["evaluation", model_name],
                )
        except Exception as e:
            logger.debug("Langfuse trace creation skipped: %s", e)

        try:
            # Run model against test cases with concurrency limit
            semaphore = asyncio.Semaphore(max_concurrency)
            tasks = [
                self._run_single_case(
                    semaphore, tc, model_name, system_prompt, temperature
                )
                for tc in test_cases
            ]
            case_results = await asyncio.gather(*tasks, return_exceptions=True)

            # Score results with LLM judge
            judge = LLMJudge()
            scored_results = []
            category_scores: dict[str, list[float]] = {}

            for i, result in enumerate(case_results):
                tc = test_cases[i]
                if isinstance(result, Exception):
                    scored_results.append(
                        {
                            "test_case_id": tc.id,
                            "task_type": tc.task_type,
                            "error": str(result),
                            "overall_score": 0.0,
                        }
                    )
                    record_eval_test_case(model_name, tc.task_type, False)
                else:
                    score = await judge.score(
                        input_prompt=tc.input_prompt,
                        expected_behavior=tc.expected_behavior,
                        actual_output=result,
                        rubric=tc.rubric,
                    )
                    case_score = score.get("overall_score", 0.0)
                    scored_results.append(
                        {
                            "test_case_id": tc.id,
                            "task_type": tc.task_type,
                            "input_preview": tc.input_prompt[:100],
                            "output_preview": result[:200],
                            "scores": score.get("scores", {}),
                            "overall_score": case_score,
                            "summary": score.get("summary", ""),
                        }
                    )

                    # Track per-category scores
                    cat = tc.task_type
                    if cat not in category_scores:
                        category_scores[cat] = []
                    category_scores[cat].append(case_score)

                    # Record per-case metrics (pass = score >= 3.0)
                    record_eval_test_case(model_name, tc.task_type, case_score >= 3.0)

            # Compute aggregates
            all_scores = [
                r["overall_score"] for r in scored_results if "error" not in r
            ]
            aggregate = sum(all_scores) / len(all_scores) if all_scores else 0.0

            avg_by_category = {
                cat: round(sum(scores) / len(scores), 2)
                for cat, scores in category_scores.items()
            }

            eval_run.status = "completed"
            eval_run.aggregate_score = round(aggregate, 2)
            eval_run.scores_by_category = avg_by_category
            eval_run.per_case_scores = scored_results
            eval_run.completed_at = datetime.now(UTC)

            # Record Prometheus metrics
            duration = time.perf_counter() - run_start
            record_eval_run(
                model=model_name,
                duration_seconds=duration,
                aggregate_score=aggregate,
                category_scores=avg_by_category,
                status="completed",
            )

            # Push score to Langfuse
            try:
                if langfuse.enabled:
                    langfuse.score_trace(
                        trace_id=langfuse_trace_id,
                        name="eval_aggregate_score",
                        value=round(aggregate, 2),
                        comment=f"Eval run {eval_run.id}: {len(all_scores)} cases scored",
                    )
            except Exception as e:
                logger.debug("Langfuse score push skipped: %s", e)

        except Exception as e:
            logger.error("Evaluation run failed: %s", e, exc_info=True)
            eval_run.status = "failed"
            eval_run.error_message = str(e)
            eval_run.completed_at = datetime.now(UTC)

            duration = time.perf_counter() - run_start
            record_eval_run(
                model=model_name,
                duration_seconds=duration,
                aggregate_score=0.0,
                status="failed",
            )

        await self.db.flush()
        return eval_run

    async def compare_models(
        self,
        dataset_id: str,
        model_a: str,
        model_b: str,
        system_prompt: str | None = None,
    ) -> dict[str, Any]:
        run_a = await self.run_evaluation(
            dataset_id, model_name=model_a, system_prompt=system_prompt
        )
        run_b = await self.run_evaluation(
            dataset_id, model_name=model_b, system_prompt=system_prompt
        )

        return {
            "model_a": {
                "name": model_a,
                "aggregate_score": run_a.aggregate_score,
                "scores_by_category": run_a.scores_by_category,
                "status": run_a.status,
            },
            "model_b": {
                "name": model_b,
                "aggregate_score": run_b.aggregate_score,
                "scores_by_category": run_b.scores_by_category,
                "status": run_b.status,
            },
            "delta": round(
                (run_b.aggregate_score or 0) - (run_a.aggregate_score or 0), 2
            ),
            "winner": (
                model_b
                if (run_b.aggregate_score or 0) > (run_a.aggregate_score or 0)
                else model_a
            ),
        }

    async def get_run(self, run_id: str) -> EvalRun | None:
        result = await self.db.execute(select(EvalRun).where(EvalRun.id == run_id))
        return result.scalar_one_or_none()

    async def list_runs(
        self, dataset_id: str | None = None, limit: int = 20
    ) -> list[EvalRun]:
        stmt = select(EvalRun).order_by(EvalRun.created_at.desc()).limit(limit)
        if dataset_id:
            stmt = stmt.where(EvalRun.dataset_id == dataset_id)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def _run_single_case(
        self,
        semaphore: asyncio.Semaphore,
        test_case: GoldenTestCase,
        model_name: str,
        system_prompt: str | None,
        temperature: float,
    ) -> str:
        async with semaphore:
            return await self._call_model(
                model_name=model_name,
                prompt=test_case.input_prompt,
                system_prompt=system_prompt,
                temperature=temperature,
            )

    async def _call_model(
        self,
        model_name: str,
        prompt: str,
        system_prompt: str | None = None,
        temperature: float = 0.7,
    ) -> str:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {settings.LLM_API_KEY}",
        }
        payload = {
            "model": model_name,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": 2048,
        }

        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(
                f"{settings.LLM_API_BASE}/chat/completions",
                headers=headers,
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"]

    @staticmethod
    def _compute_config_hash(config: dict[str, Any]) -> str:
        raw = json.dumps(config, sort_keys=True)
        return hashlib.sha256(raw.encode()).hexdigest()[:16]
