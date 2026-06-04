# TASK-BE-STUB-11 — Add Structured Error Logging to All Silent pass Exception Handlers

## Current State
Across the backend, 40+ `pass` statements in exception handlers silently swallow errors. Critical examples:
- `mission_cache.py`: 7 `pass` in cache operations
- `task_executor.py`: multiple `pass` in tool execution failures
- `mission_planner.py`: `pass` in planning errors
- `llm_router.py`: `pass` in usage logging failures
- `browser_agent.py`: 3 `pass` in browser execution paths
- `trigger_service.py`: 3 `pass` in trigger processing
- `graph_executor.py`: 2 `pass` in graph execution
- `cost_tracker.py`: `pass` in LLM call record failure
- `webhook_handler/signature.py`: `pass` in signature verification
- `rag/embedding_service.py`, `chunking_service.py`, `prompt_synthesizer.py`: `pass` in RAG pipeline

## Problem
- **MEDIUM**: Failures in tool execution, caching, planning, cost tracking, and RAG produce zero logs. Debugging requires code instrumentation.
- Users see silent failures: tasks fail with no error message, cache misses with no indication, costs silently unrecorded.

## Exact Files (all in `/opt/flowmanner/backend/app/`)
- `services/mission_cache.py` (lines 121, 142, 167, 192, 217, 242, 282)
- `services/task_executor.py` (lines 641, 643, 720)
- `services/mission_planner.py` (lines 467, 472)
- `services/llm_router.py` (line 314)
- `services/browser_agent.py` (lines 358, 391, 431)
- `services/trigger_service.py` (lines 136, 180, 232)
- `services/graph_executor.py` (lines 291, 293)
- `services/cost_tracker.py` (line 131)
- `services/webhook_handler/signature.py` (lines 27, 32)
- `services/rag/embedding_service.py` (lines 46, 58)
- `services/rag/chunking_service.py` (line 146)
- `services/rag/prompt_synthesizer.py` (line 164)
- `services/langgraph/agent_goals.py` (line 242)

## Exact Implementation Steps
Replace every `pass` in an exception handler with:
```python
except Exception as e:
    logger.error(
        "Operation failed: %s in %s: %s",
        "cache_get" if appropriate else "unknown",
        __name__,
        str(e),
        exc_info=True
    )
```
For **cache operations**: Log the key, operation type, and error.
For **tool execution**: Log the tool_id, task_id, error message, and stack trace.
For **planning**: Log the mission_id, plan context, and error.
For **cost tracking**: Log the model_id, token count, and error.

Use structured logging format consistently:
```python
logger.error(
    "tool_execution_failed",
    extra={"tool_id": tool_id, "task_id": task_id, "error": str(e)}
)
```

## Constraints
- Must not change any function return values or behavior — only add logging.
- Must use the existing `logger` instance (already imported in each file).
- Logged messages must not contain sensitive data (API keys, user PII).

## Verification
```bash
cd /opt/flowmanner/backend
# Count remaining bare pass in except blocks (excluding abstractmethods)
grep -rn "except.*:" app/services/ --include="*.py" -A1 | grep "pass$" | wc -l
# Target: reduce by at least 30 instances
# Run test suite to ensure no behavioral change
python -m pytest app/tests/ -x --tb=short -q
```
