# TASK-BE-STUB-05 — Wire Real LLM Call in BaseDomainAgent.run()

## Current State
`/opt/flowmanner/backend/app/services/domain_agents/base_domain_agent.py:70`:
```python
def run(self, query: str, context=None) -> dict:
    logger.info(f"[{self.domain_name.upper()}] Processing query: {query[:100]}...")
    # Placeholder implementation - override in subclasses for real LLM calls
    result = {
        "domain": self.domain_name,
        "query": query,
        "response": f"[{self.domain_name.upper()}] {query}",  # ECHOES INPUT!
        "metadata": self.metadata,
        "success": True,
    }
    return result
```

## Problem
- **CRITICAL**: All domain-specific AI agents (Legal, Finance, Support, etc.) return an echo of user input instead of a real LLM response.
- Domain agent API routes call this method — they are completely non-functional.
- No subclass overrides `run()` with real LLM calls.

## Exact Files
- **Modify:** `/opt/flowmanner/backend/app/services/domain_agents/base_domain_agent.py` (lines 60-75)
- **Reference:** `/opt/flowmanner/backend/app/services/budget_enforcer.py` (BudgetEnforcer.call)
- **Reference:** `/opt/flowmanner/backend/app/services/business-templates/` (domain-specific templates)
- **Check:** `/opt/flowmanner/backend/app/services/business-templates/legal_template.py`
- **Check:** `/opt/flowmanner/backend/app/services/business-templates/finance_template.py`
- **Check:** `/opt/flowmanner/backend/app/services/business-templates/support_template.py`

## Exact Implementation Steps
1. Convert `run()` to an async method (the base signature must change to `async def run`).
2. Use `BudgetEnforcer.call()` with domain-specific system prompts:
   ```python
   async def run(self, query: str, context=None) -> dict:
       from app.services.budget_enforcer import get_budget_enforcer
       from app.models.capability_models import Budget
       
       enforcer = get_budget_enforcer()
       system_prompt = self.get_system_prompt()
       
       messages = [{"role": "system", "content": system_prompt}]
       if context and context.get("history"):
           messages.extend(context["history"])
       messages.append({"role": "user", "content": query})
       
       response = await enforcer.call(
           budget=Budget(max_cost_usd=1.0),
           model_id=self.model,
           messages=messages,
           temperature=self.temperature,
           max_tokens=self.max_tokens,
       )
       
       return {
           "domain": self.domain_name,
           "query": query,
           "response": response.get("response", ""),
           "metadata": self.metadata,
           "success": response.get("success", False),
       }
   ```
3. Update all callers of `run()` to use `await`.
4. Verify that subclasses (Legal, Finance, Support) override `get_system_prompt()` to return domain-specific system prompts.
5. If subclasses don't exist for all domains, create them using the business-templates.

## Constraints
- Must use BudgetEnforcer.call() — the only LLM call path.
- Must set reasonable budget limits (no unbounded LLM costs per domain agent call).
- Must maintain synchronous-compatible interface OR update all callers.

## Verification
```bash
cd /opt/flowmanner/backend
# Test domain agent returns real LLM response
python -c "
import asyncio
from app.services.domain_agents.base_domain_agent import BaseDomainAgent

class TestAgent(BaseDomainAgent):
    domain_name = 'test'
    def get_system_prompt(self): return 'You are a test agent.'
    def get_tools(self): return []
    def process_response(self, r): return {'response': r}

async def test():
    agent = TestAgent()
    result = await agent.run('What is 2+2?')
    assert result['success']
    assert '4' in result['response'].lower() or 'four' in result['response'].lower()
    print('Agent response:', result['response'][:100])
asyncio.run(test())
"
```
