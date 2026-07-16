"""Eval Run API — trigger eval suite runs and view results.

Phase 6: wraps the existing GoldenDataset/EvalRun models with API
endpoints and dispatches the Celery task for async execution.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select

from app.api.deps import get_current_user
from app.database import get_db
from app.models.evaluation_models import EvalRun, GoldenDataset

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/evals", tags=["evals"])


# ── Request / Response schemas ──────────────────────────────────────


class TriggerEvalRequest(BaseModel):
    dataset_id: str
    model_name: str | None = None
    system_prompt: str | None = None
    temperature: float = 0.7


class EvalRunResponse(BaseModel):
    id: str
    dataset_id: str
    model_name: str
    status: str
    aggregate_score: float | None
    scores_by_category: dict | None
    per_case_count: int
    # Comment 10: cost-per-correct-answer fields.
    total_cost_usd: float | None = None
    total_latency_ms: int | None = None
    routed_provider: str | None = None
    judge_model: str | None = None
    pass_rate: float | None = None
    correct_count: int | None = None
    error_message: str | None
    started_at: str | None
    completed_at: str | None

    class Config:
        from_attributes = True


class CompareCandidatesRequest(BaseModel):
    dataset_id: str
    candidate_models: list[str]
    system_prompt: str | None = None
    temperature: float = 0.7
    # A single fixed/deterministic judge model keeps the quality comparison
    # apples-to-apples across candidates (Comment 10).
    judge_model: str | None = None


class EvalRunListResponse(BaseModel):
    items: list[EvalRunResponse]
    total: int


# ── Endpoints ───────────────────────────────────────────────────────


@router.post("/run", status_code=202)
async def trigger_eval_run(
    body: TriggerEvalRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Trigger an async eval run via Celery. Returns the task ID for polling."""
    # Validate dataset exists
    result = await db.execute(select(GoldenDataset).where(GoldenDataset.id == body.dataset_id))
    if result.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Dataset not found")

    from app.tasks.eval_run import run_eval_suite

    task = run_eval_suite.delay(
        dataset_id=body.dataset_id,
        model_name=body.model_name,
        system_prompt=body.system_prompt,
        temperature=body.temperature,
    )

    return {"task_id": task.id, "status": "queued", "dataset_id": body.dataset_id}


@router.get("/runs", response_model=EvalRunListResponse)
async def list_eval_runs(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    dataset_id: str | None = None,
    status: str | None = None,
    limit: int = 20,
):
    """List eval runs, optionally filtered by dataset or status."""
    stmt = select(EvalRun).order_by(EvalRun.created_at.desc()).limit(limit)
    if dataset_id:
        stmt = stmt.where(EvalRun.dataset_id == dataset_id)
    if status:
        stmt = stmt.where(EvalRun.status == status)

    result = await db.execute(stmt)
    items = list(result.scalars().all())

    return EvalRunListResponse(
        items=[
            EvalRunResponse(
                id=er.id,
                dataset_id=er.dataset_id,
                model_name=er.model_name,
                status=er.status,
                aggregate_score=er.aggregate_score,
                scores_by_category=er.scores_by_category,
                per_case_count=len(er.per_case_scores) if er.per_case_scores else 0,
                total_cost_usd=er.total_cost_usd,
                total_latency_ms=er.total_latency_ms,
                routed_provider=er.routed_provider,
                judge_model=er.judge_model,
                pass_rate=er.pass_rate,
                correct_count=er.correct_count,
                error_message=er.error_message,
                started_at=er.started_at.isoformat() if er.started_at else None,
                completed_at=er.completed_at.isoformat() if er.completed_at else None,
            )
            for er in items
        ],
        total=len(items),
    )


@router.post("/compare", status_code=202)
async def compare_candidate_models(
    body: CompareCandidatesRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Comment 10: run the same dataset/prompt/config against a list of
    candidate models and rank them by quality and cost efficiency.

    Returns a task id; poll ``GET /evals/runs`` or the comparison result.  The
    heavy lifting is delegated to a Celery task so large candidate sets don't
    block the request.
    """
    if not body.candidate_models:
        raise HTTPException(status_code=422, detail="candidate_models must be non-empty")

    from app.tasks.eval_run import run_candidate_comparison

    task = run_candidate_comparison.delay(
        dataset_id=body.dataset_id,
        candidate_models=body.candidate_models,
        system_prompt=body.system_prompt,
        temperature=body.temperature,
        judge_model=body.judge_model,
    )
    return {
        "task_id": task.id,
        "status": "queued",
        "dataset_id": body.dataset_id,
        "candidate_models": body.candidate_models,
    }


@router.get("/runs/{run_id}", response_model=EvalRunResponse)
async def get_eval_run(
    run_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Get a specific eval run with full details."""
    result = await db.execute(select(EvalRun).where(EvalRun.id == run_id))
    er = result.scalar_one_or_none()
    if er is None:
        raise HTTPException(status_code=404, detail="Eval run not found")

    return EvalRunResponse(
        id=er.id,
        dataset_id=er.dataset_id,
        model_name=er.model_name,
        status=er.status,
        aggregate_score=er.aggregate_score,
        scores_by_category=er.scores_by_category,
        per_case_count=len(er.per_case_scores) if er.per_case_scores else 0,
        total_cost_usd=er.total_cost_usd,
        total_latency_ms=er.total_latency_ms,
        routed_provider=er.routed_provider,
        judge_model=er.judge_model,
        pass_rate=er.pass_rate,
        correct_count=er.correct_count,
        error_message=er.error_message,
        started_at=er.started_at.isoformat() if er.started_at else None,
        completed_at=er.completed_at.isoformat() if er.completed_at else None,
    )


@router.get("/runs/{run_id}/cases")
async def get_eval_run_cases(
    run_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Get per-case scores for a specific eval run."""
    result = await db.execute(select(EvalRun).where(EvalRun.id == run_id))
    er = result.scalar_one_or_none()
    if er is None:
        raise HTTPException(status_code=404, detail="Eval run not found")

    return {
        "run_id": er.id,
        "per_case_scores": er.per_case_scores or [],
        "aggregate_score": er.aggregate_score,
        "scores_by_category": er.scores_by_category or {},
    }
