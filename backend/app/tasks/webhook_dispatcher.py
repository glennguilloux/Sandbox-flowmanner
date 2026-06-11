from typing import Any

#!/usr/bin/env python3
"""
Webhook Dispatcher Task

Celery task for delivering webhook events to subscribed endpoints.
Supports HMAC signatures, retries, and failure handling.
"""

import asyncio
import hashlib
import hmac
import json
import logging
import time
import uuid
from datetime import UTC, datetime, timedelta

import aiohttp
from celery import shared_task
from sqlalchemy import and_
from sqlalchemy.orm import Session

from ..database import SessionLocal
from ..models.webhook_subscription import (
    WebhookDelivery,
    WebhookEventType,
    WebhookSubscription,
)

logger = logging.getLogger(__name__)


# Maximum retries before disabling a subscription
MAX_CONSECUTIVE_FAILURES = 5


def generate_hmac_signature(secret: str, payload: str) -> str:
    """Generate HMAC-SHA256 signature for webhook payload"""
    if not secret:
        return ""
    return hmac.new(secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()


def get_subscriptions_for_event(event_type: str, db: Session) -> list:
    """Get all active subscriptions for a given event type"""
    # Query subscriptions where event_types contains the event_type
    subscriptions = (
        db.query(WebhookSubscription)
        .filter(
            and_(
                WebhookSubscription.is_active == True,
                WebhookSubscription.event_types.contains([event_type]),
            )
        )
        .all()
    )
    return subscriptions


async def deliver_webhook_async(
    subscription: WebhookSubscription,
    event_type: str,
    event_id: str,
    payload: dict,
    db: Session,
) -> bool:
    """Deliver a webhook to a single subscription endpoint"""

    # Create delivery record
    delivery = WebhookDelivery(
        subscription_id=subscription.id,
        event_type=event_type,
        event_id=event_id,
        payload=payload,
        status="pending",
    )
    db.add(delivery)
    db.commit()
    db.refresh(delivery)

    # Prepare payload with metadata
    webhook_payload = {
        "id": str(uuid.uuid4()),
        "event": event_type,
        "event_id": event_id,
        "timestamp": datetime.now(UTC).isoformat(),
        "data": payload,
    }

    payload_str = json.dumps(webhook_payload)

    # Generate signature if secret is configured
    signature = generate_hmac_signature(subscription.secret, payload_str) if subscription.secret else None

    # Prepare headers
    headers = {
        "Content-Type": "application/json",
        "X-Webhook-Event": event_type,
        "X-Webhook-ID": webhook_payload["id"],
        "X-Webhook-Timestamp": webhook_payload["timestamp"],
    }

    if signature:
        headers["X-Webhook-Signature"] = f"sha256={signature}"

    # Add custom headers
    if subscription.headers:
        headers.update(subscription.headers)

    # Deliver with retries
    attempt = 0
    max_attempts = subscription.retry_count + 1

    while attempt < max_attempts:
        attempt += 1
        delivery.attempt_number = attempt

        try:
            start_time = time.time()

            async with (
                aiohttp.ClientSession() as session,
                session.request(
                    method=subscription.method,
                    url=subscription.endpoint_url,
                    data=payload_str,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=subscription.timeout_seconds),
                ) as response,
            ):
                response_time_ms = int((time.time() - start_time) * 1000)
                response_text = await response.text()

                delivery.response_time_ms = response_time_ms
                delivery.http_status = response.status
                delivery.response_body = response_text[:10000]  # Limit response body size

                if 200 <= response.status < 300:
                    # Success
                    delivery.status = "success"
                    delivery.delivered_at = datetime.now(UTC)

                    subscription.last_triggered_at = datetime.now(UTC)
                    subscription.last_success_at = datetime.now(UTC)
                    subscription.consecutive_failures = 0

                    logger.info(
                        "Webhook delivered successfully to %s",
                        subscription.endpoint_url,
                    )
                    return True
                else:
                    # HTTP error
                    delivery.status = "failed"
                    delivery.error_message = f"HTTP {response.status}: {response_text[:500]}"

                    logger.warning("Webhook delivery failed with HTTP %s", response.status)

        except TimeoutError:
            delivery.status = "failed"
            delivery.error_message = f"Timeout after {subscription.timeout_seconds}s"
            logger.warning("Webhook delivery timed out")

        except aiohttp.ClientError as e:
            delivery.status = "failed"
            delivery.error_message = str(e)
            logger.warning("Webhook delivery error: %s", e)

        except Exception as e:
            delivery.status = "failed"
            delivery.error_message = f"Unexpected error: {e!s}"
            logger.error("Webhook delivery unexpected error: %s", e)

        # Check if we should retry
        if attempt < max_attempts and delivery.status == "failed":
            delivery.status = "retry"
            delivery.next_retry_at = datetime.now(UTC) + timedelta(seconds=subscription.retry_delay_seconds * attempt)
            db.commit()

            # Wait before retry (exponential backoff)
            await asyncio.sleep(subscription.retry_delay_seconds * attempt)

        db.commit()

    # All retries exhausted
    subscription.last_triggered_at = datetime.now(UTC)
    subscription.last_failure_at = datetime.now(UTC)
    subscription.consecutive_failures += 1

    # Disable subscription if too many consecutive failures
    if subscription.consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
        subscription.is_active = False
        logger.warning(
            "Disabled webhook subscription %s due to %s consecutive failures",
            subscription.id,
            MAX_CONSECUTIVE_FAILURES,
        )

    db.commit()
    return False


@shared_task(name="dispatch_webhook_event")
def dispatch_webhook_event(event_type: str, event_id: str, payload: dict) -> dict:
    """
    Dispatch a webhook event to all subscribed endpoints.

    Args:
        event_type: Type of event (e.g., "workflow.completed")
        event_id: Unique identifier for the event
        payload: Event data to deliver

    Returns:
        Dict with delivery results
    """
    logger.info("Dispatching webhook event: %s (id=%s)", event_type, event_id)

    db = SessionLocal()
    try:
        # Validate event type
        try:
            WebhookEventType(event_type)
        except ValueError:
            logger.warning("Unknown event type: %s", event_type)
            return {"success": False, "error": f"Unknown event type: {event_type}"}

        # Get subscriptions
        subscriptions = get_subscriptions_for_event(event_type, db)

        if not subscriptions:
            logger.info("No active subscriptions for event: %s", event_type)
            return {"success": True, "deliveries": 0, "message": "No subscriptions"}

        # Deliver to all subscriptions
        results: list[dict[str, Any]] = []

        async def deliver_all():
            tasks = [deliver_webhook_async(sub, event_type, event_id, payload, db) for sub in subscriptions]
            return await asyncio.gather(*tasks, return_exceptions=True)

        # Run async deliveries
        delivery_results = asyncio.run(deliver_all())

        success_count = sum(1 for r in delivery_results if r is True)
        failure_count = len(delivery_results) - success_count

        logger.info(
            "Webhook dispatch complete: %s success, %s failed",
            success_count,
            failure_count,
        )

        return {
            "success": True,
            "event_type": event_type,
            "event_id": event_id,
            "total_subscriptions": len(subscriptions),
            "successful_deliveries": success_count,
            "failed_deliveries": failure_count,
        }

    except Exception as e:
        logger.error("Error dispatching webhook event: %s", e)
        return {"success": False, "error": str(e)}
    finally:
        db.close()


@shared_task(name="retry_failed_webhooks")
def retry_failed_webhooks() -> dict:
    """
    Retry failed webhook deliveries that have next_retry_at in the past.
    Should be run periodically by Celery Beat.
    """
    logger.info("Checking for failed webhooks to retry")

    db = SessionLocal()
    try:
        now = datetime.now(UTC)

        # Find deliveries pending retry
        pending = (
            db.query(WebhookDelivery)
            .filter(
                and_(
                    WebhookDelivery.status == "retry",
                    WebhookDelivery.next_retry_at <= now,
                )
            )
            .all()
        )

        if not pending:
            return {"success": True, "retried": 0}

        retried = 0
        for delivery in pending:
            subscription = db.query(WebhookSubscription).get(delivery.subscription_id)
            if not subscription or not subscription.is_active:
                continue

            # Re-dispatch
            result = asyncio.run(
                deliver_webhook_async(
                    subscription,
                    delivery.event_type,
                    delivery.event_id,
                    delivery.payload,
                    db,
                )
            )

            if result:
                retried += 1

        return {"success": True, "retried": retried}

    except Exception as e:
        logger.error("Error retrying webhooks: %s", e)
        return {"success": False, "error": str(e)}
    finally:
        db.close()


# Event emitter helper functions
def emit_event(event_type: str, payload: dict, event_id: str = None) -> None:
    """
    Emit a webhook event. Call this from your application code.

    Args:
        event_type: Type of event (use WebhookEventType enum values)
        payload: Event data
        event_id: Optional unique ID (auto-generated if not provided)
    """
    if event_id is None:
        event_id = str(uuid.uuid4())

    # Dispatch asynchronously via Celery
    dispatch_webhook_event.delay(event_type, event_id, payload)


# Convenience functions for common events
def emit_workflow_completed(workflow_id: int, user_id: int, result: dict):
    emit_event(
        WebhookEventType.WORKFLOW_COMPLETED.value,
        {"workflow_id": workflow_id, "user_id": user_id, "result": result},
    )


def emit_workflow_failed(workflow_id: int, user_id: int, error: str):
    emit_event(
        WebhookEventType.WORKFLOW_FAILED.value,
        {"workflow_id": workflow_id, "user_id": user_id, "error": error},
    )


def emit_agent_approval_required(execution_id: int, user_id: int, tool_name: str, params: dict):
    emit_event(
        WebhookEventType.AGENT_APPROVAL_REQUIRED.value,
        {
            "execution_id": execution_id,
            "user_id": user_id,
            "tool_name": tool_name,
            "params": params,
        },
    )


def emit_rag_document_processed(document_id: int, collection_id: int, status: str):
    emit_event(
        WebhookEventType.RAG_DOCUMENT_PROCESSED.value,
        {"document_id": document_id, "collection_id": collection_id, "status": status},
    )


def emit_chat_thread_created(thread_id: int, user_id: int, title: str):
    emit_event(
        WebhookEventType.CHAT_THREAD_CREATED.value,
        {"thread_id": thread_id, "user_id": user_id, "title": title},
    )
