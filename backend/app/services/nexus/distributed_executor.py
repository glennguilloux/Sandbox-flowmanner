"""
Distributed Executor - Celery-based Distributed Task Execution

Enables distributed execution of capabilities and DAGs across
Celery workers for scalable, fault-tolerant processing.

Integration Points:
- Celery App: app.celery_app.celery_app
- Capability Registry: For executing capabilities
- Meta-Loop Orchestrator: For distributed mode
"""

import asyncio
import logging
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Import Celery app
try:
    from app.celery_app import celery_app

    CELERY_AVAILABLE = True
except ImportError:
    CELERY_AVAILABLE = False
    logger.warning("Celery not available, distributed execution disabled")

# Worker initialization - register capabilities when worker starts
if CELERY_AVAILABLE:

    @celery_app.on_after_configure.connect
    def initialize_worker_capabilities(sender=None, **kwargs):
        """Initialize capability registry when Celery worker starts.

        This ensures tools are registered in worker processes,
        which don't go through FastAPI startup.
        """
        logger.info("[Celery Worker] Initializing capability registry...")
        try:
            from .capability_registry import get_capability_registry
            from .orchestrator import get_nexus_orchestrator

            # Get the registry singleton
            registry = get_capability_registry()

            # Initialize the orchestrator which registers built-in capabilities
            orchestrator = get_nexus_orchestrator()

            # Run async initialization in sync context
            import asyncio

            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # If loop is already running, create a task
                    _init_task = asyncio.create_task(orchestrator.initialize())
                else:
                    loop.run_until_complete(orchestrator.initialize())
            except RuntimeError:
                # No event loop, create one
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    loop.run_until_complete(orchestrator.initialize())
                finally:
                    loop.close()

            logger.info(
                "[Celery Worker] Capability registry initialized with %s capabilities",
                len(registry.list_capabilities()),
            )
        except Exception as e:
            logger.error(
                "[Celery Worker] Failed to initialize capability registry: %s", e
            )


class TaskStatus(str, Enum):
    """Status of a distributed task"""

    PENDING = "pending"
    STARTED = "started"
    PROGRESS = "progress"
    SUCCESS = "success"
    FAILURE = "failure"
    RETRY = "retry"
    REVOKED = "revoked"


@dataclass
class DistributedTask:
    """Represents a distributed task"""

    task_id: str
    name: str
    status: TaskStatus
    result: Any = None
    error: str | None = None
    progress: float = 0.0
    created_at: datetime = field(default_factory=datetime.utcnow)
    started_at: datetime | None = None
    completed_at: datetime | None = None
    worker_name: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "name": self.name,
            "status": self.status.value,
            "result": self.result,
            "error": self.error,
            "progress": self.progress,
            "created_at": self.created_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": (
                self.completed_at.isoformat() if self.completed_at else None
            ),
            "worker_name": self.worker_name,
            "metadata": self.metadata,
        }


@dataclass
class ExecutionDAG:
    """Directed Acyclic Graph for execution planning"""

    dag_id: str
    nodes: dict[str, dict[str, Any]] = field(default_factory=dict)
    edges: list[tuple] = field(default_factory=list)  # (from_node, to_node)
    created_at: datetime = field(default_factory=datetime.utcnow)

    def add_node(
        self,
        node_id: str,
        capability_id: str,
        params: dict[str, Any],
        depends_on: list[str] = None,
    ):
        """Add a node to the DAG"""
        self.nodes[node_id] = {
            "capability_id": capability_id,
            "params": params,
            "depends_on": depends_on or [],
            "status": "pending",
        }

    def add_edge(self, from_node: str, to_node: str):
        """Add an edge between nodes"""
        self.edges.append((from_node, to_node))
        if to_node in self.nodes and from_node not in self.nodes[to_node]["depends_on"]:
            self.nodes[to_node]["depends_on"].append(from_node)

    def get_ready_nodes(self, completed: list[str]) -> list[str]:
        """Get nodes ready for execution (all dependencies met)"""
        ready = []
        for node_id, node in self.nodes.items():
            if node["status"] == "pending" and all(
                dep in completed for dep in node["depends_on"]
            ):
                ready.append(node_id)
        return ready

    def to_dict(self) -> dict[str, Any]:
        return {
            "dag_id": self.dag_id,
            "nodes": self.nodes,
            "edges": self.edges,
            "created_at": self.created_at.isoformat(),
        }


class NexusCeleryTasks:
    """
    Celery task definitions for Nexus distributed execution.
    These tasks are registered with the Celery app.
    """

    @staticmethod
    def register_tasks():
        """Register all Nexus tasks with Celery"""
        if not CELERY_AVAILABLE:
            logger.warning("Cannot register tasks: Celery not available")
            return

        logger.info(
            "[Celery Worker] Pre-initializing capability registry before task registration..."
        )
        try:
            from .capability_registry import get_capability_registry
            from .orchestrator import get_nexus_orchestrator

            registry = get_capability_registry()
            orchestrator = get_nexus_orchestrator()

            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    init_task = asyncio.create_task(orchestrator.initialize())
                    init_task.add_done_callback(
                        lambda task: task.exception() if not task.cancelled() else None
                    )
                else:
                    loop.run_until_complete(orchestrator.initialize())
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    loop.run_until_complete(orchestrator.initialize())
                finally:
                    loop.close()

            logger.info(
                "[Celery Worker] Capability registry pre-initialized with %s capabilities",
                len(registry.list_capabilities()),
            )
        except Exception as e:
            logger.error(
                "[Celery Worker] Failed to pre-initialize capability registry: %s", e
            )

        @celery_app.task(bind=True, name="nexus.execute_capability")
        def execute_capability_task(
            self,
            capability_id: str,
            params: dict,
            user_id: str = None,
            session_id: str = None,
        ):
            """Execute a single capability in a Celery worker"""
            import asyncio

            from app.services.nexus.capability_registry import get_capability_registry

            logger.info("Executing capability: %s", capability_id)

            try:
                self.update_state(state="PROGRESS", meta={"progress": 0})

                registry = get_capability_registry()
                capability = registry.get(capability_id)

                if not capability:
                    return {
                        "success": False,
                        "error": f"Capability not found: {capability_id}",
                    }

                # Execute capability (handle both sync and async)
                if asyncio.iscoroutinefunction(capability.handler):
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    try:
                        result = loop.run_until_complete(capability.execute(params))
                    finally:
                        loop.close()
                else:
                    result = capability.execute(params)

                self.update_state(state="PROGRESS", meta={"progress": 100})

                return {
                    "success": True,
                    "capability_id": capability_id,
                    "result": result,
                    "worker": (
                        self.request.hostname if hasattr(self, "request") else "unknown"
                    ),
                }

            except Exception as e:
                logger.error("Capability execution failed: %s", e)
                return {
                    "success": False,
                    "capability_id": capability_id,
                    "error": str(e),
                }

        @celery_app.task(bind=True, name="nexus.execute_dag_node")
        def execute_dag_node_task(
            self,
            dag_id: str,
            node_id: str,
            capability_id: str,
            params: dict,
            dependency_results: dict = None,
        ):
            """Execute a single DAG node"""
            import asyncio

            from app.services.nexus.capability_registry import get_capability_registry

            logger.info("Executing DAG node: %s in DAG %s", node_id, dag_id)

            try:
                self.update_state(
                    state="PROGRESS", meta={"node_id": node_id, "progress": 0}
                )

                # Merge dependency results into params
                if dependency_results:
                    params = {**params, "dependency_results": dependency_results}

                registry = get_capability_registry()
                capability = registry.get(capability_id)

                if not capability:
                    return {
                        "success": False,
                        "node_id": node_id,
                        "error": f"Capability not found: {capability_id}",
                    }

                # Execute capability
                if asyncio.iscoroutinefunction(capability.handler):
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    try:
                        result = loop.run_until_complete(capability.execute(params))
                    finally:
                        loop.close()
                else:
                    result = capability.execute(params)

                self.update_state(
                    state="PROGRESS", meta={"node_id": node_id, "progress": 100}
                )

                return {
                    "success": True,
                    "dag_id": dag_id,
                    "node_id": node_id,
                    "result": result,
                }

            except Exception as e:
                logger.error("DAG node execution failed: %s", e)
                return {
                    "success": False,
                    "dag_id": dag_id,
                    "node_id": node_id,
                    "error": str(e),
                }

        @celery_app.task(bind=True, name="nexus.execute_composed")
        def execute_composed_task(self, composed_id: str, params: dict):
            """Execute a composed capability"""
            import asyncio

            from app.services.nexus.capability_composer import get_capability_composer

            logger.info("Executing composed capability: %s", composed_id)

            try:
                self.update_state(
                    state="PROGRESS", meta={"composed_id": composed_id, "progress": 0}
                )

                composer = get_capability_composer()

                # Execute composed capability
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    result = loop.run_until_complete(
                        composer.execute_composed(composed_id, params)
                    )
                finally:
                    loop.close()

                self.update_state(
                    state="PROGRESS", meta={"composed_id": composed_id, "progress": 100}
                )

                return {
                    "success": result.success,
                    "composed_id": composed_id,
                    "final_output": result.final_output,
                    "capabilities_executed": result.capabilities_executed,
                    "error": result.error,
                }

            except Exception as e:
                logger.error("Composed capability execution failed: %s", e)
                return {"success": False, "composed_id": composed_id, "error": str(e)}

        logger.info("Nexus Celery tasks registered")


class DistributedExecutor:
    """
    Distributed execution engine using Celery.

    Provides:
    - Task submission to Celery workers
    - DAG execution across workers
    - Task status monitoring
    - Worker health metrics
    """

    def __init__(self):
        self._tasks: dict[str, DistributedTask] = {}
        self._celery_available = CELERY_AVAILABLE

        if self._celery_available:
            NexusCeleryTasks.register_tasks()

    def is_available(self) -> bool:
        """Check if Celery is available"""
        return self._celery_available

    async def submit_task(
        self,
        coro: Callable,
        priority: int = 0,
        task_name: str = None,
        metadata: dict[str, Any] = None,
    ) -> str:
        """
        Submit an async task to Celery.

        Args:
            coro: Coroutine or callable to execute
            priority: Task priority (0-9, higher = more important)
            task_name: Optional task name
            metadata: Additional metadata

        Returns:
            Task ID
        """
        if not self._celery_available:
            logger.warning("Celery not available, executing locally")
            return await self._execute_locally(coro, metadata)

        task_id = str(uuid.uuid4())

        # Create task record
        task = DistributedTask(
            task_id=task_id,
            name=task_name or "anonymous_task",
            status=TaskStatus.PENDING,
            metadata=metadata or {},
        )
        self._tasks[task_id] = task

        try:
            # Submit to Celery
            result = celery_app.send_task(
                "nexus.execute_capability",
                kwargs={
                    "capability_id": metadata.get("capability_id", "unknown"),
                    "params": metadata.get("params", {}),
                },
                priority=priority,
                task_id=task_id,
            )

            task.status = TaskStatus.STARTED
            logger.info("Submitted task %s with priority %s", task_id, priority)

            return task_id

        except Exception as e:
            logger.error("Failed to submit task: %s", e)
            task.status = TaskStatus.FAILURE
            task.error = str(e)
            raise

    async def _execute_locally(self, coro: Callable, metadata: dict[str, Any]) -> str:
        """Execute task locally when Celery is unavailable"""
        task_id = str(uuid.uuid4())
        task = DistributedTask(
            task_id=task_id,
            name="local_execution",
            status=TaskStatus.STARTED,
            metadata=metadata or {},
        )
        self._tasks[task_id] = task

        try:
            if asyncio.iscoroutine(coro):
                result = await coro
            elif asyncio.iscoroutinefunction(coro):
                result = await coro()
            else:
                result = coro()

            task.status = TaskStatus.SUCCESS
            task.result = result
            task.completed_at = datetime.now(UTC)

        except Exception as e:
            task.status = TaskStatus.FAILURE
            task.error = str(e)

        return task_id

    async def submit_dag(self, dag: ExecutionDAG, priority: int = 0) -> str:
        """
        Execute a DAG across Celery workers.

        Args:
            dag: ExecutionDAG to execute
            priority: Task priority

        Returns:
            DAG execution ID
        """
        if not self._celery_available:
            logger.warning("Celery not available, executing DAG locally")
            return await self._execute_dag_locally(dag)

        dag_id = dag.dag_id

        # Create task record for the DAG
        task = DistributedTask(
            task_id=dag_id,
            name=f"dag_execution:{dag_id}",
            status=TaskStatus.PENDING,
            metadata={"dag": dag.to_dict()},
        )
        self._tasks[dag_id] = task

        try:
            # Execute DAG nodes in topological order
            completed_nodes: list[str] = []
            node_results: dict[str, Any] = {}

            while len(completed_nodes) < len(dag.nodes):
                # Get nodes ready for execution
                ready_nodes = dag.get_ready_nodes(completed_nodes)

                if not ready_nodes:
                    # Check for cycles or missing dependencies
                    remaining = [n for n in dag.nodes if n not in completed_nodes]
                    if remaining:
                        logger.error(
                            "DAG execution stuck, remaining nodes: %s", remaining
                        )
                        break
                    break

                # Submit ready nodes in parallel
                tasks_to_submit = []
                for node_id in ready_nodes:
                    node = dag.nodes[node_id]

                    # Gather dependency results
                    dep_results = {
                        dep: node_results.get(dep) for dep in node["depends_on"]
                    }

                    tasks_to_submit.append(
                        {
                            "node_id": node_id,
                            "capability_id": node["capability_id"],
                            "params": node["params"],
                            "dependency_results": dep_results,
                        }
                    )
                    dag.nodes[node_id]["status"] = "running"

                # Submit batch to Celery
                celery_results = []
                for task_info in tasks_to_submit:
                    result = celery_app.send_task(
                        "nexus.execute_dag_node",
                        kwargs={
                            "dag_id": dag_id,
                            "node_id": task_info["node_id"],
                            "capability_id": task_info["capability_id"],
                            "params": task_info["params"],
                            "dependency_results": task_info["dependency_results"],
                        },
                        priority=priority,
                    )
                    celery_results.append((task_info["node_id"], result))

                # Wait for batch completion
                for node_id, celery_result in celery_results:
                    try:
                        result = celery_result.get(timeout=300)  # 5 min timeout
                        if result.get("success"):
                            node_results[node_id] = result.get("result")
                            completed_nodes.append(node_id)
                            dag.nodes[node_id]["status"] = "completed"
                        else:
                            dag.nodes[node_id]["status"] = "failed"
                            logger.error(
                                "Node %s failed: %s", node_id, result.get("error")
                            )
                    except Exception as e:
                        dag.nodes[node_id]["status"] = "failed"
                        logger.error("Node %s execution error: %s", node_id, e)

            task.status = TaskStatus.SUCCESS
            task.result = node_results
            task.completed_at = datetime.now(UTC)

            return dag_id

        except Exception as e:
            logger.error("DAG execution failed: %s", e)
            task.status = TaskStatus.FAILURE
            task.error = str(e)
            raise

    async def _execute_dag_locally(self, dag: ExecutionDAG) -> str:
        """Execute DAG locally when Celery is unavailable"""
        from app.services.nexus.capability_registry import get_capability_registry

        dag_id = dag.dag_id
        task = DistributedTask(
            task_id=dag_id,
            name=f"local_dag:{dag_id}",
            status=TaskStatus.STARTED,
            metadata={"dag": dag.to_dict()},
        )
        self._tasks[dag_id] = task

        registry = get_capability_registry()
        completed_nodes: list[str] = []
        node_results: dict[str, Any] = {}

        while len(completed_nodes) < len(dag.nodes):
            ready_nodes = dag.get_ready_nodes(completed_nodes)

            if not ready_nodes:
                break

            for node_id in ready_nodes:
                node = dag.nodes[node_id]
                capability = registry.get(node["capability_id"])

                if capability:
                    try:
                        # Merge dependency results
                        params = node["params"].copy()
                        for dep in node["depends_on"]:
                            if dep in node_results:
                                params[f"_{dep}_result"] = node_results[dep]

                        result = await capability.execute(params)
                        node_results[node_id] = result
                        dag.nodes[node_id]["status"] = "completed"
                    except Exception as e:
                        logger.error("Node %s failed: %s", node_id, e)
                        dag.nodes[node_id]["status"] = "failed"

                completed_nodes.append(node_id)

        task.status = TaskStatus.SUCCESS
        task.result = node_results
        task.completed_at = datetime.now(UTC)

        return dag_id

    def get_task_status(self, task_id: str) -> DistributedTask | None:
        """
        Get the status of a task.

        Args:
            task_id: Task ID to check

        Returns:
            DistributedTask or None if not found
        """
        task = self._tasks.get(task_id)

        if task and self._celery_available:
            # Update from Celery
            try:
                from celery.result import AsyncResult

                async_result = AsyncResult(task_id)

                if async_result.state == "SUCCESS":
                    task.status = TaskStatus.SUCCESS
                    task.result = async_result.result
                    task.completed_at = datetime.now(UTC)
                elif async_result.state == "FAILURE":
                    task.status = TaskStatus.FAILURE
                    task.error = str(async_result.result)
                elif async_result.state == "PROGRESS":
                    task.status = TaskStatus.PROGRESS
                    task.progress = async_result.info.get("progress", 0)
                elif async_result.state == "STARTED":
                    task.status = TaskStatus.STARTED
                    task.started_at = datetime.now(UTC)
            except Exception as e:
                logger.warning("Could not get Celery status: %s", e)

        return task

    def cancel_task(self, task_id: str) -> bool:
        """
        Cancel a running task.

        Args:
            task_id: Task ID to cancel

        Returns:
            True if cancelled successfully
        """
        task = self._tasks.get(task_id)
        if not task:
            return False

        if self._celery_available:
            try:
                from celery.result import AsyncResult

                async_result = AsyncResult(task_id)
                async_result.revoke(terminate=True)
                task.status = TaskStatus.REVOKED
                logger.info("Revoked task %s", task_id)
                return True
            except Exception as e:
                logger.error("Failed to revoke task: %s", e)
                return False
        else:
            task.status = TaskStatus.REVOKED
            return True

    def get_worker_stats(self) -> dict[str, Any]:
        """
        Get worker health and metrics.

        Returns:
            Dictionary with worker statistics
        """
        if not self._celery_available:
            return {"available": False, "message": "Celery not available"}

        try:
            from celery import current_app

            inspect = current_app.control.inspect()

            stats = {
                "available": True,
                "workers": {},
                "total_workers": 0,
                "active_tasks": 0,
            }

            # Get active workers
            active = inspect.active() or {}
            stats["total_workers"] = len(active)

            for worker, tasks in active.items():
                stats["workers"][worker] = {
                    "active_tasks": len(tasks),
                    "status": "online",
                }
                stats["active_tasks"] += len(tasks)

            # Get registered tasks
            registered = inspect.registered() or {}
            for worker, tasks in registered.items():
                if worker in stats["workers"]:
                    stats["workers"][worker]["registered_tasks"] = len(tasks)

            # Get worker stats
            worker_stats = inspect.stats() or {}
            for worker, wstats in worker_stats.items():
                if worker in stats["workers"]:
                    stats["workers"][worker]["total_tasks"] = wstats.get(
                        "total", {}
                    ).get("tasks", 0)

            return stats

        except Exception as e:
            logger.error("Failed to get worker stats: %s", e)
            return {"available": False, "error": str(e)}

    def list_tasks(self, status: TaskStatus = None) -> list[DistributedTask]:
        """List all tasks, optionally filtered by status"""
        tasks = list(self._tasks.values())
        if status:
            tasks = [t for t in tasks if t.status == status]
        return tasks

    def clear_completed_tasks(self) -> int:
        """Clear completed tasks from memory"""
        to_remove = [
            task_id
            for task_id, task in self._tasks.items()
            if task.status
            in (TaskStatus.SUCCESS, TaskStatus.FAILURE, TaskStatus.REVOKED)
        ]
        for task_id in to_remove:
            del self._tasks[task_id]

        logger.info("Cleared %s completed tasks", len(to_remove))
        return len(to_remove)


# Singleton instance
_distributed_executor: Optional["DistributedExecutor"] = None


def get_distributed_executor() -> DistributedExecutor:
    """Get or create the distributed executor singleton"""
    global _distributed_executor
    if _distributed_executor is None:
        _distributed_executor = DistributedExecutor()
    return _distributed_executor
