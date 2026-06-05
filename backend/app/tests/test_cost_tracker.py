"""Unit tests for app/services/cost_tracker.py — CostTracker."""

import os
from unittest.mock import MagicMock, patch

import pytest

os.environ.setdefault("OPENAI_API_KEY", "sk-test")


class TestEstimateCost:
    """CostTracker.estimate_cost: correct cost computation."""

    def test_deepseek_chat_cost(self):
        from app.services.cost_tracker import CostTracker

        tracker = CostTracker()
        cost = tracker.estimate_cost("deepseek-chat", 1_000_000)
        assert abs(cost - 0.14) < 0.01

    def test_deepseek_reasoner_cost(self):
        from app.services.cost_tracker import CostTracker

        tracker = CostTracker()
        cost = tracker.estimate_cost("deepseek-reasoner", 1_000_000)
        assert abs(cost - 0.55) < 0.01

    def test_claude_sonnet_cost(self):
        from app.services.cost_tracker import CostTracker

        tracker = CostTracker()
        cost = tracker.estimate_cost("claude-3-5-sonnet", 1_000_000)
        assert abs(cost - 3.0) < 0.01

    def test_claude_haiku_cost(self):
        from app.services.cost_tracker import CostTracker

        tracker = CostTracker()
        cost = tracker.estimate_cost("claude-3-haiku", 1_000_000)
        assert abs(cost - 0.25) < 0.01

    def test_free_model_cost_is_zero(self):
        from app.services.cost_tracker import CostTracker

        tracker = CostTracker()
        cost = tracker.estimate_cost("vllm-qwen3-14b-chat", 1_000_000)
        assert cost == 0.0

    def test_free_openrouter_cost_is_zero(self):
        from app.services.cost_tracker import CostTracker

        tracker = CostTracker()
        cost = tracker.estimate_cost("openrouter-gemma-2-9b-free", 1_000_000)
        assert cost == 0.0

    def test_unknown_model_uses_default(self):
        from app.services.cost_tracker import CostTracker

        tracker = CostTracker()
        cost = tracker.estimate_cost("some-unknown-model", 1_000_000)
        assert abs(cost - 0.5) < 0.01

    def test_proportional_token_count(self):
        from app.services.cost_tracker import CostTracker

        tracker = CostTracker()
        cost_500k = tracker.estimate_cost("deepseek-chat", 500_000)
        cost_1m = tracker.estimate_cost("deepseek-chat", 1_000_000)
        assert abs(cost_1m - 2 * cost_500k) < 0.001

    def test_zero_tokens(self):
        from app.services.cost_tracker import CostTracker

        tracker = CostTracker()
        cost = tracker.estimate_cost("deepseek-chat", 0)
        assert cost == 0.0


class TestRecordLlmCall:
    """CostTracker.record_llm_call: DB persistence and Prometheus metrics."""

    @pytest.mark.asyncio
    async def test_records_to_db_when_db_provided(self):
        from app.services.cost_tracker import CostTracker

        tracker = CostTracker()
        mock_db = MagicMock()
        mock_db.add = MagicMock()

        await tracker.record_llm_call(
            db=mock_db,
            mission_id="mission-1",
            task_id="task-1",
            model_id="deepseek-chat",
            provider="deepseek",
            prompt_tokens=100,
            completion_tokens=50,
            cost_usd=0.001,
            latency_ms=200,
            success=True,
        )

        mock_db.add.assert_called_once()

    @pytest.mark.asyncio
    async def test_skips_db_when_db_is_none(self):
        from app.services.cost_tracker import CostTracker

        tracker = CostTracker()

        # Should not raise
        await tracker.record_llm_call(
            db=None,
            mission_id="mission-1",
            task_id="task-1",
            model_id="deepseek-chat",
            provider="deepseek",
            prompt_tokens=100,
            completion_tokens=50,
            cost_usd=0.001,
            latency_ms=200,
            success=True,
        )

    @pytest.mark.asyncio
    async def test_records_error_message_on_failure(self):
        from app.services.cost_tracker import CostTracker

        tracker = CostTracker()
        mock_db = MagicMock()
        mock_db.add = MagicMock()

        await tracker.record_llm_call(
            db=mock_db,
            mission_id="mission-1",
            task_id=None,
            model_id="deepseek-chat",
            provider="deepseek",
            prompt_tokens=0,
            completion_tokens=0,
            cost_usd=0.0,
            latency_ms=500,
            success=False,
            error_message="Connection refused",
        )

        mock_db.add.assert_called_once()
        # Verify the record has the error message
        record = mock_db.add.call_args[0][0]
        assert record.error_message == "Connection refused"
        assert record.success is False

    @pytest.mark.asyncio
    async def test_survives_db_add_failure(self):
        from app.services.cost_tracker import CostTracker

        tracker = CostTracker()
        mock_db = MagicMock()
        mock_db.add = MagicMock(side_effect=RuntimeError("DB down"))

        # Should not raise — error is caught and logged
        await tracker.record_llm_call(
            db=mock_db,
            mission_id="mission-1",
            task_id="task-1",
            model_id="deepseek-chat",
            provider="deepseek",
            prompt_tokens=100,
            completion_tokens=50,
            cost_usd=0.001,
            latency_ms=200,
            success=True,
        )

    @pytest.mark.asyncio
    async def test_survives_prometheus_failure(self):
        """Prometheus recording failure should not propagate."""
        from app.services.cost_tracker import CostTracker

        tracker = CostTracker()

        with patch(
            "app.services.cost_tracker.record_llm_request",
            side_effect=RuntimeError("metrics down"),
        ):
            # Should not raise
            await tracker.record_llm_call(
                db=None,
                mission_id="mission-1",
                task_id="task-1",
                model_id="deepseek-chat",
                provider="deepseek",
                prompt_tokens=100,
                completion_tokens=50,
                cost_usd=0.001,
                latency_ms=200,
                success=True,
            )

    @pytest.mark.asyncio
    async def test_records_none_mission_and_task_ids(self):
        from app.services.cost_tracker import CostTracker

        tracker = CostTracker()
        mock_db = MagicMock()
        mock_db.add = MagicMock()

        await tracker.record_llm_call(
            db=mock_db,
            mission_id=None,
            task_id=None,
            model_id="deepseek-chat",
            provider="deepseek",
            prompt_tokens=10,
            completion_tokens=5,
            cost_usd=0.0001,
            latency_ms=100,
            success=True,
        )

        mock_db.add.assert_called_once()
        record = mock_db.add.call_args[0][0]
        assert record.mission_id is None
        assert record.task_id is None


class TestCostPer1MTokens:
    """CostTracker.COST_PER_1M_TOKENS: verify the pricing table."""

    def test_all_keys_are_strings(self):
        from app.services.cost_tracker import CostTracker

        for key in CostTracker.COST_PER_1M_TOKENS:
            assert isinstance(key, str)

    def test_default_key_exists(self):
        from app.services.cost_tracker import CostTracker

        assert "default" in CostTracker.COST_PER_1M_TOKENS

    def test_all_values_are_numbers(self):
        from app.services.cost_tracker import CostTracker

        for val in CostTracker.COST_PER_1M_TOKENS.values():
            assert isinstance(val, (int, float))
