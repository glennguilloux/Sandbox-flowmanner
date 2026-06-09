"""
N8N Callback Task

Celery task that waits for n8n webhook callbacks with correlation ID support.
Enables async workflow execution with result retrieval.
"""

import json
import logging
import os
from datetime import UTC, datetime
from typing import Any

import redis
from celery import shared_task
from celery.result import AsyncResult

logger = logging.getLogger(__name__)

# Redis connection for callback storage
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
CALLBACK_PREFIX = "n8n:callback:"
EXECUTION_PREFIX = "n8n:execution:"
CALLBACK_TIMEOUT = int(os.getenv("N8N_CALLBACK_TIMEOUT", "300"))  # 5 minutes default


def get_redis_client():
    """Get Redis client for callback storage"""
    return redis.from_url(REDIS_URL, decode_responses=True)


@shared_task(bind=True, max_retries=3, default_retry_delay=5)
def wait_for_n8n_callback(
    self, execution_id: str, timeout: int = None
) -> dict[str, Any]:
    """
    Wait for an n8n webhook callback with the given execution ID.

    This task polls Redis for a callback result, enabling async workflow
    execution where n8n reports results back via webhook.

    Args:
        execution_id: Unique identifier for the n8n execution
        timeout: Maximum time to wait in seconds (default: CALLBACK_TIMEOUT)

    Returns:
        Dict with status, result, and metadata
    """
    timeout = timeout or CALLBACK_TIMEOUT
    redis_client = get_redis_client()
    callback_key = f"{CALLBACK_PREFIX}{execution_id}"

    start_time = datetime.now(UTC)
    poll_interval = 2  # seconds

    logger.info('Waiting for n8n callback: execution_id=%s, timeout=%ss', execution_id, timeout)

    while True:
        elapsed = (datetime.now(UTC) - start_time).total_seconds()

        if elapsed >= timeout:
            logger.warning('N8N callback timeout: execution_id=%s', execution_id)
            return {
                "status": "timeout",
                "execution_id": execution_id,
                "error": f"Callback not received within {timeout} seconds",
                "elapsed_seconds": elapsed,
            }

        # Check for callback in Redis
        callback_data = redis_client.get(callback_key)

        if callback_data:
            try:
                result = json.loads(callback_data)
                logger.info('N8N callback received: execution_id=%s, status=%s', execution_id, result.get('status'))

                # Clean up the callback key
                redis_client.delete(callback_key)

                return {
                    "status": "completed",
                    "execution_id": execution_id,
                    "result": result.get("data"),
                    "workflow_id": result.get("workflow_id"),
                    "n8n_status": result.get("status"),
                    "error": result.get("error"),
                    "metadata": result.get("metadata", {}),
                    "elapsed_seconds": elapsed,
                }
            except json.JSONDecodeError as e:
                logger.error('Invalid callback data for %s: %s', execution_id, e)
                return {
                    "status": "error",
                    "execution_id": execution_id,
                    "error": f"Invalid callback data: {e!s}",
                }

        # Sleep before next poll
        import time

        time.sleep(poll_interval)


@shared_task
def store_n8n_callback(execution_id: str, callback_data: dict[str, Any]) -> bool:
    """
    Store an n8n callback result in Redis.

    Called by the webhook receiver when n8n posts results.

    Args:
        execution_id: The execution ID to store the callback for
        callback_data: The callback payload from n8n

    Returns:
        True if stored successfully
    """
    redis_client = get_redis_client()
    callback_key = f"{CALLBACK_PREFIX}{execution_id}"

    # Store with TTL slightly longer than timeout
    ttl = CALLBACK_TIMEOUT + 60

    callback_json = json.dumps(
        {
            "execution_id": execution_id,
            "workflow_id": callback_data.get("workflow_id"),
            "status": callback_data.get("status", "completed"),
            "data": callback_data.get("data"),
            "error": callback_data.get("error"),
            "metadata": callback_data.get("metadata", {}),
            "received_at": datetime.now(UTC).isoformat(),
        }
    )

    redis_client.setex(callback_key, ttl, callback_json)
    logger.info('Stored n8n callback: execution_id=%s', execution_id)

    return True


@shared_task
def get_n8n_execution_status(execution_id: str) -> dict[str, Any]:
    """
    Get the current status of an n8n execution.

    Args:
        execution_id: The execution ID to check

    Returns:
        Dict with execution status and result if available
    """
    redis_client = get_redis_client()
    callback_key = f"{CALLBACK_PREFIX}{execution_id}"

    callback_data = redis_client.get(callback_key)

    if callback_data:
        return {"status": "completed", "data": json.loads(callback_data)}

    # Check if there's a Celery task waiting
    task_result = AsyncResult(execution_id)
    if task_result.state == "PENDING":
        return {"status": "waiting"}
    elif task_result.state == "SUCCESS":
        return {"status": "completed", "data": task_result.result}
    elif task_result.state == "FAILURE":
        return {"status": "failed", "error": str(task_result.result)}
    else:
        return {"status": task_result.state.lower()}


@shared_task
def cancel_n8n_execution(execution_id: str) -> dict[str, Any]:
    """
    Cancel a waiting n8n execution.

    Args:
        execution_id: The execution ID to cancel

    Returns:
        Dict with cancellation status
    """
    redis_client = get_redis_client()
    callback_key = f"{CALLBACK_PREFIX}{execution_id}"

    # Store cancellation result
    cancel_data = json.dumps(
        {
            "status": "cancelled",
            "execution_id": execution_id,
            "cancelled_at": datetime.now(UTC).isoformat(),
        }
    )

    redis_client.setex(callback_key, 60, cancel_data)

    logger.info('Cancelled n8n execution: %s', execution_id)

    return {"status": "cancelled", "execution_id": execution_id}


@shared_task
def cleanup_stale_callbacks() -> int:
    """
    Periodic task to clean up stale callback entries.

    Returns:
        Number of entries cleaned up
    """
    redis_client = get_redis_client()

    # Find all callback keys
    keys = redis_client.keys(f"{CALLBACK_PREFIX}*")
    cleaned = 0

    for key in keys:
        ttl = redis_client.ttl(key)
        if ttl == -1:  # No expiry set
            redis_client.expire(key, 300)  # Set 5 min expiry
            cleaned += 1

    if cleaned > 0:
        logger.info('Cleaned up %s stale callback entries', cleaned)

    return cleaned
