"""
Autonomous Self-Improvement System

This package implements a comprehensive autonomous self-improvement architecture.
Imports are wrapped in try/except to allow partial functionality.
"""

import logging

logger = logging.getLogger(__name__)

# Phase 1: Foundation
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

# Phase 2: Causal Understanding
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

try:
    from .knob_manager import (
        ImprovementKnob,
        KnobAdjustment,
        KnobManager,
        get_knob_manager,
    )
except ImportError as e:
    logger.warning("Failed to import knob_manager: %s", e)
    ImprovementKnob = None  # type: ignore[misc]
    KnobAdjustment = None  # type: ignore[misc]
    KnobManager = None  # type: ignore[misc]
    get_knob_manager = None  # type: ignore[misc]

try:
    from .improvement_models import (
        AppliedImprovement,
        FailureContextModel,
        ImprovementMetrics,
        ImprovementSession,
    )
except ImportError as e:
    logger.warning("Failed to import improvement_models: %s", e)
    AppliedImprovement = None  # type: ignore[misc]
    FailureContextModel = None  # type: ignore[misc]
    ImprovementSession = None  # type: ignore[misc]
    ImprovementMetrics = None  # type: ignore[misc]

# Phase 3: Verification
try:
    from .hypothesis_tester import (
        HypothesisState,
        HypothesisTest,
        HypothesisTester,
        RollbackTrigger,
        SafetyConstraint,
        TestResult,
        TestType,
        get_hypothesis_tester,
    )
except ImportError as e:
    logger.warning("Failed to import hypothesis_tester: %s", e)
    HypothesisState = None  # type: ignore[misc]
    TestType = None  # type: ignore[misc]
    RollbackTrigger = None  # type: ignore[misc]
    HypothesisTest = None  # type: ignore[misc]
    TestResult = None  # type: ignore[misc]
    SafetyConstraint = None  # type: ignore[misc]
    HypothesisTester = None  # type: ignore[misc]
    get_hypothesis_tester = None  # type: ignore[misc]

# Phase 4: Synthesis
try:
    from .improvement_loop_v2 import (
        ImprovementKnowledge,
        ImprovementLoopV2,
        ImprovementSessionData,
        SessionState,
        get_improvement_loop,
        initialize_improvement_loop,
    )
except ImportError as e:
    logger.warning("Failed to import improvement_loop_v2: %s", e)
    SessionState = None  # type: ignore[misc]
    ImprovementSessionData = None  # type: ignore[misc]
    ImprovementKnowledge = None  # type: ignore[misc]
    ImprovementLoopV2 = None  # type: ignore[misc]
    get_improvement_loop = None  # type: ignore[misc]
    initialize_improvement_loop = None  # type: ignore[misc]

# Phase 5: Production Integration
try:
    from .metrics_collector import (
        MetricPoint,
        MetricsCollector,
        MetricType,
        get_metrics_collector,
    )
except ImportError as e:
    logger.warning("Failed to import metrics_collector: %s", e)
    MetricType = None  # type: ignore[misc]
    MetricPoint = None  # type: ignore[misc]
    MetricsCollector = None  # type: ignore[misc]
    get_metrics_collector = None  # type: ignore[misc]

try:
    from .failure_repository import (
        FailureRepository,
        get_failure_repository,
    )
except ImportError as e:
    logger.warning("Failed to import failure_repository: %s", e)
    FailureRepository = None  # type: ignore[misc]
    get_failure_repository = None  # type: ignore[misc]

try:
    from .alerting import (
        Alert,
        AlertingSystem,
        AlertSeverity,
        get_alerting_system,
    )
except ImportError as e:
    logger.warning("Failed to import alerting: %s", e)
    AlertSeverity = None  # type: ignore[misc]
    Alert = None  # type: ignore[misc]
    AlertingSystem = None  # type: ignore[misc]
    get_alerting_system = None  # type: ignore[misc]

# Phase 6: Advanced Learning
try:
    from .success_learner import (
        SuccessLearner,
        SuccessPattern,
        get_success_learner,
    )
except ImportError as e:
    logger.warning("Failed to import success_learner: %s", e)
    SuccessPattern = None  # type: ignore[misc]
    SuccessLearner = None  # type: ignore[misc]
    get_success_learner = None  # type: ignore[misc]

logger.info("Improvement module loaded with graceful degradation")
