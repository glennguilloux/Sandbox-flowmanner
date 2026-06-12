"""DISABLED 2026-06-12 — transitive `get_llm` import error.

The original `langgraph_tasks.py` is preserved in `_disabled/` for revival.
The original 1-line fix in `app/services/langgraph/tool_converter.py:24`
(changed `app.core.llm_config` → `app.services.langgraph.llm_config`) is
correct and stays; the deeper problem is that `app.services.langgraph.agent`
imports a `get_llm` symbol from `app.services.langgraph.llm_config` that
does not exist (only `LLMManager` class and `get_llm_manager` function do).

To revive this module, you need:
  1. Add `get_llm(...)` to `app/services/langgraph/llm_config.py` — likely
     a thin wrapper around `LLMManager.get(...)` returning a
     `BaseChatModel`. See `app/services/langgraph/agent.py:817` for the
     call shape.
  2. Confirm `app.services.langgraph.tool_handlers.registry.ToolHandlerRegistry`
     still exists and its `execute_tool` / `close_all` signatures match
     the call sites in the original `_disabled/langgraph_tasks.py`.
  3. If you revive `app.tasks.base_task` first, this module's
     `from app.tasks.base_task import BaseTask` import will resolve.

Until then this stub keeps the celery worker import graph clean.
"""
