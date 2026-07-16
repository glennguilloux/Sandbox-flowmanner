"""ExecutionStrategy ABC — the interface every strategy implements (H5.1).

All 7 strategies (Solo, DAG, Graph, Swarm, Pipeline, Meta, LangGraph)
implement this interface.  The UnifiedExecutor calls validate() before
execution and execute() to run the workflow.

Strategies receive the database session from the UnifiedExecutor which
in turn receives it from the API route — no strategy creates its own
session.  This preserves transactional integrity.

WorkflowWSManager provides a shared WebSocket broadcast utility that
replaces the scattered ws_manager.send_event() and sio.emit() patterns
in the old executors.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.services.substrate.executor import UnifiedExecutor
    from app.services.substrate.workflow_models import (
        StrategyResult,
        Workflow,
        WorkflowType,
    )

logger = logging.getLogger(__name__)


def _validate_edge_endpoints(workflow: Workflow) -> list[str]:
    """Reject edges whose source or target names a non-existent node id.

    Shared by every strategy so dangling edges fail validation uniformly
    (parity). Previously only DAG/Graph checked this; Swarm/Pipeline/Meta/
    LangGraph silently accepted dangling edges. This is now the single
    source of truth.

    The message strings are asserted by DAG validation tests, so they must
    stay exactly: ``Edge source '<id>' not found in nodes`` /
    ``Edge target '<id>' not found in nodes``.
    """
    node_ids = {n.id for n in workflow.nodes}
    errors: list[str] = []
    for edge in workflow.edges:
        if edge.source not in node_ids:
            errors.append(f"Edge source '{edge.source}' not found in nodes")
        if edge.target not in node_ids:
            errors.append(f"Edge target '{edge.target}' not found in nodes")
    return errors


class ExecutionStrategy(ABC):
    """Interface for all workflow execution strategies.

    Each strategy handles exactly one WorkflowType.  The strategy
    validates the workflow structure and executes it against a
    UnifiedExecutor context.
    """

    @abstractmethod
    async def validate(self, workflow: Workflow) -> list[str]:
        """Pre-flight validation. Returns list of errors (empty = valid).

        Each strategy enforces its own structural rules:
        - SoloStrategy: exactly 1 node, no edges
        - DAGStrategy: no cycles, all dep references valid
        - SwarmStrategy: at least 1 FAN_OUT and 1 FAN_IN node
        - PipelineStrategy: all nodes are PHASE_GATE, ordered by edges
        - GraphStrategy: nodes have handlers in NodeHandlerRegistry
        - MetaStrategy: contains at least 1 SUB_WORKFLOW node, depth <= max
        - LangGraphStrategy: nodes reference valid LangGraph graphs
        """
        ...

    @abstractmethod
    async def execute(
        self,
        workflow: Workflow,
        context: dict[str, Any],
        executor: UnifiedExecutor,
        db: AsyncSession,
        run_id: str,
    ) -> StrategyResult:
        """Execute the strategy against a workflow.

        Args:
            workflow: The workflow to execute.
            context: Execution context (node outputs, iteration vars, etc.).
            executor: The UnifiedExecutor that provides shared services
                      (event_log, budget_enforcer, capability_engine, etc.).
            db: The database session from the API route — strategies MUST
                use this session, not create their own.
            run_id: The substrate run ID. This is the ONLY authoritative run
                ID for the execution and is owned by UnifiedExecutor. Strategies
                MUST NOT generate or read their own run ID; all events, abort
                checks, leases, and HITL resume use this value so that replay,
                leases, aborts, and event correlation stay consistent.

        Returns:
            StrategyResult with success, status, and execution details.
        """
        ...

    @abstractmethod
    def can_handle(self, workflow_type: WorkflowType) -> bool:
        """Check if this strategy handles the given workflow type."""
        ...


class WorkflowWSManager:
    """Shared WebSocket broadcast utility for all strategies.

    Replaces the scattered patterns in the old executors:
    - swarm_pipeline: ws_manager.send_event()
    - graph_executor: sio.emit()
    - mission_executor: (no WS, but would benefit)

    All strategies use this single manager for event broadcasting.
    """

    async def send_event(self, run_id: str, event_type: str, data: dict[str, Any]) -> None:
        """Send an event to all clients watching a specific run."""
        try:
            from app.websocket.mission_ws import sio

            await sio.emit(
                f"workflow:{event_type}",
                {"run_id": run_id, **data},
                room=f"workflow_{run_id}",
            )
        except Exception as e:
            logger.debug("WebSocket send_event failed (non-critical): %s", e)

    async def broadcast_phase(self, run_id: str, phase: str, status: str) -> None:
        """Broadcast a pipeline phase transition."""
        await self.send_event(
            run_id,
            "phase_changed",
            {"phase": phase, "status": status},
        )

    async def broadcast_node_state(
        self,
        run_id: str,
        node_id: str,
        status: str,
        output: dict[str, Any] | None = None,
    ) -> None:
        """Broadcast a node state change."""
        await self.send_event(
            run_id,
            "node_state",
            {"node_id": node_id, "status": status, "output": output},
        )


# Singleton
_ws_manager: WorkflowWSManager | None = None


def get_ws_manager() -> WorkflowWSManager:
    """Get or create the WorkflowWSManager singleton."""
    global _ws_manager
    if _ws_manager is None:
        _ws_manager = WorkflowWSManager()
    return _ws_manager
