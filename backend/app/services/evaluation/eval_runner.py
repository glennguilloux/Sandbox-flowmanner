"""Evaluation runner — execute golden datasets against models and score results."""

import asyncio
import hashlib
import json
import logging
import time
import uuid
from datetime import UTC, datetime
from typing import Any

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
        # Comment 10: per-run accumulators for cost-per-correct-answer.
        self._run_cost_usd: float = 0.0
        self._run_latency_ms: int = 0
        self._run_correct: int = 0
        self._run_providers: dict[str, int] = {}

    # Rubric overall-score (1-5) at/above which a case counts as "correct".
    CORRECT_THRESHOLD: float = 3.0

    async def run_evaluation(
        self,
        dataset_id: str,
        model_name: str | None = None,
        model_config: dict[str, Any] | None = None,
        system_prompt: str | None = None,
        temperature: float = 0.7,
        max_concurrency: int = 5,
        judge_model: str | None = None,
    ) -> EvalRun:
        # Comment 10: reset per-run accumulators so repeated runs on the same
        # runner instance (compare_candidates) never double-count cost/correct.
        self._run_cost_usd = 0.0
        self._run_latency_ms = 0
        self._run_correct = 0
        self._run_providers = {}

        model_name = model_name or settings.LLM_MODEL_NAME
        config = model_config or {}
        if system_prompt:
            config["system_prompt"] = system_prompt
        config["temperature"] = temperature
        config_hash = self._compute_config_hash(config)

        # Validate dataset exists before creating run
        ds_result = await self.db.execute(select(GoldenDataset).where(GoldenDataset.id == dataset_id))
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
        result = await self.db.execute(select(GoldenTestCase).where(GoldenTestCase.dataset_id == dataset_id))
        test_cases = list(result.scalars().all())

        if not test_cases:
            eval_run.status = "failed"
            eval_run.error_message = "No test cases found in dataset"
            eval_run.completed_at = datetime.now(UTC)
            await self.db.flush()
            return eval_run

        langfuse_trace_id = str(uuid.uuid4())
        eval_run.langfuse_trace_id = langfuse_trace_id

        run_start = time.perf_counter()

        # Create Langfuse trace only when Langfuse is enabled
        langfuse = None
        if settings.LANGFUSE_ENABLED:
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
            tasks = [self._run_single_case(semaphore, tc, model_name, system_prompt, temperature) for tc in test_cases]
            case_results = await asyncio.gather(*tasks, return_exceptions=True)

            # Score results with LLM judge (fixed/deterministic judge model where possible).
            judge = LLMJudge(model=judge_model)
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
                            "correct": False,
                            "usage": {},
                            "cost_usd": 0.0,
                            "latency_ms": 0,
                            "provider": None,
                            "served_model": model_name,
                            "judge_model": judge.model,
                            "success": False,
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
                    # Comment 10: capture model-call usage for cost-per-correct-answer.
                    usage: dict[str, Any] = result.get("usage", {}) if isinstance(result, dict) else {}
                    cost_usd = float(result.get("cost_usd", 0.0)) if isinstance(result, dict) else 0.0
                    latency_ms = int(result.get("latency_ms", 0) or 0) if isinstance(result, dict) else 0
                    provider = result.get("provider") if isinstance(result, dict) else None
                    served_model = (
                        result.get("served_model") or result.get("model") if isinstance(result, dict) else model_name
                    )
                    is_correct = case_score >= self.CORRECT_THRESHOLD
                    scored_results.append(
                        {
                            "test_case_id": tc.id,
                            "task_type": tc.task_type,
                            "input_preview": tc.input_prompt[:100],
                            "output_preview": (result.get("output") if isinstance(result, dict) else str(result))[:200],
                            "scores": score.get("scores", {}),
                            "overall_score": case_score,
                            "summary": score.get("summary", ""),
                            "correct": is_correct,
                            "usage": usage,
                            "cost_usd": cost_usd,
                            "latency_ms": latency_ms,
                            "provider": provider,
                            "served_model": served_model,
                            "judge_model": judge.model,
                            "success": True,
                        }
                    )

                    # Track per-category scores
                    cat = tc.task_type
                    if cat not in category_scores:
                        category_scores[cat] = []
                    category_scores[cat].append(case_score)

                    # Comment 10: accumulate run-level cost/latency/provider.
                    self._run_cost_usd += cost_usd
                    self._run_latency_ms += latency_ms
                    if provider:
                        self._run_providers[provider] = self._run_providers.get(provider, 0) + 1
                    if is_correct:
                        self._run_correct += 1

                    # Record per-case metrics (pass = score >= 3.0)
                    record_eval_test_case(model_name, tc.task_type, case_score >= 3.0)

            # Compute aggregates
            all_scores = [r["overall_score"] for r in scored_results if "error" not in r]
            aggregate = sum(all_scores) / len(all_scores) if all_scores else 0.0

            avg_by_category = {cat: round(sum(scores) / len(scores), 2) for cat, scores in category_scores.items()}

            total_cases = len(scored_results)
            correct = self._run_correct
            pass_rate = (correct / total_cases) if total_cases else 0.0
            cost_per_correct = (self._run_cost_usd / correct) if correct else None
            dominant_provider = (
                max(self._run_providers.items(), key=lambda kv: kv[1])[0] if self._run_providers else None
            )

            eval_run.status = "completed"
            eval_run.aggregate_score = round(aggregate, 2)
            eval_run.scores_by_category = avg_by_category
            eval_run.per_case_scores = scored_results
            eval_run.total_cost_usd = round(self._run_cost_usd, 6)
            eval_run.total_latency_ms = self._run_latency_ms
            eval_run.routed_provider = dominant_provider
            eval_run.judge_model = judge.model
            eval_run.correct_count = correct
            eval_run.pass_rate = round(pass_rate, 4)
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
            try:
                from app.core.metrics import record_eval_run_cost

                record_eval_run_cost(
                    model=model_name,
                    total_cost_usd=self._run_cost_usd,
                    correct_count=correct,
                    cost_per_correct=cost_per_correct,
                    pass_rate=pass_rate,
                )
            except Exception:
                logger.debug("eval cost metric skipped", exc_info=True)

            # Push score to Langfuse (only when enabled)
            if langfuse and langfuse.enabled:
                try:
                    langfuse.score_trace(
                        trace_id=langfuse_trace_id,
                        name="eval_aggregate_score",
                        value=round(aggregate, 2),
                        comment=f"Eval run {eval_run.id}: {len(all_scores)} cases scored",
                    )
                except Exception as e:
                    logger.debug("Langfuse score push skipped: %s", e)

        except Exception as e:
            logger.exception("Evaluation run failed")
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
        judge_model: str | None = None,
    ) -> dict[str, Any]:
        run_a = await self.run_evaluation(
            dataset_id, model_name=model_a, system_prompt=system_prompt, judge_model=judge_model
        )
        run_b = await self.run_evaluation(
            dataset_id, model_name=model_b, system_prompt=system_prompt, judge_model=judge_model
        )

        def _summary(run: EvalRun) -> dict[str, Any]:
            a = run.aggregate_score or 0.0
            b = run_b.aggregate_score or 0.0
            return {
                "name": run.model_name,
                "aggregate_score": run.aggregate_score,
                "scores_by_category": run.scores_by_category,
                "status": run.status,
                "total_cost_usd": run.total_cost_usd,
                "cost_per_correct": (
                    round(run.total_cost_usd / run.correct_count, 6)
                    if run.correct_count and run.correct_count > 0
                    else None
                ),
                "pass_rate": run.pass_rate,
                "correct_count": run.correct_count,
                "routed_provider": run.routed_provider,
                "judge_model": run.judge_model,
            }

        return {
            "model_a": _summary(run_a),
            "model_b": _summary(run_b),
            "delta": round((run_b.aggregate_score or 0) - (run_a.aggregate_score or 0), 2),
            "winner": (model_b if (run_b.aggregate_score or 0) > (run_a.aggregate_score or 0) else model_a),
        }

    async def compare_candidates(
        self,
        dataset_id: str,
        candidate_models: list[str],
        *,
        system_prompt: str | None = None,
        temperature: float = 0.7,
        judge_model: str | None = None,
    ) -> dict[str, Any]:
        """Comment 10: run the SAME dataset/prompt/config against a list of
        candidate models and rank them by quality and cost efficiency.

        Uses a single fixed judge model across all candidates so the quality
        comparison is apples-to-apples. Returns aggregate score, pass rate,
        total cost, and cost-per-correct-answer per candidate, plus a ranked
        list (cheapest-correct first, then highest score).
        """
        candidates = list(dict.fromkeys(candidate_models))  # de-dup, keep order
        runs: dict[str, EvalRun] = {}
        for model in candidates:
            runs[model] = await self.run_evaluation(
                dataset_id,
                model_name=model,
                system_prompt=system_prompt,
                temperature=temperature,
                judge_model=judge_model,
            )

        per_candidate = []
        for model, run in runs.items():
            per_candidate.append(
                {
                    "model": model,
                    "aggregate_score": run.aggregate_score,
                    "pass_rate": run.pass_rate,
                    "correct_count": run.correct_count,
                    "total_cost_usd": run.total_cost_usd,
                    "total_latency_ms": run.total_latency_ms,
                    "routed_provider": run.routed_provider,
                    "judge_model": run.judge_model,
                    "cost_per_correct": (
                        round(run.total_cost_usd / run.correct_count, 6)
                        if run.correct_count and run.correct_count > 0
                        else None
                    ),
                    "status": run.status,
                }
            )

        # Rank: prefer cost-efficiency (cost per correct) for models that pass
        # at least one case, then by aggregate score descending.
        def _rank_key(c: dict[str, Any]):
            cpc = c["cost_per_correct"]
            if cpc is None:
                cpc = float("inf")
            return (cpc, -(c["aggregate_score"] or 0.0))

        ranked = sorted(per_candidate, key=_rank_key)
        return {
            "dataset_id": dataset_id,
            "candidate_count": len(candidates),
            "judge_model": judge_model,
            "candidates": per_candidate,
            "ranked_by_cost_per_correct": [c["model"] for c in ranked],
        }

    async def get_run(self, run_id: str) -> EvalRun | None:
        result = await self.db.execute(select(EvalRun).where(EvalRun.id == run_id))
        return result.scalar_one_or_none()

    async def list_runs(self, dataset_id: str | None = None, limit: int = 20) -> list[EvalRun]:
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
    ) -> dict[str, Any]:
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
    ) -> dict[str, Any]:
        """Call the candidate model and return output + usage telemetry.

        Comment 10: the returned dict carries the generated ``output`` plus
        ``cost_usd``, ``latency_ms``, ``provider`` and ``usage`` so the run can
        compute cost-per-correct-answer without re-instrumenting the enforcer.
        """
        from app.services.budget_enforcer import get_budget_enforcer

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        enforcer = get_budget_enforcer()
        start = time.perf_counter()
        response = await enforcer.call_simple(
            model_id=model_name,
            messages=messages,
            temperature=temperature,
            max_tokens=2048,
        )
        latency_ms = int((time.perf_counter() - start) * 1000)

        if not response.get("success", False):
            raise RuntimeError(f"Eval model call failed: {response.get('error', 'unknown')}")

        cost = response.get("cost", {}) or {}
        out = response.get("response", response.get("content", ""))
        return {
            "output": out,
            "cost_usd": float(cost.get("usd", 0.0) if isinstance(cost.get("usd"), (int, float)) else 0.0),
            "latency_ms": latency_ms,
            "provider": response.get("provider"),
            "served_model": response.get("served_model") or response.get("model") or model_name,
            "usage": {
                "input_tokens": cost.get("input_tokens", 0),
                "output_tokens": cost.get("output_tokens", 0),
            },
            "model": model_name,
        }

    @staticmethod
    def _compute_config_hash(config: dict[str, Any]) -> str:
        raw = json.dumps(config, sort_keys=True)
        return hashlib.sha256(raw.encode()).hexdigest()[:16]
