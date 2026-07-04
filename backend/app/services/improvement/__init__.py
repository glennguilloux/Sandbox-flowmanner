"""
Autonomous Self-Improvement System — Slim Version.

Phases 3–6 (hypothesis testing, knob management, success learning,
strategy evolution, metrics collection, alerting) have been removed.
They were never wired into production — 107 missions ran with zero
improvement data recorded.

What remains:
- Phase 1 (failure_types): failure classification and telemetry
- Phase 2 (causal_decomposer): failure-to-strategy mapping
- Dispatch layer (improvement_loop_v2): background review Celery task
"""

import logging

logger = logging.getLogger(__name__)

# Phase 1: Foundation — failure classification
try:
    from .failure_types import (
        FailureContext,
        FailureSeverity,
        FailureType,
        capture_failure_telemetry,
        classify_failure,
        get_failure_telemetry,
    )
except ImportError as e:
    logger.warning("Failed to import failure_types: %s", e)
    FailureType = None  # type: ignore[misc]
    FailureSeverity = None  # type: ignore[misc]
    FailureContext = None  # type: ignore[misc]
    classify_failure = None  # type: ignore[misc]
    capture_failure_telemetry = None  # type: ignore[misc]
    get_failure_telemetry = None  # type: ignore[misc]

# Phase 2: Causal Understanding — failure-to-strategy mapping
try:
    from .causal_decomposer import (
        CausalDecomposer,
        ImprovementStrategy,
        KnobType,
        RiskLevel,
        StrategyType,
        WeakArea,
        get_causal_decomposer,
    )
except ImportError as e:
    logger.warning("Failed to import causal_decomposer: %s", e)
    KnobType = None  # type: ignore[misc]
    StrategyType = None  # type: ignore[misc]
    RiskLevel = None  # type: ignore[misc]
    ImprovementStrategy = None  # type: ignore[misc]
    WeakArea = None  # type: ignore[misc]
    CausalDecomposer = None  # type: ignore[misc]
    get_causal_decomposer = None  # type: ignore[misc]

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

logger.info("Improvement module loaded (slim version — Phases 1–2 + dispatch)")
