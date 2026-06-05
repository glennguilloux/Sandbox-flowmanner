"""Unit tests for the DAG executor service."""

from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.services.dag_executor import (
    _has_cycle,
    get_downstream,
    get_ready_tasks,
    topological_sort,
    validate_dag,
)


def _task(
    task_id: str | None = None, deps: list[str] | None = None, status: str = "pending"
):
    """Create a mock MissionTask-like object."""
    return SimpleNamespace(
        id=task_id or str(uuid4()),
        title=f"Task-{(task_id or 'unknown')[:8]}",
        status=status,
        dependencies={"depends_on": deps} if deps else {},
    )


class TestTopologicalSort:
    def test_empty(self):
        assert topological_sort([]) == []

    def test_single_task(self):
        t = _task()
        layers = topological_sort([t])
        assert layers == [[str(t.id)]]

    def test_linear_chain(self):
        """A -> B -> C"""
        a = _task("a")
        b = _task("b", deps=["a"])
        c = _task("c", deps=["b"])
        layers = topological_sort([a, b, c])
        assert layers[0] == ["a"]
        assert layers[1] == ["b"]
        assert layers[2] == ["c"]

    def test_parallel_tasks(self):
        """A -> {B, C} -> D"""
        a = _task("a")
        b = _task("b", deps=["a"])
        c = _task("c", deps=["a"])
        d = _task("d", deps=["b", "c"])
        layers = topological_sort([a, b, c, d])
        assert layers[0] == ["a"]
        assert set(layers[1]) == {"b", "c"}
        assert layers[2] == ["d"]

    def test_independent_tasks(self):
        """A, B, C (no deps) — all in layer 0"""
        a = _task("a")
        b = _task("b")
        c = _task("c")
        layers = topological_sort([a, b, c])
        assert len(layers) == 1
        assert set(layers[0]) == {"a", "b", "c"}


class TestCycleDetection:
    def test_simple_cycle(self):
        """A -> B -> A"""
        a = _task("a", deps=["b"])
        b = _task("b", deps=["a"])
        with pytest.raises(ValueError, match="cycle"):
            topological_sort([a, b])

    def test_three_node_cycle(self):
        """A -> B -> C -> A"""
        a = _task("a", deps=["c"])
        b = _task("b", deps=["a"])
        c = _task("c", deps=["b"])
        with pytest.raises(ValueError, match="cycle"):
            topological_sort([a, b, c])

    def test_has_cycle_false(self):
        a = _task("a")
        b = _task("b", deps=["a"])
        assert _has_cycle([a, b]) is False


class TestValidateDag:
    def test_valid_dag(self):
        a = _task("a")
        b = _task("b", deps=["a"])
        errors = validate_dag([a, b])
        assert errors == []

    def test_missing_dependency(self):
        a = _task("a", deps=["nonexistent"])
        errors = validate_dag([a])
        assert len(errors) == 1
        assert "non-existent" in errors[0]

    def test_cycle_error(self):
        a = _task("a", deps=["b"])
        b = _task("b", deps=["a"])
        errors = validate_dag([a, b])
        assert any("cycle" in e for e in errors)


class TestGetDownstream:
    def test_direct_downstream(self):
        a = _task("a")
        b = _task("b", deps=["a"])
        c = _task("c", deps=["a"])
        downstream = get_downstream("a", [a, b, c])
        assert downstream == {"b", "c"}

    def test_transitive_downstream(self):
        a = _task("a")
        b = _task("b", deps=["a"])
        c = _task("c", deps=["b"])
        downstream = get_downstream("a", [a, b, c])
        assert downstream == {"b", "c"}

    def test_no_downstream(self):
        a = _task("a")
        b = _task("b", deps=["a"])
        downstream = get_downstream("b", [a, b])
        assert downstream == set()


class TestGetReadyTasks:
    def test_root_tasks_ready(self):
        a = _task("a")
        b = _task("b", deps=["a"])
        ready = get_ready_tasks([a, b])
        assert ready == ["a"]

    def test_ready_after_completion(self):
        a = _task("a", status="completed")
        b = _task("b", deps=["a"])
        ready = get_ready_tasks([a, b])
        assert ready == ["b"]

    def test_not_ready_pending_dep(self):
        a = _task("a", status="running")
        b = _task("b", deps=["a"])
        ready = get_ready_tasks([a, b])
        assert ready == []

    def test_failed_dep_not_ready(self):
        a = _task("a", status="failed")
        b = _task("b", deps=["a"])
        ready = get_ready_tasks([a, b])
        # b should NOT be ready (dep failed, but get_ready_tasks only checks completed)
        assert ready == []
