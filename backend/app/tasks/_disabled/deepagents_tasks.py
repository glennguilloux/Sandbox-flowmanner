# mypy: disable-error-code=attr-defined
"""
DeepAgents Celery tasks for async agent execution.
"""

import asyncio
import json
import logging
from datetime import UTC, datetime
from typing import Any

from app.services.deepagents_integration import get_deepagents_service, is_available
from app.services.langgraph.llm_config import get_llm
from app.settings import Config
from app.tasks.base_task import BaseTask
from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(base=BaseTask, bind=True, name="deepagents.execute")
def deepagents_execute_task(
    self,
    message: str,
    session_id: str | None = None,
    model_id: str | None = None,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Execute DeepAgents agent asynchronously.

    Args:
        message: User message to process
        session_id: Optional session ID for conversation continuity
        model_id: Optional model ID for LLM
        context: Optional context dictionary

    Returns:
        Agent response dictionary
    """
    logger.info("Starting DeepAgents task for message: %s...", message[:100])

    # Check if DeepAgents is available
    if not is_available():
        raise RuntimeError("DeepAgents is not available")

    # Create task record
    task_record = self.create_task_record(
        task_id=self.request.id,
        task_name="deepagents.execute",
        args=(message,),
        kwargs={"session_id": session_id, "model_id": model_id, "context": context},
    )

    try:
        # Update task status
        task_record.status = "started"
        task_record.started_at = datetime.now(UTC)
        self.db.commit()

        # Run async execution
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        # Get LLM
        llm = loop.run_until_complete(get_llm(model_id=model_id, use_fallback=True))

        if not llm:
            raise RuntimeError("No LLM available")

        # Get DeepAgents service
        service = loop.run_until_complete(
            get_deepagents_service(
                llm=llm,
                backend_type=Config.DEEPAGENTS_BACKEND_TYPE,
                filesystem_root=Config.DEEPAGENTS_FS_ROOT,
                enable_long_term_memory=Config.DEEPAGENTS_LONG_TERM_MEMORY,
                interrupt_on={} if not Config.DEEPAGENTS_HUMAN_IN_LOOP else None,
            )
        )

        if not service:
            raise RuntimeError("Failed to initialize DeepAgents service")

        # Execute DeepAgents
        result = service.invoke(message=message, session_id=session_id)

        loop.close()

        # Update task with result
        task_record.result = json.dumps(result)
        task_record.completed_at = datetime.now(UTC)
        self.db.commit()

        logger.info("DeepAgents task completed successfully: %s", self.request.id)
        return result

    except Exception as e:
        logger.error("DeepAgents task failed: %s", e, exc_info=True)

        # Update task with error
        task_record.status = "failed"
        task_record.error = str(e)
        task_record.completed_at = datetime.now(UTC)
        self.db.commit()

        raise


@celery_app.task(base=BaseTask, bind=True, name="deepagents.stream")
def deepagents_stream_task(
    self,
    message: str,
    session_id: str | None = None,
    model_id: str | None = None,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Execute DeepAgents with streaming (returns accumulated result).

    Note: This task accumulates all stream chunks and returns them as a single result.
    For real-time streaming, use the /stream endpoint instead.

    Args:
        message: User message to process
        session_id: Optional session ID for conversation continuity
        model_id: Optional model ID for LLM
        context: Optional context dictionary

    Returns:
        Accumulated stream response dictionary
    """
    logger.info("Starting DeepAgents stream task for message: %s...", message[:100])

    # Check if DeepAgents is available
    if not is_available():
        raise RuntimeError("DeepAgents is not available")

    # Create task record
    task_record = self.create_task_record(
        task_id=self.request.id,
        task_name="deepagents.stream",
        args=(message,),
        kwargs={"session_id": session_id, "model_id": model_id, "context": context},
    )

    try:
        # Update task status
        task_record.status = "started"
        task_record.started_at = datetime.now(UTC)
        self.db.commit()

        # Run async execution
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        # Get LLM
        llm = loop.run_until_complete(get_llm(model_id=model_id, use_fallback=True))

        if not llm:
            raise RuntimeError("No LLM available")

        # Get DeepAgents service
        service = loop.run_until_complete(
            get_deepagents_service(
                llm=llm,
                backend_type=Config.DEEPAGENTS_BACKEND_TYPE,
                filesystem_root=Config.DEEPAGENTS_FS_ROOT,
                enable_long_term_memory=Config.DEEPAGENTS_LONG_TERM_MEMORY,
            )
        )

        if not service:
            raise RuntimeError("Failed to initialize DeepAgents service")

        # Stream and accumulate chunks
        chunks = []

        async def collect_chunks():
            async for chunk in service.astream(message=message, session_id=session_id):
                chunks.append(chunk)

        loop.run_until_complete(collect_chunks())
        loop.close()

        # Build result from chunks
        result = {
            "success": True,
            "chunks": chunks,
            "chunk_count": len(chunks),
            "session_id": session_id,
            "timestamp": datetime.now(UTC).isoformat(),
        }

        # Update task with result
        task_record.result = json.dumps(result)
        task_record.completed_at = datetime.now(UTC)
        self.db.commit()

        logger.info("DeepAgents stream task completed successfully: %s", self.request.id)
        return result

    except Exception as e:
        logger.error("DeepAgents stream task failed: %s", e, exc_info=True)

        # Update task with error
        task_record.status = "failed"
        task_record.error = str(e)
        task_record.completed_at = datetime.now(UTC)
        self.db.commit()

        raise


@celery_app.task(base=BaseTask, bind=True, name="deepagents.batch_execute")
def deepagents_batch_execute_task(
    self,
    messages: list,
    session_id: str | None = None,
    model_id: str | None = None,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Execute multiple DeepAgents messages as a batch.

    Args:
        messages: List of messages to process
        session_id: Optional session ID
        model_id: Optional model ID for LLM
        context: Optional context dictionary

    Returns:
        Batch processing results
    """
    logger.info("Starting DeepAgents batch processing for %s messages", len(messages))

    # Check if DeepAgents is available
    if not is_available():
        raise RuntimeError("DeepAgents is not available")

    # Create task record
    task_record = self.create_task_record(
        task_id=self.request.id,
        task_name="deepagents.batch_execute",
        args=(messages,),
        kwargs={"session_id": session_id, "model_id": model_id, "context": context},
    )

    try:
        # Update task status
        task_record.status = "started"
        task_record.started_at = datetime.now(UTC)
        self.db.commit()

        results = []
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        # Get LLM
        llm = loop.run_until_complete(get_llm(model_id=model_id, use_fallback=True))

        if not llm:
            raise RuntimeError("No LLM available")

        # Get DeepAgents service
        service = loop.run_until_complete(
            get_deepagents_service(
                llm=llm,
                backend_type=Config.DEEPAGENTS_BACKEND_TYPE,
                filesystem_root=Config.DEEPAGENTS_FS_ROOT,
                enable_long_term_memory=Config.DEEPAGENTS_LONG_TERM_MEMORY,
                interrupt_on={} if not Config.DEEPAGENTS_HUMAN_IN_LOOP else None,
            )
        )

        if not service:
            raise RuntimeError("Failed to initialize DeepAgents service")

        # Process each message
        for i, message in enumerate(messages):
            logger.info("Processing batch message %s/%s", i + 1, len(messages))

            try:
                result = service.invoke(message=message, session_id=session_id)
                results.append({"message": message, "result": result, "success": True})
            except Exception as e:
                logger.error("Failed to process batch message %s: %s", i + 1, e)
                results.append({"message": message, "error": str(e), "success": False})

        loop.close()

        # Update task with result
        batch_result = {
            "processed": len(results),
            "successful": sum(1 for r in results if r.get("success", False)),
            "failed": sum(1 for r in results if not r.get("success", False)),
            "results": results,
        }
        task_record.result = json.dumps(batch_result)
        task_record.completed_at = datetime.now(UTC)
        self.db.commit()

        logger.info("DeepAgents batch processing completed: %s messages", len(results))
        return batch_result

    except Exception as e:
        logger.error("DeepAgents batch processing failed: %s", e, exc_info=True)

        # Update task with error
        task_record.status = "failed"
        task_record.error = str(e)
        task_record.completed_at = datetime.now(UTC)
        self.db.commit()

        raise
