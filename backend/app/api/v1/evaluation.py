"""Evaluation API — golden datasets, test cases, and eval runs."""

import logging
from datetime import UTC, datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_role
from app.database import get_db
from app.models.user import User
from app.services.evaluation.dataset_builder import DatasetBuilder
from app.services.evaluation.eval_runner import EvaluationRunner

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/evaluation", tags=["evaluation"])


# ── Request / Response schemas ──────────────────────────────────────────


class CreateDatasetRequest(BaseModel):
    name: str
    category: str = Field(..., description="code, review, rag, agent, creative")
    description: str = ""


class CreateTestCaseRequest(BaseModel):
    input_prompt: str
    expected_behavior: str
    task_type: str = Field(
        ...,
        description="code_generation, rag_accuracy, agent_reasoning, creative, general",
    )
    difficulty: str = Field("medium", pattern="^(easy|medium|hard)$")
    tags: list[str] = Field(default_factory=list)
    rubric: dict[str, Any] | None = None


class BulkCreateTestCasesRequest(BaseModel):
    cases: list[CreateTestCaseRequest]


class UpdateTestCaseRequest(BaseModel):
    input_prompt: str | None = None
    expected_behavior: str | None = None
    task_type: str | None = None
    difficulty: str | None = None
    tags: list[str] | None = None
    rubric: dict[str, Any] | None = None


class RunEvaluationRequest(BaseModel):
    dataset_id: str
    model_name: str | None = None
    system_prompt: str | None = None
    temperature: float = Field(0.7, ge=0.0, le=2.0)


class CompareModelsRequest(BaseModel):
    dataset_id: str
    model_a: str
    model_b: str
    system_prompt: str | None = None


class ImportLangfuseRequest(BaseModel):
    dataset_name: str
    traces: list[dict[str, Any]]
    category: str = "imported"


# ── Dataset endpoints ───────────────────────────────────────────────────


@router.post("/datasets")
async def create_dataset(
    body: CreateDatasetRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    builder = DatasetBuilder(db)
    ds = await builder.create_dataset(name=body.name, category=body.category, description=body.description)
    return {
        "id": ds.id,
        "name": ds.name,
        "category": ds.category,
        "version": ds.version,
    }


@router.get("/datasets")
async def list_datasets(
    category: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    builder = DatasetBuilder(db)
    datasets = await builder.list_datasets(category=category)
    return {
        "datasets": [
            {
                "id": d.id,
                "name": d.name,
                "category": d.category,
                "version": d.version,
                "description": d.description,
                "created_at": d.created_at.isoformat() if d.created_at else None,
            }
            for d in datasets
        ]
    }


@router.get("/datasets/{dataset_id}")
async def get_dataset(
    dataset_id: str,
    db: AsyncSession = Depends(get_db),
):
    builder = DatasetBuilder(db)
    ds = await builder.get_dataset(dataset_id)
    if not ds:
        raise HTTPException(404, "Dataset not found")
    cases = await builder.get_test_cases(dataset_id)
    return {
        "id": ds.id,
        "name": ds.name,
        "category": ds.category,
        "version": ds.version,
        "description": ds.description,
        "test_case_count": len(cases),
        "created_at": ds.created_at.isoformat() if ds.created_at else None,
    }


@router.delete("/datasets/{dataset_id}")
async def delete_dataset(
    dataset_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    from sqlalchemy import select

    from app.models.evaluation_models import GoldenDataset

    result = await db.execute(select(GoldenDataset).where(GoldenDataset.id == dataset_id))
    ds = result.scalar_one_or_none()
    if not ds:
        raise HTTPException(404, "Dataset not found")
    await db.delete(ds)
    await db.flush()
    return {"deleted": True}


# ── Test case endpoints ─────────────────────────────────────────────────


@router.post("/datasets/{dataset_id}/test-cases")
async def add_test_case(
    dataset_id: str,
    body: CreateTestCaseRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    builder = DatasetBuilder(db)
    ds = await builder.get_dataset(dataset_id)
    if not ds:
        raise HTTPException(404, "Dataset not found")
    tc = await builder.add_test_case(
        dataset_id=dataset_id,
        input_prompt=body.input_prompt,
        expected_behavior=body.expected_behavior,
        task_type=body.task_type,
        difficulty=body.difficulty,
        tags=body.tags,
        rubric=body.rubric,
    )
    return {"id": tc.id, "task_type": tc.task_type, "difficulty": tc.difficulty}


@router.post("/datasets/{dataset_id}/test-cases/bulk")
async def add_test_cases_bulk(
    dataset_id: str,
    body: BulkCreateTestCasesRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    builder = DatasetBuilder(db)
    ds = await builder.get_dataset(dataset_id)
    if not ds:
        raise HTTPException(404, "Dataset not found")
    cases_data = [c.model_dump() for c in body.cases]
    results = await builder.add_test_cases_bulk(dataset_id, cases_data)
    return {"created": len(results), "ids": [r.id for r in results]}


@router.get("/datasets/{dataset_id}/test-cases")
async def list_test_cases(
    dataset_id: str,
    db: AsyncSession = Depends(get_db),
):
    builder = DatasetBuilder(db)
    cases = await builder.get_test_cases(dataset_id)
    return {
        "test_cases": [
            {
                "id": c.id,
                "input_prompt": c.input_prompt[:200],
                "expected_behavior": c.expected_behavior[:200],
                "task_type": c.task_type,
                "difficulty": c.difficulty,
                "tags": c.tags,
            }
            for c in cases
        ]
    }


@router.patch("/test-cases/{test_case_id}")
async def update_test_case(
    test_case_id: str,
    body: UpdateTestCaseRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    builder = DatasetBuilder(db)
    updates = body.model_dump(exclude_none=True)
    tc = await builder.update_test_case(test_case_id, **updates)
    if not tc:
        raise HTTPException(404, "Test case not found")
    return {"id": tc.id, "updated": True}


@router.delete("/test-cases/{test_case_id}")
async def delete_test_case(
    test_case_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    builder = DatasetBuilder(db)
    deleted = await builder.delete_test_case(test_case_id)
    if not deleted:
        raise HTTPException(404, "Test case not found")
    return {"deleted": True}


# ── Eval run endpoints ──────────────────────────────────────────────────


@router.post("/runs")
async def run_evaluation(
    body: RunEvaluationRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    runner = EvaluationRunner(db)
    try:
        eval_run = await runner.run_evaluation(
            dataset_id=body.dataset_id,
            model_name=body.model_name,
            system_prompt=body.system_prompt,
            temperature=body.temperature,
        )
    except ValueError as e:
        raise HTTPException(404, str(e))
    return {
        "id": eval_run.id,
        "status": eval_run.status,
        "model_name": eval_run.model_name,
        "aggregate_score": eval_run.aggregate_score,
        "scores_by_category": eval_run.scores_by_category,
        "started_at": eval_run.started_at.isoformat() if eval_run.started_at else None,
        "completed_at": (eval_run.completed_at.isoformat() if eval_run.completed_at else None),
    }


@router.post("/compare")
async def compare_models(
    body: CompareModelsRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    runner = EvaluationRunner(db)
    try:
        result = await runner.compare_models(
            dataset_id=body.dataset_id,
            model_a=body.model_a,
            model_b=body.model_b,
            system_prompt=body.system_prompt,
        )
    except ValueError as e:
        raise HTTPException(404, str(e))
    return result


@router.get("/runs")
async def list_runs(
    dataset_id: str | None = None,
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
):
    runner = EvaluationRunner(db)
    runs = await runner.list_runs(dataset_id=dataset_id, limit=limit)
    return {
        "runs": [
            {
                "id": r.id,
                "dataset_id": r.dataset_id,
                "model_name": r.model_name,
                "status": r.status,
                "aggregate_score": r.aggregate_score,
                "scores_by_category": r.scores_by_category,
                "started_at": r.started_at.isoformat() if r.started_at else None,
                "completed_at": r.completed_at.isoformat() if r.completed_at else None,
            }
            for r in runs
        ]
    }


@router.get("/runs/{run_id}")
async def get_run(
    run_id: str,
    db: AsyncSession = Depends(get_db),
):
    runner = EvaluationRunner(db)
    run = await runner.get_run(run_id)
    if not run:
        raise HTTPException(404, "Eval run not found")
    return {
        "id": run.id,
        "dataset_id": run.dataset_id,
        "model_name": run.model_name,
        "model_config_hash": run.model_config_hash,
        "status": run.status,
        "aggregate_score": run.aggregate_score,
        "scores_by_category": run.scores_by_category,
        "per_case_scores": run.per_case_scores,
        "langfuse_trace_id": run.langfuse_trace_id,
        "error_message": run.error_message,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
    }


# ── Import endpoint ─────────────────────────────────────────────────────


@router.post("/import/langfuse")
async def import_from_langfuse(
    body: ImportLangfuseRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("admin")),
):
    builder = DatasetBuilder(db)
    ds = await builder.import_from_langfuse_traces(
        dataset_name=body.dataset_name,
        traces=body.traces,
        category=body.category,
    )
    return {"id": ds.id, "name": ds.name, "imported_count": len(body.traces)}


# ── Regression detection ────────────────────────────────────────────────


@router.get("/regressions")
async def detect_regressions(
    model_name: str | None = None,
    dataset_id: str | None = None,
    threshold: float = 0.5,
    limit: int = 10,
    db: AsyncSession = Depends(get_db),
):
    """Detect quality regressions by comparing recent eval runs for the same model+dataset."""
    from app.models.evaluation_models import EvalRun as EvalRunModel

    limit = max(1, min(limit, 100))

    # Get completed runs ordered by creation date
    stmt = (
        select(EvalRunModel)
        .where(EvalRunModel.status == "completed")
        .order_by(EvalRunModel.created_at.desc())
        .limit(limit * 3)  # fetch extra to find pairs
    )
    if model_name:
        stmt = stmt.where(EvalRunModel.model_name == model_name)
    if dataset_id:
        stmt = stmt.where(EvalRunModel.dataset_id == dataset_id)

    result = await db.execute(stmt)
    runs = list(result.scalars().all())

    # Group by model+dataset and find consecutive pairs
    from collections import defaultdict

    grouped: dict[str, list] = defaultdict(list)
    for run in runs:
        key = f"{run.model_name}:{run.dataset_id}"
        grouped[key].append(run)

    regressions = []
    for group_runs in grouped.values():
        # Sort oldest first
        group_runs.sort(key=lambda r: r.created_at or datetime.min.replace(tzinfo=UTC))
        for i in range(1, len(group_runs)):
            prev = group_runs[i - 1]
            curr = group_runs[i]
            prev_score = prev.aggregate_score or 0.0
            curr_score = curr.aggregate_score or 0.0
            delta = curr_score - prev_score
            if delta < -threshold:
                regressions.append(
                    {
                        "model_name": curr.model_name,
                        "dataset_id": curr.dataset_id,
                        "current_run_id": curr.id,
                        "previous_run_id": prev.id,
                        "current_score": curr_score,
                        "previous_score": prev_score,
                        "delta": round(delta, 2),
                        "detected_at": (curr.completed_at.isoformat() if curr.completed_at else None),
                        "category_deltas": _compute_category_deltas(
                            prev.scores_by_category or {},
                            curr.scores_by_category or {},
                        ),
                    }
                )

    # Sort by severity (largest drop first)
    regressions.sort(key=lambda r: r["delta"])
    return {
        "regressions": regressions[:limit],
        "total_found": len(regressions),
        "threshold": threshold,
    }


def _compute_category_deltas(
    prev_scores: dict[str, float], curr_scores: dict[str, float]
) -> dict[str, dict[str, float]]:
    """Compute per-category score deltas between two runs."""
    deltas = {}
    all_categories = set(prev_scores.keys()) | set(curr_scores.keys())
    for cat in all_categories:
        p = prev_scores.get(cat, 0.0)
        c = curr_scores.get(cat, 0.0)
        deltas[cat] = {"previous": p, "current": c, "delta": round(c - p, 2)}
    return deltas


@router.get("/stats")
async def eval_stats(
    model_name: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    """Get aggregate evaluation statistics."""
    from sqlalchemy import func

    from app.models.evaluation_models import EvalRun as EvalRunModel

    stmt = select(
        func.count(EvalRunModel.id).label("total_runs"),
        func.count(EvalRunModel.id).filter(EvalRunModel.status == "completed").label("completed_runs"),
        func.count(EvalRunModel.id).filter(EvalRunModel.status == "failed").label("failed_runs"),
        func.avg(EvalRunModel.aggregate_score).label("avg_score"),
        func.min(EvalRunModel.aggregate_score).label("min_score"),
        func.max(EvalRunModel.aggregate_score).label("max_score"),
    )
    if model_name:
        stmt = stmt.where(EvalRunModel.model_name == model_name)

    result = await db.execute(stmt)
    row = result.one()
    return {
        "total_runs": row.total_runs or 0,
        "completed_runs": row.completed_runs or 0,
        "failed_runs": row.failed_runs or 0,
        "avg_score": round(row.avg_score, 2) if row.avg_score else None,
        "min_score": round(row.min_score, 2) if row.min_score else None,
        "max_score": round(row.max_score, 2) if row.max_score else None,
    }


# ── Templates ───────────────────────────────────────────────────────────


EVAL_TEMPLATES: list[dict[str, Any]] = [
    {
        "id": "code-review",
        "name": "Code Review",
        "category": "code",
        "description": "Evaluate code quality, correctness, and adherence to best practices",
        "default_rubric": {
            "criteria": {
                "correctness": {
                    "weight": 0.30,
                    "description": "Code produces correct output for all cases",
                },
                "readability": {
                    "weight": 0.25,
                    "description": "Clear naming, structure, and comments",
                },
                "efficiency": {
                    "weight": 0.20,
                    "description": "Appropriate time/space complexity",
                },
                "safety": {
                    "weight": 0.15,
                    "description": "No security vulnerabilities or unsafe patterns",
                },
                "style": {
                    "weight": 0.10,
                    "description": "Follows language conventions and project standards",
                },
            },
            "scale": {"min": 1, "max": 5},
        },
        "sample_cases": [
            {
                "input_prompt": "Review this Python function for bugs and improvements:\n\ndef find_duplicates(lst):\n    duplicates = []\n    for i in range(len(lst)):\n        for j in range(i+1, len(lst)):\n            if lst[i] == lst[j] and lst[i] not in duplicates:\n                duplicates.append(lst[i])\n    return duplicates",
                "expected_behavior": "Identifies O(n²) complexity, suggests set-based approach, notes append is O(n) in loop making it O(n³) worst case",
            },
            {
                "input_prompt": "Review this SQL query for performance issues:\n\nSELECT * FROM users u JOIN orders o ON u.id = o.user_id WHERE u.created_at > '2024-01-01' ORDER BY o.total DESC",
                "expected_behavior": "Notes SELECT *, missing index on created_at, suggests covering index, mentions LIMIT if only top N needed",
            },
        ],
    },
    {
        "id": "rag-qa",
        "name": "RAG Q&A Accuracy",
        "category": "rag",
        "description": "Evaluate retrieval-augmented generation answers for factual accuracy and grounding",
        "default_rubric": {
            "criteria": {
                "groundedness": {
                    "weight": 0.35,
                    "description": "Answer is supported by the provided context",
                },
                "completeness": {
                    "weight": 0.25,
                    "description": "Covers all relevant information from context",
                },
                "relevance": {
                    "weight": 0.25,
                    "description": "Directly answers the question asked",
                },
                "no_hallucination": {
                    "weight": 0.15,
                    "description": "Does not invent information not in the context",
                },
            },
            "scale": {"min": 1, "max": 5},
        },
        "sample_cases": [
            {
                "input_prompt": "Context: The server runs on port 8000 with 4 workers. Memory usage is typically 500MB per worker.\n\nQuestion: How much memory does the server use?",
                "expected_behavior": "States ~2GB total (4 workers × 500MB). Does not add information about CPU, disk, or other resources not mentioned.",
            },
        ],
    },
    {
        "id": "agent-task",
        "name": "Agent Task Completion",
        "category": "agent",
        "description": "Evaluate agent reasoning and task completion quality",
        "default_rubric": {
            "criteria": {
                "task_completion": {
                    "weight": 0.35,
                    "description": "Successfully completes the requested task",
                },
                "reasoning_quality": {
                    "weight": 0.25,
                    "description": "Logical steps, correct diagnosis, sound conclusions",
                },
                "tool_usage": {
                    "weight": 0.20,
                    "description": "Appropriate selection and use of available tools",
                },
                "error_handling": {
                    "weight": 0.20,
                    "description": "Gracefully handles edge cases and failures",
                },
            },
            "scale": {"min": 1, "max": 5},
        },
        "sample_cases": [
            {
                "input_prompt": "A user reports their API returns 500 on POST /api/missions but GET /api/missions works fine. The backend logs show 'IntegrityError: null value in column \"owner_id\"'. Diagnose and fix.",
                "expected_behavior": "Identifies missing owner_id in POST request body. Suggests either: making owner_id optional with default, extracting from auth token, or adding validation with clear error message.",
            },
        ],
    },
    {
        "id": "creative-writing",
        "name": "Creative Writing",
        "category": "creative",
        "description": "Evaluate creative content quality, tone, and audience fit",
        "default_rubric": {
            "criteria": {
                "clarity": {
                    "weight": 0.30,
                    "description": "Message is clear and easy to understand",
                },
                "tone": {
                    "weight": 0.25,
                    "description": "Appropriate tone for the target audience",
                },
                "engagement": {
                    "weight": 0.25,
                    "description": "Compelling and holds reader attention",
                },
                "accuracy": {
                    "weight": 0.20,
                    "description": "Factually correct and consistent",
                },
            },
            "scale": {"min": 1, "max": 5},
        },
        "sample_cases": [
            {
                "input_prompt": "Write a 2-sentence error message for a user whose API key has expired. Professional but helpful tone.",
                "expected_behavior": "States the problem (API key expired), provides clear next step (regenerate in settings). No blame, no jargon.",
            },
        ],
    },
]


@router.get("/templates")
async def list_templates(category: str | None = None):
    """List pre-built evaluation templates."""
    templates = EVAL_TEMPLATES
    if category:
        templates = [t for t in templates if t["category"] == category]
    return {"templates": templates}


@router.get("/templates/{template_id}")
async def get_template(template_id: str):
    """Get a specific evaluation template by ID."""
    for t in EVAL_TEMPLATES:
        if t["id"] == template_id:
            return t
    raise HTTPException(404, f"Template '{template_id}' not found")


@router.post("/templates/{template_id}/create-dataset")
async def create_dataset_from_template(
    template_id: str,
    name: str | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Create a new dataset pre-populated with a template's sample test cases."""
    template = None
    for t in EVAL_TEMPLATES:
        if t["id"] == template_id:
            template = t
            break
    if not template:
        raise HTTPException(404, f"Template '{template_id}' not found")

    builder = DatasetBuilder(db)
    ds = await builder.create_dataset(
        name=name or f"{template['name']} Dataset",
        category=template["category"],  # type: ignore[arg-type]
        description=f"Created from template: {template['name']}",
    )

    cases = [
        {
            "input_prompt": sc["input_prompt"],
            "expected_behavior": sc["expected_behavior"],
            "task_type": f"{template['category']}_generation",
            "difficulty": "medium",
            "tags": [template["category"]],
            "rubric": template["default_rubric"],
        }
        for sc in template.get("sample_cases", [])
    ]
    if cases:
        await builder.add_test_cases_bulk(ds.id, cases)

    return {
        "dataset_id": ds.id,
        "name": ds.name,
        "category": ds.category,
        "test_cases_created": len(cases),
        "rubric": template["default_rubric"],
    }


# ── Benchmarks ──────────────────────────────────────────────────────────


class BenchmarkRequest(BaseModel):
    dataset_id: str
    models: list[str] = Field(..., min_length=1, max_length=10)
    system_prompt: str | None = None
    temperature: float = Field(0.7, ge=0.0, le=2.0)


@router.post("/benchmarks")
async def run_benchmark(
    body: BenchmarkRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("admin")),
):
    """Run a benchmark: evaluate multiple models against the same dataset and return a leaderboard."""
    runner = EvaluationRunner(db)

    results: list[dict[str, Any]] = []
    for model_name in body.models:
        try:
            eval_run = await runner.run_evaluation(
                dataset_id=body.dataset_id,
                model_name=model_name,
                system_prompt=body.system_prompt,
                temperature=body.temperature,
            )
            results.append(
                {
                    "model": model_name,
                    "run_id": eval_run.id,
                    "aggregate_score": eval_run.aggregate_score,
                    "scores_by_category": eval_run.scores_by_category,
                    "status": eval_run.status,
                    "test_cases_evaluated": len(eval_run.per_case_scores or []),
                }
            )
        except ValueError as e:
            results.append(
                {
                    "model": model_name,
                    "status": "error",
                    "error": str(e),
                }
            )

    # Sort by aggregate score descending
    scored = [r for r in results if r.get("aggregate_score") is not None]
    errored = [r for r in results if r.get("aggregate_score") is None]
    scored.sort(key=lambda r: r["aggregate_score"], reverse=True)

    # Add rank
    for i, r in enumerate(scored):
        r["rank"] = i + 1

    leaderboard = scored + errored
    winner = scored[0] if scored else None

    return {
        "leaderboard": leaderboard,
        "winner": winner,
        "models_evaluated": len(results),
        "dataset_id": body.dataset_id,
    }


@router.get("/benchmarks/leaderboard")
async def get_leaderboard(
    dataset_id: str | None = None,
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """Get the leaderboard of best model scores across all benchmark runs."""
    from sqlalchemy import func

    from app.models.evaluation_models import EvalRun as EvalRunModel

    # Get best score per model per dataset
    stmt = (
        select(
            EvalRunModel.model_name,
            EvalRunModel.dataset_id,
            func.max(EvalRunModel.aggregate_score).label("best_score"),
            func.count(EvalRunModel.id).label("run_count"),
        )
        .where(EvalRunModel.status == "completed")
        .where(EvalRunModel.aggregate_score.isnot(None))
        .group_by(EvalRunModel.model_name, EvalRunModel.dataset_id)
        .order_by(func.max(EvalRunModel.aggregate_score).desc())
        .limit(limit)
    )
    if dataset_id:
        stmt = stmt.where(EvalRunModel.dataset_id == dataset_id)

    result = await db.execute(stmt)
    rows = result.all()

    entries = []
    for i, row in enumerate(rows):
        entries.append(
            {
                "rank": i + 1,
                "model_name": row.model_name,
                "dataset_id": row.dataset_id,
                "best_score": round(row.best_score, 2),
                "run_count": row.run_count,
            }
        )

    return {"leaderboard": entries, "total": len(entries)}
