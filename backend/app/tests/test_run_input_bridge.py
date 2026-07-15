"""Q1 regression test — run.input_data must reach the executor context.

RunService.execute() builds a `context` dict and passes it to
UnifiedExecutor.execute(). The context's "inputs" key must hold
run.input_data so downstream blueprints can interpolate {{ inputs.* }} tokens.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from app.services.run_service import RunService


async def test_execute_bridges_input_data_into_context():
    run = MagicMock()
    run.id = "run-1"
    run.status = "pending"
    run.input_data = {"repo_url": "https://github.com/x/y", "prior_clues_url": "https://x/y/clues"}
    run.blueprint_id = None
    run.snapshot = {}
    run.output_data = None

    result = MagicMock()
    result.status = "completed"
    result.total_tokens = 0
    result.total_cost_usd = 0.0
    result.error = None
    result.data = None

    captured: dict = {}

    async def fake_execute(db, workflow, run_id, blueprint_id=None, context=None):
        captured["context"] = context
        return result

    executor = MagicMock()
    executor.execute = fake_execute

    db = MagicMock()
    db.flush = AsyncMock()

    service = RunService(db=db)
    service.get = AsyncMock(return_value=run)

    with patch(
        "app.services.run_service.get_unified_executor", return_value=executor
    ), patch(
        "app.services.run_service.blueprint_to_workflow", return_value=MagicMock()
    ):
        await service.execute(run_id="run-1", user_id=1)

    assert captured["context"]["inputs"] == run.input_data


async def test_execute_defaults_empty_input_data_to_empty_dict():
    run = MagicMock()
    run.id = "run-2"
    run.status = "pending"
    run.input_data = None
    run.blueprint_id = None
    run.snapshot = {}
    run.output_data = None

    result = MagicMock()
    result.status = "completed"
    result.total_tokens = 0
    result.total_cost_usd = 0.0
    result.error = None
    result.data = None

    captured: dict = {}

    async def fake_execute(db, workflow, run_id, blueprint_id=None, context=None):
        captured["context"] = context
        return result

    executor = MagicMock()
    executor.execute = fake_execute

    db = MagicMock()
    db.flush = AsyncMock()

    service = RunService(db=db)
    service.get = AsyncMock(return_value=run)

    with patch(
        "app.services.run_service.get_unified_executor", return_value=executor
    ), patch(
        "app.services.run_service.blueprint_to_workflow", return_value=MagicMock()
    ):
        await service.execute(run_id="run-2", user_id=1)

    assert captured["context"]["inputs"] == {}
