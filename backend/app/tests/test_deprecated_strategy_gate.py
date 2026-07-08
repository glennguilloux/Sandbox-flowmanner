"""Tests for the deprecated strategy gate (Item #4 from Opus 4.8 Design-QA).

Verifies:
- Deprecated strategies are blocked by default
- STRATEGY_ALLOW_DEPRECATED=True re-enables them
- Non-deprecated strategies are unaffected
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from app.services.substrate.executor import UnifiedExecutor
from app.services.substrate.workflow_models import WorkflowType


class TestDeprecatedStrategyGate:
    """_get_strategy rejects deprecated strategies unless explicitly allowed."""

    def test_meta_blocked_by_default(self):
        executor = UnifiedExecutor()
        with patch("app.config.settings") as mock_settings:
            mock_settings.STRATEGY_ALLOW_DEPRECATED = False
            mock_settings.STRATEGY_EXPERIMENTAL = False
            with pytest.raises(ValueError, match="deprecated"):
                executor._get_strategy(WorkflowType.META)

    def test_swarm_blocked_by_default(self):
        executor = UnifiedExecutor()
        with patch("app.config.settings") as mock_settings:
            mock_settings.STRATEGY_ALLOW_DEPRECATED = False
            mock_settings.STRATEGY_EXPERIMENTAL = False
            with pytest.raises(ValueError, match="deprecated"):
                executor._get_strategy(WorkflowType.SWARM)

    def test_pipeline_blocked_by_default(self):
        executor = UnifiedExecutor()
        with patch("app.config.settings") as mock_settings:
            mock_settings.STRATEGY_ALLOW_DEPRECATED = False
            mock_settings.STRATEGY_EXPERIMENTAL = False
            with pytest.raises(ValueError, match="deprecated"):
                executor._get_strategy(WorkflowType.PIPELINE)

    def test_langgraph_blocked_by_default(self):
        executor = UnifiedExecutor()
        with patch("app.config.settings") as mock_settings:
            mock_settings.STRATEGY_ALLOW_DEPRECATED = False
            mock_settings.STRATEGY_EXPERIMENTAL = False
            with pytest.raises(ValueError, match="deprecated"):
                executor._get_strategy(WorkflowType.LANGGRAPH)

    def test_meta_allowed_when_flag_set(self):
        executor = UnifiedExecutor()
        with patch("app.config.settings") as mock_settings:
            mock_settings.STRATEGY_ALLOW_DEPRECATED = True
            mock_settings.STRATEGY_EXPERIMENTAL = True  # META is also EXPERIMENTAL
            strategy = executor._get_strategy(WorkflowType.META)
            assert strategy is not None

    def test_solo_not_affected(self):
        """Non-deprecated strategies work regardless of the flag."""
        executor = UnifiedExecutor()
        with patch("app.config.settings") as mock_settings:
            mock_settings.STRATEGY_ALLOW_DEPRECATED = False
            mock_settings.STRATEGY_EXPERIMENTAL = False
            strategy = executor._get_strategy(WorkflowType.SOLO)
            assert strategy is not None

    def test_dag_not_affected(self):
        executor = UnifiedExecutor()
        with patch("app.config.settings") as mock_settings:
            mock_settings.STRATEGY_ALLOW_DEPRECATED = False
            mock_settings.STRATEGY_EXPERIMENTAL = False
            strategy = executor._get_strategy(WorkflowType.DAG)
            assert strategy is not None

    def test_graph_not_affected(self):
        executor = UnifiedExecutor()
        with patch("app.config.settings") as mock_settings:
            mock_settings.STRATEGY_ALLOW_DEPRECATED = False
            mock_settings.STRATEGY_EXPERIMENTAL = False
            strategy = executor._get_strategy(WorkflowType.GRAPH)
            assert strategy is not None

    def test_error_message_includes_strategy_name(self):
        executor = UnifiedExecutor()
        with patch("app.config.settings") as mock_settings:
            mock_settings.STRATEGY_ALLOW_DEPRECATED = False
            mock_settings.STRATEGY_EXPERIMENTAL = False
            with pytest.raises(ValueError, match="meta"):
                executor._get_strategy(WorkflowType.META)
