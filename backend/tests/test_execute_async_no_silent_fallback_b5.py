"""Phase 3.5 cutover — B5 regression tests.

B5: ``backend/app/services/run_service.py::RunService.execute_async``
silently swallows Celery dispatch failures by falling back to
``asyncio.create_task(...)``.

```python
try:
    from app.tasks.mission_execution import dispatch_mission_execution
    dispatch_mission_execution(str(run.id), user_id)
except Exception:
    logger.warning("Celery dispatch failed for run %s, using background task", run_id)
    import asyncio
    async def _run():
        ...
    asyncio.create_task(_run())
return run
```

If Celery/RabbitMQ is down, the function returns a run that lives ONLY
in the FastAPI worker's asyncio task. When that worker exits or recycles,
the run is orphaned with no retry queue. The user sees "queued" forever.

FIX (per ``plans/blueprint-run-phase3.5-cutover-plan.md`` §0 row B5):
When Celery dispatch fails, log at ERROR and re-raise the original
exception. No silent fallback. Operators learn about outages immediately
via Sentry/alerts.

These tests MUST FAIL on the current code.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.services.run_service import RunService


def _make_pending_run(user_id: int = 1):
    """Construct a Run in pending status without touching the DB."""
    from app.models.blueprint_models import Run, RunStatus

    return Run(
        id=str(uuid4()),
        blueprint_id=None,
        workspace_id=None,
        user_id=user_id,
        status=RunStatus.PENDING.value,
        snapshot={"blueprint_type": "solo", "title": "test"},
        input_data={},
        budget_limit_usd=None,
    )


def _make_run_service_with_run(run):
    db = AsyncMock()
    # RunService.get(): db.execute(select(Run).where(Run.id == ...)).scalar_one_or_none()
    result_mock = MagicMock()
    result_mock.scalar_one_or_none = MagicMock(return_value=run)
    db.execute = AsyncMock(return_value=result_mock)
    db.flush = AsyncMock()
    return RunService(db)


@pytest.mark.asyncio
class TestExecuteAsyncNoSilentFallback:
    """Test-first regression for B5.

    Note: only the primary ``pytest.raises`` test remains. We initially
    added a complementary ``asyncio.all_tasks`` count check, but task
    bookkeeping under pytest-asyncio is too fragile (loop instrumentation,
    destroy callbacks) to give a reliable signal. The ``pytest.raises``
    test is sufficient — a fix that does not raise is fixing the bug.
    """

    async def test_execute_async_raises_when_celery_dispatch_fails(self):
        """FIX: run_service.execute_async must RERAISE Celery dispatch
        failures, not silently spawn an asyncio.create_task fallback.

        Currently the except-branch swallows the error, sets run.status,
        schedules asyncio.create_task, and returns the run. After the
        fix, the original RuntimeError must propagate.
        """
        pending_run = _make_pending_run(user_id=1)
        svc = _make_run_service_with_run(pending_run)

        with (
            patch(
                "app.tasks.mission_execution.dispatch_mission_execution",
                side_effect=RuntimeError("celery queue unreachable"),
            ),
            pytest.raises(RuntimeError, match="celery queue unreachable"),
        ):
            await svc.execute_async(str(pending_run.id), 1)

    async def test_execute_async_does_not_call_create_task_on_failure(self):
        """Anti-regression guard: ``asyncio.create_task`` must NOT be
        scheduled when Celery dispatch fails. Use a direct spy on the
        call so the signal is deterministic (no asyncio.all_tasks
        bookkeeping fragility).
        """
        import asyncio

        pending_run = _make_pending_run(user_id=1)
        svc = _make_run_service_with_run(pending_run)

        with (
            patch(
                "app.tasks.mission_execution.dispatch_mission_execution",
                side_effect=RuntimeError("celery queue unreachable"),
            ),
            patch("asyncio.create_task", wraps=asyncio.create_task) as create_task_spy,
        ):
            try:
                await svc.execute_async(str(pending_run.id), 1)
            except RuntimeError:
                # After fix: create_task is gone from the except-branch.
                pass

        # No fallback fire-and-forget background task should be scheduled.
        assert create_task_spy.call_count == 0, (
            "B5 FIX MISSING: asyncio.create_task was called "
            f"{create_task_spy.call_count} time(s) as a fallback for "
            "Celery dispatch failure. This orphans the run if the FastAPI "
            "worker recycles. Remove the asyncio.create_task fallback, "
            "log at ERROR, and re-raise the original exception."
        )
