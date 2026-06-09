"""
LangGraph Celery tasks for async agent execution.
"""

import asyncio
import json
import logging
from datetime import UTC, datetime
from typing import Any

from app.services.langgraph.agent import LangGraphAgent
from app.services.langgraph.tool_handlers.registry import ToolHandlerRegistry
from app.settings import Config
from app.tasks.base_task import BaseTask
from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(base=BaseTask, bind=True, name="langgraph.execute")
def langgraph_execute_task(
    self,
    message: str,
    session_id: str | None = None,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Execute LangGraph agent asynchronously.

    Args:
        message: User message to process
        session_id: Optional session ID for conversation continuity
        context: Optional context dictionary

    Returns:
        Agent response dictionary
    """
    logger.info("Starting LangGraph task for message: %s...", message[:100])

    # Create task record
    task_record = self.create_task_record(
        task_id=self.request.id,
        task_name="langgraph.execute",
        args=(message,),
        kwargs={"session_id": session_id, "context": context},
    )

    try:
        # Update task status
        task_record.status = "started"
        task_record.started_at = datetime.now(UTC)
        self.db.commit()

        # Run async agent
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        # Initialize agent
        agent = LangGraphAgent(
            model_name=Config.LLM_MODEL,
            temperature=Config.LLM_TEMPERATURE,
            max_tokens=Config.LLM_MAX_TOKENS,
            llamacpp_url=Config.LLAMACPP_URL,
        )

        # Process message
        result = loop.run_until_complete(
            agent.process_message(message, session_id, context or {})  # type: ignore[arg-type]
        )

        # Close agent
        loop.run_until_complete(agent.close())
        loop.close()

        # Update task with result
        task_record.result = json.dumps(result)
        task_record.completed_at = datetime.now(UTC)
        self.db.commit()

        logger.info("LangGraph task completed successfully: %s", self.request.id)
        return result

    except Exception as e:
        logger.error("LangGraph task failed: %s", e, exc_info=True)

        # Update task with error
        task_record.status = "failed"
        task_record.error = str(e)
        task_record.completed_at = datetime.now(UTC)
        self.db.commit()

        raise


@celery_app.task(base=BaseTask, bind=True, name="langgraph.approval")
def langgraph_approval_task(
    self, session_id: str, approval: bool, notes: str | None = None
) -> dict[str, Any]:
    """
    Handle LangGraph approval asynchronously.

    Args:
        session_id: Session ID to approve/reject
        approval: True to approve, False to reject
        notes: Optional notes for the approval

    Returns:
        Approval result dictionary
    """
    logger.info("Processing LangGraph approval for session: %s", session_id)

    # Create task record
    task_record = self.create_task_record(
        task_id=self.request.id,
        task_name="langgraph.approval",
        args=(session_id, approval),
        kwargs={"notes": notes},
    )

    try:
        # Update task status
        task_record.status = "started"
        task_record.started_at = datetime.now(UTC)
        self.db.commit()

        # Run async approval
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        # Initialize agent
        agent = LangGraphAgent(
            model_name=Config.LLM_MODEL,
            temperature=Config.LLM_TEMPERATURE,
            max_tokens=Config.LLM_MAX_TOKENS,
            llamacpp_url=Config.LLAMACPP_URL,
        )

        # Handle approval
        result = loop.run_until_complete(
            agent.handle_approval(session_id, approval, notes)  # type: ignore[arg-type]
        )

        # Close agent
        loop.run_until_complete(agent.close())
        loop.close()

        # Update task with result
        task_record.result = json.dumps(result)
        task_record.completed_at = datetime.now(UTC)
        self.db.commit()

        logger.info("LangGraph approval task completed: %s", self.request.id)
        return result

    except Exception as e:
        logger.error("LangGraph approval task failed: %s", e, exc_info=True)

        # Update task with error
        task_record.status = "failed"
        task_record.error = str(e)
        task_record.completed_at = datetime.now(UTC)
        self.db.commit()

        raise


@celery_app.task(base=BaseTask, bind=True, name="langgraph.tool_execution")
def langgraph_tool_execution_task(
    self,
    tool_name: str,
    parameters: dict[str, Any],
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Execute a single LangGraph tool asynchronously.

    Args:
        tool_name: Name of the tool to execute
        parameters: Tool parameters
        context: Optional execution context

    Returns:
        Tool execution result
    """
    logger.info("Executing LangGraph tool: %s", tool_name)

    # Create task record
    task_record = self.create_task_record(
        task_id=self.request.id,
        task_name="langgraph.tool_execution",
        args=(tool_name,),
        kwargs={"parameters": parameters, "context": context},
    )

    try:
        # Update task status
        task_record.status = "started"
        task_record.started_at = datetime.now(UTC)
        self.db.commit()

        # Run async tool execution
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        # Initialize tool registry
        registry = ToolHandlerRegistry()

        # Execute tool
        result = loop.run_until_complete(
            registry.execute_tool(tool_name, parameters, context or {})  # type: ignore[attr-defined]
        )

        # Close registry
        loop.run_until_complete(registry.close_all())
        loop.close()

        # Update task with result
        task_record.result = json.dumps(result)
        task_record.completed_at = datetime.now(UTC)
        self.db.commit()

        logger.info("LangGraph tool execution completed: %s", tool_name)
        return result

    except Exception as e:
        logger.error("LangGraph tool execution failed: %s", e, exc_info=True)

        # Update task with error
        task_record.status = "failed"
        task_record.error = str(e)
        task_record.completed_at = datetime.now(UTC)
        self.db.commit()

        raise


@celery_app.task(base=BaseTask, bind=True, name="langgraph.batch_process")
def langgraph_batch_process_task(
    self,
    messages: list,
    session_id: str | None = None,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Process multiple LangGraph messages as a batch.

    Args:
        messages: List of messages to process
        session_id: Optional session ID
        context: Optional context dictionary

    Returns:
        Batch processing results
    """
    logger.info("Starting LangGraph batch processing for %s messages", len(messages))

    # Create task record
    task_record = self.create_task_record(
        task_id=self.request.id,
        task_name="langgraph.batch_process",
        args=(messages,),
        kwargs={"session_id": session_id, "context": context},
    )

    try:
        # Update task status
        task_record.status = "started"
        task_record.started_at = datetime.now(UTC)
        self.db.commit()

        results = []
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        # Initialize agent
        agent = LangGraphAgent(
            model_name=Config.LLM_MODEL,
            temperature=Config.LLM_TEMPERATURE,
            max_tokens=Config.LLM_MAX_TOKENS,
            llamacpp_url=Config.LLAMACPP_URL,
        )

        # Process each message
        for i, message in enumerate(messages):
            logger.info("Processing batch message %s/%s", i + 1, len(messages))

            try:
                result = loop.run_until_complete(
                    agent.process_message(message, session_id, context or {})  # type: ignore[arg-type]
                )
                results.append({"message": message, "result": result, "success": True})
            except Exception as e:
                logger.error("Failed to process batch message %s: %s", i + 1, e)
                results.append({"message": message, "error": str(e), "success": False})

        # Close agent
        loop.run_until_complete(agent.close())
        loop.close()

        # Update task with result
        task_record.result = json.dumps({"processed": len(results), "results": results})
        task_record.completed_at = datetime.now(UTC)
        self.db.commit()

        logger.info("LangGraph batch processing completed: %s messages", len(results))
        return {
            "processed": len(results),
            "successful": sum(1 for r in results if r.get("success", False)),
            "failed": sum(1 for r in results if not r.get("success", False)),
            "results": results,
        }

    except Exception as e:
        logger.error("LangGraph batch processing failed: %s", e, exc_info=True)

        # Update task with error
        task_record.status = "failed"
        task_record.error = str(e)
        task_record.completed_at = datetime.now(UTC)
        self.db.commit()

        raise
