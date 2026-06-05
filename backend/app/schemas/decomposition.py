"""Pydantic schemas for mission decomposition and DAG execution."""

from __future__ import annotations

from pydantic import BaseModel


class TaskDecomposition(BaseModel):
    title: str
    description: str = ""
    task_type: str = "general"
    depends_on: list[int] = []  # indices into the tasks list
    assigned_model: str | None = None


class DecomposeRequest(BaseModel):
    mode: str = "manual"
    tasks: list[TaskDecomposition] | None = None


class DAGNode(BaseModel):
    id: str
    title: str
    status: str
    dependencies: list[str]


class DAGResponse(BaseModel):
    nodes: list[DAGNode]
    edges: list[dict]  # {from: str, to: str}


class ExecuteDAGResponse(BaseModel):
    completed: int
    failed: int
    skipped: int
    errors: list[str]
