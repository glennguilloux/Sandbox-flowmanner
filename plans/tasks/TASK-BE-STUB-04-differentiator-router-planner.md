# TASK-BE-STUB-04 — Implement Sub-Agent Router and Task Planner Differentiators

## Current State
`/opt/flowmanner/backend/app/tools/differentiators.py`:
- `SubAgentRouterTool.execute()` (line ~400): returns `{"stub": True, "message": "This tool is registered as a stub..."}` 
- `TaskPlannerTool.execute()` (line ~430): same stub pattern

These are the two highest-value P0 differentiator stubs. They are registered as available in the ToolRegistry but have no real implementation.

## Problem
- **CRITICAL**: Agents calling `sub_agent_router` get a "coming soon" stub instead of task routing.
- **CRITICAL**: Agents calling `task_planner` get a "coming soon" stub instead of DAG decomposition.
- Both tools show as available on the frontend progress bar but are non-functional.

## Exact Files
- **Modify:** `/opt/flowmanner/backend/app/tools/differentiators.py` (lines 386-440)
- **Reference:** `/opt/flowmanner/backend/app/services/swarm/orchestrator.py` (agent routing patterns)
- **Reference:** `/opt/flowmanner/backend/app/services/mission_planner.py` (task planning patterns)
- **Reference:** `/opt/flowmanner/backend/app/services/agent_registry_service.py` (agent lookup)

## Exact Implementation Steps

### Sub-Agent Router
1. Use the AgentRegistry to list available agents and their capabilities.
2. Implement LLM-based intent-to-agent matching:
   ```python
   from app.services.agent_registry_service import AgentRegistry
   from app.services.budget_enforcer import get_budget_enforcer
   
   registry = AgentRegistry()
   agents = await registry.search_by_capability(validated.task)
   
   # Use LLM to select best agent
   enforcer = get_budget_enforcer()
   response = await enforcer.call(
       budget=...,
       model_id="deepseek-chat",
       messages=[{
           "role": "system",
           "content": f"Select the best agent for: {validated.task}. Agents: {agents}"
       }]
   )
   ```
3. Return the selected agent ID and routing rationale.

### Task Planner
1. Use the LLM to decompose the objective into subtasks:
   ```python
   prompt = f"Decompose this objective into max {validated.max_steps} subtasks: {validated.objective}"
   response = await enforcer.call(
       budget=...,
       model_id="deepseek-reasoner",  # Reasoning model for planning
       messages=[{"role": "user", "content": prompt}]
   )
   ```
2. Parse the LLM response into a DAG of tasks with dependencies.
3. Return the task list with estimated dependencies.

## Constraints
- Must use BudgetEnforcer.call() for all LLM calls (the only LLM path).
- Must respect budget limits (don't spend 100 tokens planning a 10-token task).
- Router must return results within 5 seconds.

## Verification
```bash
cd /opt/flowmanner/backend
# Unit test the router
python -c "
from app.tools.differentiators import SubAgentRouterTool
import asyncio
async def test():
    tool = SubAgentRouterTool()
    result = await tool.execute({
        'action': 'route', 'task': 'Write a blog post about AI',
        'available_agents': ['content-creator', 'seo-specialist']
    })
    assert result.success
    assert not result.result.get('stub')
    print('Router result:', result.result)
asyncio.run(test())
"

# Unit test the planner
python -c "
from app.tools.differentiators import TaskPlannerTool
import asyncio
async def test():
    tool = TaskPlannerTool()
    result = await tool.execute({
        'objective': 'Build a landing page for a SaaS product',
        'max_steps': 5
    })
    assert result.success
    assert not result.result.get('stub')
    print('Plan tasks:', len(result.result.get('tasks', [])))
asyncio.run(test())
"
```
