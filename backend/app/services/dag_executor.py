"""DAG executor — topological sort and dependency resolution for mission tasks.

Uses Kahn's algorithm. No external dependencies.
"""

from __future__ import annotations

from collections import defaultdict, deque
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models.mission_models import MissionTask


def validate_dag(tasks: list[MissionTask]) -> list[str]:
    """Validate a task DAG. Returns list of error strings (empty = valid).

    Checks:
    - All dependency UUIDs reference existing tasks in this mission
    - No cycles (via Kahn's algorithm)
    """
    errors: list[str] = []
    task_ids = {str(t.id) for t in tasks}

    # Check all dependencies reference existing tasks
    for task in tasks:
        deps = task.dependencies or {}
        for dep_id in deps.get("depends_on", []):
            if dep_id not in task_ids:
                errors.append(f"Task {task.id} depends on non-existent task {dep_id}")

    if errors:
        return errors

    # Check for cycles via Kahn's algorithm
    if _has_cycle(tasks):
        errors.append("DAG contains a cycle")

    return errors


def topological_sort(tasks: list[MissionTask]) -> list[list[str]]:
    """Return execution layers using Kahn's algorithm.

    Layer 0 = tasks with no dependencies (roots).
    Layer N = tasks whose dependencies are all in layers 0..N-1.

    Returns list of layers, each containing task ID strings.
    Raises ValueError if DAG has a cycle.
    """
    if not tasks:
        return []

    task_map = {str(t.id): t for t in tasks}
    task_ids = set(task_map.keys())

    # Build adjacency: dep_id -> [dependent_task_ids]  (who waits for whom)
    in_degree: dict[str, int] = dict.fromkeys(task_ids, 0)
    dependents: dict[str, list[str]] = defaultdict(list)

    for task in tasks:
        deps = task.dependencies or {}
        dep_list = deps.get("depends_on", [])
        # Only count deps that exist in this task set
        valid_deps = [d for d in dep_list if d in task_ids]
        in_degree[str(task.id)] = len(valid_deps)
        for dep_id in valid_deps:
            dependents[dep_id].append(str(task.id))

    # Kahn's: start with zero-in-degree nodes
    queue: deque[str] = deque()
    for tid, deg in in_degree.items():
        if deg == 0:
            queue.append(tid)

    layers: list[list[str]] = []
    visited = 0

    while queue:
        layer = list(queue)
        layers.append(layer)
        next_queue: deque[str] = deque()

        for tid in layer:
            visited += 1
            for dep_tid in dependents[tid]:
                in_degree[dep_tid] -= 1
                if in_degree[dep_tid] == 0:
                    next_queue.append(dep_tid)

        queue = next_queue

    if visited != len(task_ids):
        raise ValueError("DAG contains a cycle")

    return layers


def get_downstream(task_id: str, tasks: list[MissionTask]) -> set[str]:
    """Return all task IDs that transitively depend on task_id."""
    task_map = {str(t.id): t for t in tasks}

    # Build reverse adjacency: dep_id -> [dependent_task_ids]
    dependents: dict[str, list[str]] = defaultdict(list)
    for task in tasks:
        deps = task.dependencies or {}
        for dep_id in deps.get("depends_on", []):
            if dep_id in task_map:
                dependents[dep_id].append(str(task.id))

    # BFS from task_id
    visited: set[str] = set()
    queue: deque[str] = deque(dependents.get(task_id, []))

    while queue:
        tid = queue.popleft()
        if tid in visited:
            continue
        visited.add(tid)
        queue.extend(dependents.get(tid, []))

    return visited


def get_ready_tasks(tasks: list[MissionTask]) -> list[str]:
    """Return task IDs whose dependencies are all completed."""
    task_map = {str(t.id): t for t in tasks}
    task_ids = set(task_map.keys())
    ready: list[str] = []

    for task in tasks:
        if task.status not in ("pending",):
            continue
        deps = task.dependencies or {}
        dep_list = deps.get("depends_on", [])
        valid_deps = [d for d in dep_list if d in task_ids]
        if not valid_deps:
            ready.append(str(task.id))
        else:
            all_done = all(task_map[d].status == "completed" for d in valid_deps)
            if all_done:
                ready.append(str(task.id))

    return ready


def _has_cycle(tasks: list[MissionTask]) -> bool:
    """Check if the task graph has a cycle using DFS."""
    task_ids = {str(t.id) for t in tasks}
    adj: dict[str, list[str]] = defaultdict(list)

    for task in tasks:
        deps = task.dependencies or {}
        for dep_id in deps.get("depends_on", []):
            if dep_id in task_ids:
                adj[str(task.id)].append(dep_id)

    WHITE, GRAY, BLACK = 0, 1, 2
    color: dict[str, int] = dict.fromkeys(task_ids, WHITE)

    def dfs(node: str) -> bool:
        color[node] = GRAY
        for neighbor in adj[node]:
            if color[neighbor] == GRAY:
                return True
            if color[neighbor] == WHITE and dfs(neighbor):
                return True
        color[node] = BLACK
        return False

    return any(color[tid] == WHITE and dfs(tid) for tid in task_ids)
