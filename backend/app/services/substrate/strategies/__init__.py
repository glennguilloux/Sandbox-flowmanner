"""Strategy registry — maps WorkflowType → ExecutionStrategy (H5.1).

The UnifiedExecutor uses this registry to dispatch workflow execution
to the correct strategy.  New strategies register themselves here.
"""

from __future__ import annotations

from app.services.substrate.workflow_models import WorkflowType

# Lazy imports to avoid circular dependencies at module load time.
# Each strategy module registers itself when imported.


class StrategyRegistry:
    """Maps WorkflowType → ExecutionStrategy class.

    Lazy-loaded: strategies are imported on first access, not at boot.
    """

    _strategies: dict[WorkflowType, type] = {}
    _imported: set[str] = set()

    @classmethod
    def _ensure_imported(cls) -> None:
        """Import all strategy modules (idempotent)."""
        if "all" in cls._imported:
            return

        modules = [
            ("solo", ".solo", "SoloStrategy"),
            ("dag", ".dag", "DAGStrategy"),
            ("graph", ".graph", "GraphStrategy"),
            ("swarm", ".swarm", "SwarmStrategy"),
            ("pipeline", ".pipeline", "PipelineStrategy"),
            ("meta", ".meta", "MetaStrategy"),
            ("langgraph", ".langgraph", "LangGraphStrategy"),
        ]

        for wf_type, module_path, class_name in modules:
            try:
                mod = __import__(
                    module_path,
                    fromlist=[class_name],
                    level=1,
                )
                cls._strategies[WorkflowType(wf_type)] = getattr(mod, class_name)
            except ImportError as e:
                import logging

                logging.getLogger(__name__).warning("Could not import strategy %s: %s", wf_type, e)

        cls._imported.add("all")

    @classmethod
    def get(cls, workflow_type: WorkflowType) -> type | None:
        """Get the strategy class for a workflow type."""
        cls._ensure_imported()
        return cls._strategies.get(workflow_type)

    @classmethod
    def register(cls, workflow_type: WorkflowType, strategy_cls: type) -> None:
        """Manually register a strategy (for testing)."""
        cls._strategies[workflow_type] = strategy_cls

    @classmethod
    def all_types(cls) -> list[WorkflowType]:
        """Get all registered workflow types."""
        cls._ensure_imported()
        return list(cls._strategies.keys())
