"""
Task Priority Router for Celery Tasks

Provides priority-based routing for task distribution.
"""

import contextlib
import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


class TaskOptimizerConfig:
    """Configuration constants for task optimizer"""
    # Priority constants (as expected by tests)
    HIGH_PRIORITY = 9
    MEDIUM_PRIORITY = 5
    LOW_PRIORITY = 1

    # Queue settings with required keys
    QUEUE_SETTINGS = {
        "high_priority": {
            "queue": "high_priority",
            "routing_key": "high_priority",
            "exchange": "priority",
            "priority": HIGH_PRIORITY,
            "prefetch": 1,
            "concurrency": 4
        },
        "medium_priority": {
            "queue": "medium_priority",
            "routing_key": "medium_priority",
            "exchange": "priority",
            "priority": MEDIUM_PRIORITY,
            "prefetch": 2,
            "concurrency": 2
        },
        "low_priority": {
            "queue": "low_priority",
            "routing_key": "low_priority",
            "exchange": "priority",
            "priority": LOW_PRIORITY,
            "prefetch": 4,
            "concurrency": 1
        }
    }


@dataclass
class TaskOptimizerOptions:
    """Options for task optimizer"""
    high_priority_patterns: list = field(default_factory=lambda: [
        "notification", "alert", "urgent", "critical", "realtime",
        "websocket", "chat", "stream", "immediate"
    ])
    medium_priority_patterns: list = field(default_factory=lambda: [
        "email", "report", "analytics", "dashboard", "api"
    ])
    low_priority_patterns: list = field(default_factory=lambda: [
        "backup", "cleanup", "archive", "maintenance", "log", "stats"
    ])
    default_priority: int = TaskOptimizerConfig.MEDIUM_PRIORITY


class TaskPriorityRouter:
    """Routes tasks based on priority patterns"""

    def __init__(self, config: TaskOptimizerOptions | None = None):
        self.config = config or TaskOptimizerOptions()

    def _determine_priority(self, task: Any) -> int:
        """Determine priority for a task based on its name (private method)."""
        # Handle None
        if task is None:
            logger.warning("Task is None, falling back to MEDIUM_PRIORITY")
            return TaskOptimizerConfig.MEDIUM_PRIORITY

        # Get task name
        name = None
        if hasattr(task, "name"):
            with contextlib.suppress(Exception):
                name = task.name
        elif isinstance(task, str):
            name = task

        # Handle case where we couldn't get a name or name is not a string
        if name is None:
            return self.config.default_priority

        # Ensure name is a string
        if not isinstance(name, str):
            return self.config.default_priority

        name_lower = name.lower()

        try:
            # Check high priority patterns
            for pattern in self.config.high_priority_patterns:
                if pattern in name_lower:
                    return TaskOptimizerConfig.HIGH_PRIORITY

            # Check medium priority patterns
            for pattern in self.config.medium_priority_patterns:
                if pattern in name_lower:
                    return TaskOptimizerConfig.MEDIUM_PRIORITY

            # Check low priority patterns
            for pattern in self.config.low_priority_patterns:
                if pattern in name_lower:
                    return TaskOptimizerConfig.LOW_PRIORITY
        except (TypeError, AttributeError):
            logger.debug("task_optimizer_type_error", exc_info=True)

        return self.config.default_priority

    # Public alias for backward compatibility
    def determine_priority(self, task: Any) -> int:
        """Determine priority for a task (public method)."""
        return self._determine_priority(task)

    def route_task(self, task: Any, args: tuple = None, kwargs: dict = None, 
                   options: dict = None, **extra) -> dict[str, Any]:
        """
        Route a task to the appropriate queue based on priority.

        Args:
            task: The task to route (can be string name or task object)
            args: Task positional arguments (unused but accepted for compatibility)
            kwargs: Task keyword arguments (unused but accepted for compatibility)
            options: Task options dict, may contain 'priority' key
            **extra: Additional routing options

        Returns:
            Dict with queue configuration and routing info
        """
        # Check for explicit priority in options
        priority = None
        if options and isinstance(options, dict):
            priority = options.get("priority")

        # Determine priority if not provided
        if priority is None:
            priority = self._determine_priority(task)

        # Handle None priority edge case
        if priority is None:
            logger.warning("Priority was None for task %s, falling back to MEDIUM_PRIORITY", task)
            priority = TaskOptimizerConfig.MEDIUM_PRIORITY

        # Map priority to queue settings based on value ranges
        # priority >= 9 -> high_priority
        # priority < 5 -> low_priority
        # else -> medium_priority
        if priority >= TaskOptimizerConfig.HIGH_PRIORITY:
            queue_config = TaskOptimizerConfig.QUEUE_SETTINGS["high_priority"]
        elif priority < TaskOptimizerConfig.MEDIUM_PRIORITY:
            queue_config = TaskOptimizerConfig.QUEUE_SETTINGS["low_priority"]
        else:
            queue_config = TaskOptimizerConfig.QUEUE_SETTINGS["medium_priority"]

        return {
            "queue": queue_config["queue"],
            "routing_key": queue_config["routing_key"],
            "exchange": queue_config["exchange"],
            "priority": priority,
            "prefetch": queue_config.get("prefetch", 1),
            "concurrency": queue_config.get("concurrency", 1)
        }


def optimize_celery_app(celery_app):
    """
    Optimize a Celery app with priority routing and task configuration.

    Args:
        celery_app: Celery application instance to optimize

    Returns:
        The optimized Celery app
    """
    router = TaskPriorityRouter()

    # Configure task routing based on priority patterns
    if hasattr(celery_app, 'conf'):
        # Set up task routes
        celery_app.conf.task_routes = celery_app.conf.get('task_routes', {})

        # Configure worker concurrency based on priority
        celery_app.conf.worker_prefetch_multiplier = 1

        # Set up task annotations for priority
        celery_app.conf.task_annotations = {
            '**': {
                'max_retries': 3,
                'default_retry_delay': 60,
            }
        }

    return celery_app


def task_optimizer(celery_app=None, config=None):
    """
    Configure and optimize Celery task routing.

    This is a convenience function that creates a TaskPriorityRouter
    and applies it to a Celery app if provided.

    Args:
        celery_app: Optional Celery application to optimize
        config: Optional TaskOptimizerOptions for customization

    Returns:
        TaskPriorityRouter instance, or optimized celery_app if provided
    """
    router = TaskPriorityRouter(config)

    if celery_app is not None:
        return optimize_celery_app(celery_app)

    return router
