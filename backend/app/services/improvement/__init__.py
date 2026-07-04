"""
Autonomous Self-Improvement System — Slim Version.

Phases 1–3 (failure_types, causal_decomposer, hypothesis testing) have
been pruned.  They were never wired into production — 107 missions ran
with zero improvement data recorded.  Total pruned: ~1,875 LOC.

What remains:
- Dispatch layer (improvement_loop_v2): background review Celery task
"""

import logging

logger = logging.getLogger(__name__)

# Dispatch layer — background review Celery task
try:
    from .improvement_loop_v2 import (
        ImprovementLoopV2,
        get_improvement_loop,
        initialize_improvement_loop,
    )
except ImportError as e:
    logger.warning("Failed to import improvement_loop_v2: %s", e)
    ImprovementLoopV2 = None  # type: ignore[misc]
    get_improvement_loop = None  # type: ignore[misc]
    initialize_improvement_loop = None  # type: ignore[misc]

logger.info("Improvement module loaded (slim version — dispatch only)")
