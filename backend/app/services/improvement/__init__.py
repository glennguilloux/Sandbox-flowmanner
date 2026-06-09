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
    FailureType = None
    FailureSeverity = None
    FailureContext = None
    classify_failure = None
    capture_failure_telemetry = None
    get_failure_telemetry = None

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
    KnobType = None
    StrategyType = None
    RiskLevel = None
    ImprovementStrategy = None
    WeakArea = None
    CausalDecomposer = None
    get_causal_decomposer = None

try:
    from .knob_manager import (
        ImprovementKnob,
        KnobAdjustment,
        KnobManager,
        get_knob_manager,
    )
except ImportError as e:
    logger.warning("Failed to import knob_manager: %s", e)
    ImprovementKnob = None
    KnobAdjustment = None
    KnobManager = None
    get_knob_manager = None

try:
    from .improvement_models import (
        AppliedImprovement,
        FailureContextModel,
        ImprovementMetrics,
        ImprovementSession,
    )
except ImportError as e:
    logger.warning("Failed to import improvement_models: %s", e)
    AppliedImprovement = None
    FailureContextModel = None
    ImprovementSession = None
    ImprovementMetrics = None

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
    HypothesisState = None
    TestType = None
    RollbackTrigger = None
    HypothesisTest = None
    TestResult = None
    SafetyConstraint = None
    HypothesisTester = None
    get_hypothesis_tester = None

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
    SessionState = None
    ImprovementSessionData = None
    ImprovementKnowledge = None
    ImprovementLoopV2 = None
    get_improvement_loop = None
    initialize_improvement_loop = None

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
    MetricType = None
    MetricPoint = None
    MetricsCollector = None
    get_metrics_collector = None

try:
    from .failure_repository import (
        FailureRepository,
        get_failure_repository,
    )
except ImportError as e:
    logger.warning("Failed to import failure_repository: %s", e)
    FailureRepository = None
    get_failure_repository = None

try:
    from .alerting import (
        Alert,
        AlertingSystem,
        AlertSeverity,
        get_alerting_system,
    )
except ImportError as e:
    logger.warning("Failed to import alerting: %s", e)
    AlertSeverity = None
    Alert = None
    AlertingSystem = None
    get_alerting_system = None

# Phase 6: Advanced Learning
try:
    from .success_learner import (
        SuccessLearner,
        SuccessPattern,
        get_success_learner,
    )
except ImportError as e:
    logger.warning("Failed to import success_learner: %s", e)
    SuccessPattern = None
    SuccessLearner = None
    get_success_learner = None

logger.info("Improvement module loaded with graceful degradation")
