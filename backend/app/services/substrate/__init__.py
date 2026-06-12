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
from .leases import (
    LeaseRecord,
    get_active_lease,
    release_lease,
    renew_lease,
    try_claim_lease,
)
from .replay_engine import ReplayEngine, get_replay_engine
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
    "LeaseRecord",
    "get_active_lease",
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
]
