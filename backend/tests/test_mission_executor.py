import os
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

os.environ.setdefault("OPENAI_API_KEY", "sk-test")

pytestmark = pytest.mark.integration


class TestMissionExecutorInterface:
    def test_mission_executor_has_execute_mission(self):
        from app.services.mission_executor import MissionExecutor

        executor = MissionExecutor()
        assert callable(getattr(executor, "execute_mission", None))

    def test_mission_executor_has_plan_mission(self):
        from app.services.mission_executor import MissionExecutor

        executor = MissionExecutor()
        assert callable(getattr(executor, "plan_mission", None))


class TestExecuteLlmErrorPropagation:
    """Verify MissionExecutor's model router integration."""

    def test_mission_executor_has_get_model_router(self):
        from app.services.mission_executor import MissionExecutor

        executor = MissionExecutor()
        assert callable(getattr(executor, "_get_model_router", None))

    def test_mission_executor_has_classify_error(self):
        from app.services.mission_executor import MissionExecutor

        executor = MissionExecutor()
        assert callable(getattr(executor, "_classify_error", None))

    def test_classify_error_returns_error_object(self):
        from app.services.mission_executor import MissionExecutor

        executor = MissionExecutor()
        result = executor._classify_error(Exception("timeout"))
        # _classify_error returns a MissionError subclass, not a string
        assert result is not None
        assert hasattr(result, "message") or hasattr(result, "args")
