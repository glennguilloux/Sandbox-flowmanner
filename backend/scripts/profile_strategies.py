#!/usr/bin/env python
"""Profile all 7 strategies with identical prompts against the live 27B model.

Run: cd /opt/flowmanner/backend && python scripts/profile_strategies.py

Output: docs/strategy-profiling-results.json
"""

import asyncio
import json
import os
import sys
import time
from uuid import uuid4

# Ensure backend root is in PYTHONPATH
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Override DATABASE_URL to use localhost when running from host (Docker hostname
# "workflow-postgres" only resolves inside the Docker network).
if "workflow-postgres" in os.environ.get("DATABASE_URL", ""):
    os.environ["DATABASE_URL"] = os.environ["DATABASE_URL"].replace("workflow-postgres", "localhost")

from app.database import AsyncSessionLocal
from app.services.substrate.executor import get_unified_executor
from app.services.substrate.workflow_models import (
    NodeType,
    Workflow,
    WorkflowNode,
    WorkflowType,
)

STRATEGIES = [
    WorkflowType.SOLO,
    WorkflowType.DAG,
    WorkflowType.GRAPH,
    WorkflowType.SWARM,
    WorkflowType.PIPELINE,
    WorkflowType.META,
    WorkflowType.LANGGRAPH,
]

TEST_PROMPT = "Say the word 'Ready' and nothing else."


def build_workflow(strategy: WorkflowType) -> Workflow:
    """Build a minimal workflow that satisfies each strategy's validation requirements."""
    nid = lambda: str(uuid4())
    llm_node = lambda title="LLM call": WorkflowNode(
        id=nid(),
        type=NodeType.LLM_CALL,
        title=title,
        config={"prompt": TEST_PROMPT},
    )

    if strategy == WorkflowType.SOLO:
        nodes = [llm_node()]

    elif strategy == WorkflowType.DAG:
        nodes = [llm_node("Step 1"), llm_node("Step 2")]

    elif strategy == WorkflowType.GRAPH:
        nodes = [llm_node("Graph node 1"), llm_node("Graph node 2")]

    elif strategy == WorkflowType.SWARM:
        # Requires FAN_OUT + FAN_IN nodes
        fan_out = WorkflowNode(
            id=nid(),
            type=NodeType.FAN_OUT,
            title="Fan out",
            config={"branches": 2},
        )
        fan_in = WorkflowNode(
            id=nid(),
            type=NodeType.FAN_IN,
            title="Fan in",
            config={},
        )
        nodes = [fan_out, llm_node("Branch A"), llm_node("Branch B"), fan_in]

    elif strategy == WorkflowType.PIPELINE:
        # Requires PHASE_GATE nodes for all 7 phases
        phases = ["dispatch", "research", "draft", "debate", "consensus", "synthesis", "review"]
        nodes = [
            WorkflowNode(
                id=nid(),
                type=NodeType.PHASE_GATE,
                title=f"Phase: {p}",
                config={"phase": p},
            )
            for p in phases
        ]

    elif strategy == WorkflowType.META:
        # Requires SUB_WORKFLOW node
        sub = WorkflowNode(
            id=nid(),
            type=NodeType.SUB_WORKFLOW,
            title="Sub-workflow",
            config={"workflow_type": "solo"},
        )
        nodes = [sub, llm_node("Meta LLM")]

    elif strategy == WorkflowType.LANGGRAPH:
        # Requires graph_name in config
        nodes = [
            WorkflowNode(
                id=nid(),
                type=NodeType.LLM_CALL,
                title="LangGraph node",
                config={"prompt": TEST_PROMPT, "graph_name": "profile_graph"},
            )
        ]

    else:
        nodes = [llm_node()]

    return Workflow(
        id=nid(),
        type=strategy,
        title=f"Profile_{strategy.value}",
        nodes=nodes,
    )


async def profile_strategy(executor, db, strategy: WorkflowType, attempts: int = 3) -> dict:
    """Run a strategy multiple times and collect metrics."""
    successes = 0
    total_latency_ms = 0.0
    total_tokens = 0
    errors = []

    for i in range(attempts):
        workflow = build_workflow(strategy)
        try:
            start = time.monotonic()
            result = await asyncio.wait_for(
                executor.execute(db=db, workflow=workflow),
                timeout=120,
            )
            elapsed_ms = (time.monotonic() - start) * 1000

            latency = result.execution_time_ms or elapsed_ms
            total_latency_ms += latency
            total_tokens += result.total_tokens

            if result.success:
                successes += 1
            else:
                errors.append(result.error or "unknown failure")

        except TimeoutError:
            errors.append("timeout (120s)")
        except Exception as e:
            errors.append(str(e))

    success_rate = successes / attempts
    avg_latency = total_latency_ms / attempts if attempts else 0
    avg_tokens = total_tokens / attempts if attempts else 0

    return {
        "success_rate": round(success_rate, 2),
        "successes": successes,
        "attempts": attempts,
        "avg_latency_ms": round(avg_latency, 1),
        "avg_tokens": round(avg_tokens),
        "total_tokens": total_tokens,
        "errors": errors[:3],  # keep first 3 errors for debugging
    }


async def main():
    executor = get_unified_executor()
    results = {}
    for strategy in STRATEGIES:
        print(f"\n{'='*60}")
        print(f"Profiling: {strategy.value}")
        print(f"{'='*60}")

        # Fresh session per strategy to avoid transaction corruption
        async with AsyncSessionLocal() as db:
            metrics = await profile_strategy(executor, db, strategy, attempts=1)
            results[strategy.value] = metrics

            status = "✅" if metrics["success_rate"] >= 0.67 else "⚠️" if metrics["success_rate"] > 0 else "❌"
            print(f"  {status} Success rate: {metrics['success_rate']*100:.0f}%")
            print(f"     Avg latency: {metrics['avg_latency_ms']:.0f}ms")
            print(f"     Avg tokens: {metrics['avg_tokens']}")
            if metrics["errors"]:
                print(f"     Errors: {metrics['errors']}")

    # Summary
    print(f"\n{'='*60}")
    print("SUMMARY")
    print(f"{'='*60}")
    for name, m in results.items():
        status = "✅" if m["success_rate"] >= 0.67 else "⚠️" if m["success_rate"] > 0 else "❌"
        print(
            f"  {status} {name:12s}  {m['success_rate']*100:5.0f}%  {m['avg_latency_ms']:8.0f}ms  {m['avg_tokens']:6d} tok"
        )

    # Save results
    output = {
        "timestamp": time.time(),
        "model": "Qwen3.6-27B-Q5_K_M-mtp",
        "attempts_per_strategy": 1,
        "results": results,
    }

    output_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "docs",
        "strategy-profiling-results.json",
    )
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(output, f, indent=2)
    print(f"\nResults saved to {output_path}")


if __name__ == "__main__":
    asyncio.run(main())
