"""
Flowmanner Flow Service - Core orchestration

Handles the core logic for /flow/run endpoint:
- Project resolution (lookup or create)
- Run creation and tracking
- Execution coordination
- Result storage
"""
import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.graph import Workflow, WorkflowExecution
from app.services.flow.execution_router import ExecutionRouter
from app.services.flow.project_resolver import ProjectResolver

logger = logging.getLogger(__name__)


class FlowService:
    """Core service for /flow/run endpoint orchestration."""
    
    def __init__(self, db: AsyncSession):
        self.db = db
        self.execution_router = ExecutionRouter()
        self.project_resolver = ProjectResolver()
    
    async def resolve_project(
        self,
        project_slug: str | None,
        goal: str,
        creator_email: str | None = None
    ) -> dict:
        """
        Resolve existing project or create new one.
        
        Returns project dict with id, slug, name, config.
        """
        
        if project_slug:
            # Look up existing project
            result = await self.db.execute(
                select(Workflow).where(Workflow.name == project_slug)
            )
            project = result.scalar_one_or_none()
            
            if not project:
                raise ValueError(f"Project '{project_slug}' not found")
            
            logger.info(f"Found existing project: {project.name}")
            return {
                "id": str(project.id),
                "slug": project.name,
                "name": project.name,
                "config": project.graph_definition or {}
            }
        else:
            # Create new project with auto-generated slug
            slug = self.project_resolver.generate_slug(goal)
            name = self.project_resolver.infer_name(goal)
            
            # Create new project
            project_id = uuid.uuid4()
            workflow = Workflow(
                id=project_id,
                name=name,
                description=goal[:200],
                status="active",
            )
            self.db.add(workflow)
            await self.db.commit()
            
            logger.info(f"Created new project: {slug}")
            return {
                "id": str(project_id),
                "slug": slug,
                "name": name,
                "config": {}
            }
    
    async def create_run(
        self,
        project_id: str,
        goal: str,
        trigger: str,
        sender_email: str | None = None,
        metadata: dict | None = None
    ) -> dict:
        """
        Create a new Run record.
        
        Returns run dict with id, status, created_at.
        """
        run_id = uuid.uuid4()
        now = datetime.now(UTC)
        
        execution = WorkflowExecution(
            id=run_id,
            workflow_id=uuid.UUID(project_id) if project_id else None,
            input_data={"goal": goal},
            status="pending",
        )
        self.db.add(execution)
        await self.db.commit()
        
        logger.info(f"Created run: {run_id} for project: {project_id}")
        return {
            "id": str(run_id),
            "status": "pending",
            "created_at": now
        }
    
    async def execute(
        self,
        run_id: str,
        project: dict,
        request: dict,
    ) -> dict:
        """Execute the flow synchronously."""
        
        # Update run status using WorkflowExecution
        await self._update_run_status(run_id, "running")
        now = datetime.now(UTC)
        
        try:
            # Route to appropriate executor
            result = await self.execution_router.route_and_execute(
                project=project,
                goal=request.get("goal", ""),
                mode=request.get("mode", "autonomous"),
                resources=request.get("resources", {})
            )
            
            # Store result
            output = result.get("content", "")
            await self._update_run_result(run_id, "completed", output, result.get("metadata", {}))
            
            duration_ms = int((datetime.now(UTC) - now).total_seconds() * 1000)
            
            logger.info(f"Run {run_id} completed in {duration_ms}ms")
            return {
                "content": output,
                "type": result.get("type", "markdown"),
                "metadata": result.get("metadata", {})
            }
            
        except Exception as e:
            error_msg = str(e)
            await self._update_run_error(run_id, "error", error_msg)
            logger.error(f"Run {run_id} failed: {error_msg}")
            raise
    
    async def execute_async(self, run_id: str, project: dict, request: dict):
        """Execute the flow asynchronously (background task)."""
        
        try:
            result = await self.execute(run_id, project, request)
            
            # Trigger callback if provided
            callback_url = request.get("callback_url")
            if callback_url:
                await self._send_callback(callback_url, run_id, result)
                
        except Exception as e:
            logger.error(f"Async execution failed for run {run_id}: {e}")
    
    async def get_run(self, run_id: str) -> dict | None:
        """Get run by ID."""
        result = await self.db.execute(
            select(WorkflowExecution).where(WorkflowExecution.id == uuid.UUID(run_id))
        )
        run = result.scalar_one_or_none()
        
        if not run:
            return None
        
        return {
            "id": str(run.id),
            "workflow_id": str(run.workflow_id) if run.workflow_id else None,
            "input": run.input_data,
            "output": run.output_data,
            "status": run.status,
            "error_message": run.error_message,
        }
    
    async def _update_run_status(self, run_id: str, status: str):
        """Update run status."""
        updates = {"status": status}
        if status == "running":
            updates["started_at"] = datetime.now(UTC)
        
        await self.db.execute(
            update(WorkflowExecution)
            .where(WorkflowExecution.id == uuid.UUID(run_id))
            .values(**updates)
        )
        await self.db.commit()
    
    async def _update_run_result(
        self,
        run_id: str,
        status: str,
        output: str,
        metadata: dict
    ):
        """Update run with result."""
        now = datetime.now(UTC)
        
        # Get start time to calculate duration
        run_data = await self.get_run(run_id)
        duration_ms = None
        if run_data and run_data.get("started_at"):
            duration_ms = int((now - run_data["started_at"]).total_seconds() * 1000)
        
        await self.db.execute(
            update(WorkflowExecution)
            .where(WorkflowExecution.id == uuid.UUID(run_id))
            .values(
                status=status,
                output_data=output,
                completed_at=now,
            )
        )
        await self.db.commit()
    
    async def _update_run_error(self, run_id: str, status: str, error_message: str):
        """Update run with error."""
        await self.db.execute(
            update(WorkflowExecution)
            .where(WorkflowExecution.id == uuid.UUID(run_id))
            .values(
                status=status,
                error_message=error_message,
                completed_at=datetime.now(UTC)
            )
        )
        await self.db.commit()
    
    async def _send_callback(self, callback_url: str, run_id: str, result: dict):
        """Send result to callback URL."""
        import httpx
        try:
            async with httpx.AsyncClient() as client:
                await client.post(callback_url, json={
                    "run_id": run_id,
                    "status": "completed",
                    "result": result
                })
        except Exception as e:
            logger.error(f"Callback failed for run {run_id}: {e}")
    
    async def _queue_email_reply(self, run_id: str):
        """Queue email reply for email-triggered runs."""
        # This will integrate with the email gateway
        # For now, just log
        logger.info(f"Email reply queued for run {run_id}")


# Legacy import kept for backward compat (H4.2)
# Project and Run models from flow_schemas are now Workflow and WorkflowExecution
