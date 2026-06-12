"""DISABLED 2026-06-12 — missing service module.

The original `deepagents_tasks.py` is preserved in `_disabled/` for revival.

To revive this module, you need:
  1. Create `app/services/deepagents_integration.py` exporting
     `get_deepagents_service(llm, backend_type, filesystem_root,
     enable_long_term_memory, interrupt_on=None)` and `is_available()`.
  2. Confirm `Config.DEEPAGENTS_BACKEND_TYPE`, `Config.DEEPAGENTS_FS_ROOT`,
     `Config.DEEPAGENTS_LONG_TERM_MEMORY`, and
     `Config.DEEPAGENTS_HUMAN_IN_LOOP` are set in `app/settings.py`.
  3. If you revive `app.tasks.base_task` first, this module's
     `from app.tasks.base_task import BaseTask` import will resolve.

Until then this stub keeps the celery worker import graph clean.
"""
