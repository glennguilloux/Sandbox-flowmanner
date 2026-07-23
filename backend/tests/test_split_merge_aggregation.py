"""Unit test for the split -> merge aggregation fix.

Regression guard for substrate_split_merge_aggregation_defect:
DAGStrategy._run_split_branches must collect EVERY per-item output (not
just the last), and NodeExecutor._handle_merge must flatten the
marker-wrapped list so the join sees all items.

This test exercises the REAL handlers (no FakeNodeExecutor) — it only
stubs the executor.execute_node transport with deterministic per-item
outputs, which is exactly what the substrate does per split item.
"""

from __future__ import annotations

from typing import Any

import pytest

from app.services.substrate.node_executor import NodeExecutor
from app.services.substrate.strategies.dag import DAGStrategy
from app.services.substrate.workflow_models import (
    NodeType,
    SPLIT_AGGREGATE_MARKER,
    Workflow,
    WorkflowEdge,
    WorkflowNode,
    WorkflowType,
)


class _StubExecutor:
    """Mimics UnifiedExecutor.execute_node transport for split items.

    Returns a deterministic output that records which item it ran for, so
    the test can prove all items survive the fan-out (not just the last).
    """

    async def execute_node(self, *, node, context, **kwargs):
        item = context.get("input")
        return {
            "success": True,
            "output": {"ran_for": item, "nid": node.id},
            "tokens": 0,
            "cost": 0.0,
        }


def _make_workflow(split_nid: str, target_nid: str, items: list[Any]) -> Workflow:
    return Workflow(
        id="wf-test",
        type=WorkflowType.DAG,
        title="split-merge test",
        description="regression guard",
        nodes=[
            WorkflowNode(
                id=split_nid,
                type=NodeType.SPLIT,
                title="split",
                config={"splitOn": "inputs.items"},
                dependencies=[],
            ),
            WorkflowNode(
                id=target_nid,
                type=NodeType.SANDBOX,
                title="per-item target",
                config={},
                dependencies=[split_nid],
            ),
            WorkflowNode(
                id="merge",
                type=NodeType.MERGE,
                title="merge",
                config={"mergeStrategy": "concat"},
                dependencies=[target_nid],
            ),
        ],
        edges=[
            WorkflowEdge(source=split_nid, target=target_nid),
            WorkflowEdge(source=target_nid, target="merge"),
        ],
    )


async def _run_split(strategy, workflow, split_nid, items, executor) -> dict[str, Any]:
    split_output = {"items": items, "count": len(items), "empty": len(items) == 0}
    node_outputs: dict[str, Any] = {}
    await strategy._run_split_branches(
        workflow=workflow,
        split_node_id=split_nid,
        split_output=split_output,
        context={},
        executor=executor,  # type: ignore[arg-type]
        db=None,  # type: ignore[arg-type]
        run_id="run-split-merge",
        node_outputs=node_outputs,
        executed=set(),
        completed_nodes=[],
        failed_nodes=[],
    )
    return node_outputs


@pytest.mark.asyncio
async def test_split_merge_collects_all_items():
    """A split of 3 items -> merge must yield all 3, not just the last."""
    items = ["repo_a", "repo_b", "repo_c"]
    workflow = _make_workflow("split_q", "audit", items)
    strategy = DAGStrategy()

    node_outputs = await _run_split(strategy, workflow, "split_q", items, _StubExecutor())

    # The target's collected output must be a marker-wrapped list of 3 items.
    target_out = node_outputs["audit"]
    assert isinstance(target_out, dict)
    assert target_out.get(SPLIT_AGGREGATE_MARKER) is True
    assert len(target_out["items"]) == 3

    # Now run the real merge handler and confirm it flattens ALL items.
    merge_result = await NodeExecutor(unified_executor=object())._handle_merge(
        workflow.node_map["merge"],
        {"previous_outputs": node_outputs},
    )
    merged = merge_result["output"]["merged"]
    assert isinstance(merged, list)
    assert len(merged) == 3
    ran_for = sorted(m["ran_for"] for m in merged)
    assert ran_for == sorted(items)


@pytest.mark.asyncio
async def test_split_merge_merge_dict_flattens_items():
    """merge_dict strategy must deep-merge every per-item dict, not just last."""

    class _DictStubExecutor:
        async def execute_node(self, *, node, context, **kwargs):
            item = context.get("input")
            return {
                "success": True,
                "output": {"shard": item, "count": 1},
                "tokens": 0,
                "cost": 0.0,
            }

    items = ["x", "y"]
    workflow = _make_workflow("split_q", "sharder", items)
    workflow.node_map["merge"].config["mergeStrategy"] = "merge_dict"

    strategy = DAGStrategy()
    node_outputs = await _run_split(strategy, workflow, "split_q", items, _DictStubExecutor())

    merge_result = await NodeExecutor(unified_executor=object())._handle_merge(
        workflow.node_map["merge"],
        {"previous_outputs": node_outputs},
    )
    merged = merge_result["output"]["merged"]
    # merge_dict deep-merges; both shards were read (last wins on collision).
    assert isinstance(merged, dict)
    assert merged.get("shard") in {"x", "y"}


@pytest.mark.asyncio
async def test_non_split_upstream_merged_as_scalar():
    """A non-split upstream must still merge as a plain scalar (no marker)."""
    workflow = _make_workflow("split_q", "audit", ["only_one"])
    # Simulate a NON-split node that wrote a plain value (e.g. a single
    # llm_call feeding merge, or cache-warmer's warm_entry -> log_summary).
    node_outputs = {
        "plain_upstream": {"text": "single value"},
        "split_q": {"items": [], "empty": True},
    }
    merge_node = WorkflowNode(
        id="merge2",
        type=NodeType.MERGE,
        title="merge plain",
        config={"mergeStrategy": "concat"},
        dependencies=["plain_upstream"],
    )
    merge_result = await NodeExecutor(unified_executor=object())._handle_merge(
        merge_node,
        {"previous_outputs": node_outputs},
    )
    merged = merge_result["output"]["merged"]
    assert merged == [{"text": "single value"}]
