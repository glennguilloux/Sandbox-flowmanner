"""
Base task class with common functionality for all Celery tasks.
"""

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from celery import Task

from app.database import SessionLocal
from app.models import CeleryTask, TaskStatus

logger = logging.getLogger(__name__)


class BaseTask(Task):
    """
    Base task class with retry logic, error handling, and status tracking.
    """

    # Default retry settings
    autoretry_for = (Exception,)
    max_retries = 3
    retry_backoff = True
    retry_backoff_max = 600  # 10 minutes
    retry_jitter = True

    # Task timeouts
    time_limit = 300  # 5 minutes
    soft_time_limit = 240  # 4 minutes

    def __init__(self):
        super().__init__()
        self.db = SessionLocal()

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        """Handle task failure."""
        logger.error("Task %s failed: %s", task_id, exc)

        try:
            # Update task status in database
            task_record = (
                self.db.query(CeleryTask).filter(CeleryTask.task_id == task_id).first()
            )

            if task_record:
                task_record.status = TaskStatus.FAILED
                task_record.error = str(exc)
                task_record.completed_at = datetime.now(UTC)
                self.db.commit()
        except Exception as db_error:
            logger.error("Failed to update task status in database: %s", db_error)
            self.db.rollback()

        # Call parent failure handler
        super().on_failure(exc, task_id, args, kwargs, einfo)

    def on_success(self, retval, task_id, args, kwargs):
        """Handle task success."""
        logger.info("Task %s completed successfully", task_id)

        try:
            # Update task status in database
            task_record = (
                self.db.query(CeleryTask).filter(CeleryTask.task_id == task_id).first()
            )

            if task_record:
                task_record.status = TaskStatus.COMPLETED
                task_record.result = str(retval)
                task_record.completed_at = datetime.now(UTC)
                self.db.commit()
        except Exception as db_error:
            logger.error("Failed to update task status in database: %s", db_error)
            self.db.rollback()

        super().on_success(retval, task_id, args, kwargs)

    def on_retry(self, exc, task_id, args, kwargs, einfo):
        """Handle task retry."""
        logger.warning("Task %s retrying: %s", task_id, exc)

        try:
            # Update task status in database
            task_record = (
                self.db.query(CeleryTask).filter(CeleryTask.task_id == task_id).first()
            )

            if task_record:
                task_record.status = TaskStatus.RETRYING
                task_record.retry_count = (
                    task_record.retry_count + 1 if task_record.retry_count else 1
                )
                task_record.error = str(exc)
                self.db.commit()
        except Exception as db_error:
            logger.error("Failed to update task status in database: %s", db_error)
            self.db.rollback()

        super().on_retry(exc, task_id, args, kwargs, einfo)

    def create_task_record(
        self, task_id: str, task_name: str, args: tuple, kwargs: dict[str, Any]
    ) -> CeleryTask:
        """Create a task record in the database."""
        task_record = CeleryTask(
            task_id=task_id,
            task_name=task_name,
            status=TaskStatus.PENDING,
            args=str(args),
            kwargs=str(kwargs),
            created_at=datetime.now(UTC),
        )

        self.db.add(task_record)
        self.db.commit()
        return task_record

    def __del__(self):
        """Clean up database session."""
        if hasattr(self, "db"):
            self.db.close()


def cleanup_old_tasks():
    """Clean up old completed tasks from the database."""
    from celery_app import celery_app

    @celery_app.task(base=BaseTask, bind=True)
    def _cleanup_old_tasks(self):
        try:
            cutoff_time = datetime.now(UTC) - timedelta(days=7)

            # Delete tasks older than 7 days
            deleted_count = (
                self.db.query(CeleryTask)
                .filter(CeleryTask.created_at < cutoff_time)
                .delete()
            )

            self.db.commit()
            logger.info("Cleaned up %s old tasks", deleted_count)
            return {"cleaned": deleted_count}
        except Exception as e:
            logger.error("Failed to cleanup old tasks: %s", e)
            self.db.rollback()
            raise

    return _cleanup_old_tasks


def health_check():
    """Health check task for monitoring."""
    from celery_app import celery_app

    @celery_app.task(base=BaseTask, bind=True)
    def _health_check(self):
        return {
            "status": "healthy",
            "timestamp": datetime.now(UTC).isoformat(),
            "worker": self.request.hostname,
            "task_count": self.db.query(CeleryTask).count(),
        }

    return _health_check
