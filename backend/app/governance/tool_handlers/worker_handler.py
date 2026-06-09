#!/usr/bin/env python3
"""
Worker Handler

Handler for executing Celery worker tasks.
Provides same interface as OpenWhiskHandler for consistency.
"""

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class WorkerConfig:
    """Worker configuration"""

    timeout: int = 300
    max_retries: int = 3
    concurrency: int = 4


class WorkerHandler:
    """
    Handler for Celery worker tasks.

    This class provides the same interface as OpenWhiskHandler
    for consistency in the Yellow Zone. It dispatches tasks
    to Celery workers instead of OpenWhisk actions.

    Example:
        handler = WorkerHandler()
        result = handler.execute(
            action='step_2a_generate_request',
            params={'workflow_id': 'wf_001', ...}
        )
    """

    def __init__(self, config: WorkerConfig | None = None):
        """Initialize WorkerHandler"""
        self.config = config or self._load_config_from_env()

        # Task registry
        self._task_registry = {
            "step_2a_generate_request": "workers.step_2a_generate_request",
            "step_2b_process_response": "workers.step_2b_process_response",
            "data_fetch": "workers.data_fetch",
            "data_transform": "workers.data_transform",
        }

        logger.info(
            "WorkerHandler initialized - Timeout: %ss, Max Retries: %s",
            self.config.timeout,
            self.config.max_retries,
        )

    @staticmethod
    def _load_config_from_env() -> WorkerConfig:
        """Load configuration from environment variables"""
        import os

        timeout = int(os.getenv("WORKER_TIMEOUT", "300"))
        max_retries = int(os.getenv("WORKER_MAX_RETRIES", "3"))
        concurrency = int(os.getenv("WORKER_CONCURRENCY", "4"))

        return WorkerConfig(
            timeout=timeout, max_retries=max_retries, concurrency=concurrency
        )

    def execute(
        self,
        action: str,
        params: dict[str, Any],
        timeout: int | None = None,
        blocking: bool = True,
    ) -> dict[str, Any]:
        """Execute a worker task"""
        from app.tasks.celery_app import celery_app

        # Get task name from registry
        task_name = self._task_registry.get(action)
        if not task_name:
            raise ValueError(
                f"Unknown action: {action}. Available actions: {list(self._task_registry.keys())}"
            )

        # Prepare task request
        task_request = self._prepare_request(action, params)
        task_timeout = timeout or self.config.timeout

        # Execute task
        logger.info("Executing task: %s", task_name)
        result = celery_app.send_task(
            task_name, args=[task_request], expires=task_timeout
        )

        if blocking:
            try:
                task_result = result.get(timeout=task_timeout)
                return task_result
            except Exception as e:
                logger.error("Task execution failed: %s", e, exc_info=True)
                return {
                    "success": False,
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "timestamp": datetime.now(UTC).isoformat(),
                }
        else:
            return {
                "task_id": result.id,
                "task_name": task_name,
                "status": "submitted",
                "timestamp": datetime.now(UTC).isoformat(),
            }

    def execute_chain(
        self,
        actions: list,
        params_list: list,
        timeout: int | None = None,
        blocking: bool = True,
    ) -> dict[str, Any]:
        """Execute a chain of worker tasks"""
        if len(actions) != len(params_list):
            raise ValueError(
                f"Actions count ({len(actions)}) must match params count ({len(params_list)})"
            )

        from app.tasks.celery_app import celery_app

        # Build task chain
        tasks = []
        for action, params in zip(actions, params_list, strict=False):
            task_name = self._task_registry.get(action)
            if not task_name:
                raise ValueError(f"Unknown action: {action}")

            task_request = self._prepare_request(action, params)
            tasks.append(celery_app.signature(task_name, args=[task_request]))

        # Create chain
        from celery import chain

        task_chain = chain(*tasks)

        logger.info("Executing chain of %s tasks", len(tasks))
        result = task_chain.apply_async()

        if blocking:
            task_timeout = timeout or (self.config.timeout * len(tasks))
            try:
                chain_result = result.get(timeout=task_timeout)
                return {
                    "success": True,
                    "results": (
                        chain_result
                        if isinstance(chain_result, list)
                        else [chain_result]
                    ),
                    "chain_length": len(tasks),
                    "timestamp": datetime.now(UTC).isoformat(),
                }
            except Exception as e:
                logger.error("Chain execution failed: %s", e, exc_info=True)
                return {
                    "success": False,
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "timestamp": datetime.now(UTC).isoformat(),
                }
        else:
            return {
                "chain_id": result.id,
                "chain_length": len(tasks),
                "status": "submitted",
                "timestamp": datetime.now(UTC).isoformat(),
            }

    def get_task_status(self, task_id: str) -> dict[str, Any]:
        """Get status of a task"""
        from celery.result import AsyncResult

        from app.tasks.celery_app import celery_app

        result = AsyncResult(task_id, app=celery_app)

        return {
            "task_id": task_id,
            "status": result.status,
            "successful": result.successful() if result.ready() else None,
            "failed": result.failed() if result.ready() else None,
            "result": result.result if result.ready() else None,
            "timestamp": datetime.now(UTC).isoformat(),
        }

    def cancel_task(self, task_id: str) -> bool:
        """Cancel a running task"""
        from celery.result import AsyncResult

        from app.tasks.celery_app import celery_app

        try:
            result = AsyncResult(task_id, app=celery_app)
            result.revoke(terminate=True)
            logger.info("Task %s cancelled", task_id)
            return True
        except Exception as e:
            logger.error("Failed to cancel task %s: %s", task_id, e)
            return False

    def get_available_actions(self) -> list:
        """Get list of available actions"""
        return list(self._task_registry.keys())

    def _prepare_request(self, action: str, params: dict[str, Any]) -> dict[str, Any]:
        """Prepare task request in standard format"""
        request = {
            "workflow_id": params.get(
                "workflow_id", f"wf_{datetime.now(UTC).timestamp()}"
            ),
            "execution_id": params.get(
                "execution_id", f"ex_{datetime.now(UTC).timestamp()}"
            ),
            "step_name": action,
            "params": params,
            "metadata": params.get("metadata", {}),
        }

        return request
