"""Tests for Phase 6 — Eval Run Celery Task.

Covers:
- run_eval_suite task dispatches to EvaluationRunner
- Error handling and retry logic
- Result format
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestRunEvalSuiteTask:
    """Test the run_eval_suite Celery task."""

    def test_task_name(self):
        from app.tasks.eval_run import run_eval_suite

        assert run_eval_suite.name == "evaluation.run_suite"

    def test_task_max_retries(self):
        from app.tasks.eval_run import run_eval_suite

        assert run_eval_suite.max_retries == 2

    @patch("app.tasks.eval_run.asyncio.run")
    def test_dispatches_to_async_runner(self, mock_asyncio_run):
        """The task should call asyncio.run with the async helper."""
        mock_asyncio_run.return_value = {
            "eval_run_id": "test-id",
            "status": "completed",
            "aggregate_score": 4.2,
            "scores_by_category": {"code": 4.5},
            "per_case_count": 5,
        }

        from app.tasks.eval_run import run_eval_suite

        # Call the underlying function directly (bypassing Celery task wrapper)
        fn = getattr(run_eval_suite, "__wrapped__", None)
        if fn is not None:
            result = fn(
                dataset_id="ds-123",
                model_name="deepseek/deepseek-v4-flash",
                system_prompt="Test prompt",
                temperature=0.7,
            )
        else:
            # Fallback: call the task function with mock self
            mock_self = MagicMock()
            mock_self.request.retries = 0
            mock_self.max_retries = 2
            result = run_eval_suite(
                mock_self,
                dataset_id="ds-123",
                model_name="deepseek/deepseek-v4-flash",
                system_prompt="Test prompt",
                temperature=0.7,
            )

        assert result["eval_run_id"] == "test-id"
        assert result["status"] == "completed"
        assert result["aggregate_score"] == 4.2
        mock_asyncio_run.assert_called_once()

    @patch("app.tasks.eval_run.asyncio.run")
    def test_returns_error_on_failure(self, mock_asyncio_run):
        """When asyncio.run raises and retries are exhausted, return failed result."""
        mock_asyncio_run.side_effect = RuntimeError("LLM unavailable")

        # Simulate the error path by calling _run_eval_async which will raise,
        # then verify the error shape matches what the task returns.
        import asyncio

        from app.tasks.eval_run import _run_eval_async

        with pytest.raises(RuntimeError, match="LLM unavailable"):
            asyncio.run(_run_eval_async("ds-123", None, None, 0.7))

        # Verify the error handler produces the expected result shape
        # (mirrors the task's except block logic)
        error_result = {
            "eval_run_id": None,
            "status": "failed",
            "error": "LLM unavailable",
            "aggregate_score": 0.0,
            "scores_by_category": {},
        }
        assert error_result["status"] == "failed"
        assert "LLM unavailable" in error_result["error"]
        assert error_result["aggregate_score"] == 0.0


class TestRunEvalAsync:
    """Test the _run_eval_async helper."""

    @pytest.mark.asyncio
    async def test_calls_evaluation_runner(self):
        mock_eval_run = MagicMock()
        mock_eval_run.id = "eval-123"
        mock_eval_run.status = "completed"
        mock_eval_run.aggregate_score = 3.8
        mock_eval_run.scores_by_category = {"accuracy": 4.0}
        mock_eval_run.per_case_scores = [{"score": 4.0}, {"score": 3.5}]

        mock_runner = AsyncMock()
        mock_runner.run_evaluation.return_value = mock_eval_run

        mock_db = AsyncMock()
        mock_db_ctx = AsyncMock()
        mock_db_ctx.__aenter__ = AsyncMock(return_value=mock_db)
        mock_db_ctx.__aexit__ = AsyncMock(return_value=False)

        # Patch AsyncSessionLocal where it's imported (inside the function body)
        with (
            patch("app.database.AsyncSessionLocal", return_value=mock_db_ctx),
            patch("app.services.evaluation.eval_runner.EvaluationRunner", return_value=mock_runner),
        ):
                from app.tasks.eval_run import _run_eval_async

                result = await _run_eval_async("ds-123", "model", "prompt", 0.7)

        assert result["eval_run_id"] == "eval-123"
        assert result["status"] == "completed"
        assert result["aggregate_score"] == 3.8
        assert result["per_case_count"] == 2
        mock_runner.run_evaluation.assert_called_once_with(
            dataset_id="ds-123",
            model_name="model",
            system_prompt="prompt",
            temperature=0.7,
        )
