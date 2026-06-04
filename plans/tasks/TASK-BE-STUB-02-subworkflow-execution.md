# TASK-BE-STUB-02 — Implement Sub-Workflow Recursive Execution

## Current State
`/opt/flowmanner/backend/app/services/substrate/node_executor.py:549`:
```python
async def _handle_sub_workflow(self, db, node, context, budget, run_id):
    sub_workflow_id = node.config.get("workflow_id")
    if not sub_workflow_id:
        return {"success": False, "error": "No workflow_id for sub_workflow node"}
    logger.warning("Sub-workflow %s not yet wired for recursive execution", sub_workflow_id)
    return {
        "success": False,
        "error": f"Sub-workflow execution not yet implemented for {sub_workflow_id}.",
        "tokens": 0,
    }
```

## Problem
Any workflow with a `SUB_WORKFLOW` node type always fails. Complex DAG workflows (multi-step pipelines) are broken. This is a **CRITICAL** deploy blocker.

## Exact Files
- **Modify:** `/opt/flowmanner/backend/app/services/substrate/node_executor.py` (lines 525-555)
- **Reference:** `/opt/flowmanner/backend/app/models/substrate_models.py` (for Workflow model)
- **Reference:** `/opt/flowmanner/backend/app/services/substrate/workflow_models.py` (for Workflow class)

## Exact Implementation Steps
1. Query the sub-workflow from the database:
   ```python
   from sqlalchemy import select
   from app.models.substrate_models import SubstrateWorkflow, SubstrateWorkflowNode

   result = await db.execute(
       select(SubstrateWorkflow).where(SubstrateWorkflow.id == sub_workflow_id)
   )
   sub_workflow = result.scalar_one_or_none()
   if sub_workflow is None:
       return {"success": False, "error": f"Sub-workflow {sub_workflow_id} not found"}
   ```
2. Load sub-workflow nodes:
   ```python
   node_result = await db.execute(
       select(SubstrateWorkflowNode).where(
           SubstrateWorkflowNode.workflow_id == sub_workflow_id
       ).order_by(SubstrateWorkflowNode.order_index)
   )
   sub_nodes = node_result.scalars().all()
   ```
3. Convert DB models to `WorkflowNode` objects using the adapter pattern from `adapters.py`.
4. Create a children `Workflow` object and call the executor recursively:
   ```python
   from app.services.substrate.workflow_models import Workflow
   child_workflow = Workflow(
       id=sub_workflow_id,
       name=sub_workflow.name,
       nodes=converted_nodes,
       user_id=sub_workflow.user_id,
   )
   result = await self.executor.execute(db, child_workflow)
   ```
5. Return the sub-workflow execution result, adjusted for the parent node context.

## Constraints
- Must share the parent's `budget` across sub-workflow execution.
- Must handle recursion depth limits (max depth: 5) to prevent infinite loops.
- Must propagate abort signals to sub-workflows.

## Verification
```bash
# Create a test workflow with a SUB_WORKFLOW node and execute it
cd /opt/flowmanner/backend
python -c "
import asyncio
from app.database import AsyncSessionLocal
from app.services.substrate.executor import get_unified_executor
from app.services.substrate.workflow_models import Workflow, WorkflowNode, NodeType
from app.models.capability_models import Budget

async def test():
    async with AsyncSessionLocal() as db:
        executor = get_unified_executor()
        workflow = Workflow(id='test-sub', nodes=[
            WorkflowNode(id='n1', type=NodeType.SUB_WORKFLOW,
                        config={'workflow_id': 'child-workflow-id'})
        ])
        budget = Budget(max_cost_usd=5.0)
        result = await executor.execute(db, workflow)
        print('Sub-workflow result:', result)
asyncio.run(test())
"
```
