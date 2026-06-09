# mypy: disable-error-code=attr-defined
import logging
from datetime import UTC, datetime

from celery import shared_task

from app.database import SessionLocal
from app.models.models import WorkflowRuns
from app.services.monitoring_service import MonitoringService

logger = logging.getLogger(__name__)


@shared_task(bind=True, ignore_result=False)
def sync_workflow_status(self):
    """Synchronize workflow status and handle stuck workflows."""
    logger.info("Starting workflow sync for task %s", self.request.id)

    db = SessionLocal()
    try:
        # Get all running/pending workflow runs
        running_workflows = (
            db.query(WorkflowRuns)
            .filter(WorkflowRuns.status.in_(["running", "pending"]))
            .all()
        )

        updated_count = 0
        for workflow in running_workflows:
            # Check for stuck workflows (running > 2 hours)
            if workflow.started_at:
                runtime = (datetime.now(UTC) - workflow.started_at).total_seconds()
                if runtime > 7200 and workflow.status == "running":  # 2 hours
                    workflow.status = "timed_out"
                    logger.warning(
                        "Workflow run %s marked as timed out after %ss",
                        workflow.run_id,
                        runtime,
                    )
                    updated_count += 1

        db.commit()
        logger.info(
            "Synced %s workflows, %s timed out", len(running_workflows), updated_count
        )
        return {"synced": len(running_workflows), "timed_out": updated_count}

    except Exception as e:
        logger.error("Error in sync_workflow_status: %s", e)
        raise
    finally:
        db.close()


@shared_task(bind=True, ignore_result=False)
def update_system_metrics(self):
    """Update system-level performance and health metrics."""
    logger.info("Updating system metrics for task %s", self.request.id)

    try:
        monitoring = MonitoringService()

        # Update performance metrics
        metrics = {}

        # Workflow metrics
        metrics.update(monitoring.update_workflow_metrics())

        # System health metrics
        metrics.update(monitoring.update_system_health())

        # Resource usage
        metrics.update(monitoring.update_resource_usage())

        logger.info("System metrics updated successfully")
        return {"metrics": metrics, "timestamp": datetime.now(UTC).isoformat()}

    except Exception as e:
        logger.error("Error in update_system_metrics: %s", e)
        raise
