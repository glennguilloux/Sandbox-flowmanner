"""Substrate service layer — event-sourced execution (H2.1 → H5.1).

H2.1: Event-sourced substrate (event_log, replay_engine)
H5.1: Unified executor (executor, node_executor, strategies, adapters)
"""

from .adapters import (
    flow_to_workflow,
    graph_to_workflow,
    mission_to_workflow,
)
from .circuit_breaker import (
    CircuitBreakerCheck,
    CircuitBreakerOpen,
    CircuitBreakerState,
    check_and_allow,
    record_failure,
    record_success,
)
from .event_log import EventLog, get_event_log
from .executor import LeaseLostError, UnifiedExecutor, get_unified_executor
from .harness_evolution import (
    EvolutionLedger,
    ParamSpace,
    apply_params_to_candidate,
    run_evolution,
    score_run,
)
from .hitl_pause import HITLPaused, HITLResolution, check_hitl_resolution
from .lease_reclaimer import LeaseReclaimer, find_expired_leases, reclaim_one
from .leases import (
    LeaseRecord,
    get_active_lease,
    release_lease,
    renew_lease,
    try_claim_lease,
)
from .provider_fallback import (
    AllProvidersOpen,
    ProviderProvenance,
    get_fallback_chain,
    resolve_provider,
)
from .replay_engine import ReplayEngine, get_replay_engine
from .resume_validation import ResumeValidation, validate_resume_state
from .workflow_models import (
    NodeType,
    StrategyResult,
    Workflow,
    WorkflowEdge,
    WorkflowNode,
    WorkflowType,
)

__all__ = [
    "AllProvidersOpen",
    "CircuitBreakerCheck",
    "CircuitBreakerOpen",
    "CircuitBreakerState",
    "EventLog",
    "HITLPaused",
    "HITLResolution",
    "LeaseLostError",
    "LeaseReclaimer",
    "LeaseRecord",
    "NodeType",
    "ProviderProvenance",
    "ReplayEngine",
    "ResumeValidation",
    "StrategyResult",
    "UnifiedExecutor",
    "Workflow",
    "WorkflowEdge",
    "WorkflowNode",
    "WorkflowType",
    "check_and_allow",
    "check_hitl_resolution",
    "find_expired_leases",
    "flow_to_workflow",
    "get_active_lease",
    "get_event_log",
    "get_fallback_chain",
    "get_replay_engine",
    "get_unified_executor",
    "graph_to_workflow",
    "EvolutionLedger",
    "ParamSpace",
    "apply_params_to_candidate",
    "run_evolution",
    "score_run",
    "mission_to_workflow",
    "reclaim_one",
    "record_failure",
    "record_success",
    "release_lease",
    "renew_lease",
    "resolve_provider",
    "try_claim_lease",
    "validate_resume_state",
]
