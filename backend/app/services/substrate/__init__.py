"""Substrate service layer — event-sourced execution (H2.1 → H5.1).

H2.1: Event-sourced substrate (event_log, replay_engine)
H5.1: Unified executor (executor, node_executor, strategies, adapters)
"""

from .adapters import (
    flow_to_workflow,
    graph_to_workflow,
    mission_to_workflow,
)
from .event_log import EventLog, get_event_log
from .executor import LeaseLostError, UnifiedExecutor, get_unified_executor
from .lease_reclaimer import LeaseReclaimer, find_expired_leases, reclaim_one
from .leases import (
    LeaseRecord,
    get_active_lease,
    release_lease,
    renew_lease,
    try_claim_lease,
)
from .replay_engine import ReplayEngine, get_replay_engine
from .circuit_breaker import (
    CircuitBreakerCheck,
    CircuitBreakerOpen,
    CircuitBreakerState,
    check_and_allow,
    record_failure,
    record_success,
)
from .provider_fallback import AllProvidersOpen, get_fallback_chain, resolve_provider
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
    # H2.1
    "EventLog",
    "NodeType",
    "ReplayEngine",
    "StrategyResult",
    # H5.1 — Unified Executor
    "UnifiedExecutor",
    # H5.1 — Workflow models
    "Workflow",
    "WorkflowEdge",
    "WorkflowNode",
    "WorkflowType",
    # Q1-A — Worker leases
    "LeaseLostError",
    "LeaseReclaimer",
    "LeaseRecord",
    "find_expired_leases",
    "get_active_lease",
    "reclaim_one",
    "release_lease",
    "renew_lease",
    "try_claim_lease",
    "flow_to_workflow",
    "get_event_log",
    "get_replay_engine",
    "get_unified_executor",
    "graph_to_workflow",
    # H5.1 — Adapters
    "mission_to_workflow",
    # Q1-A chunk 4 — Resume validation
    "ResumeValidation",
    "validate_resume_state",
    # Q1-A chunk 5 — Per-workspace+provider circuit breaker
    "AllProvidersOpen",
    "CircuitBreakerCheck",
    "CircuitBreakerOpen",
    "CircuitBreakerState",
    "check_and_allow",
    "get_fallback_chain",
    "record_failure",
    "record_success",
    "resolve_provider",
]
