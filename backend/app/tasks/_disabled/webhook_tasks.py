# mypy: disable-error-code=attr-defined
"""
Webhook Delivery & Retry Tasks

Celery tasks for reliable webhook delivery with scheduled backoff,
dead letter queue, and HMAC-SHA256 signing.
"""

import hashlib
import hmac
import json
import logging
from datetime import UTC, datetime

import httpx
from celery import shared_task
from sqlalchemy import and_, select

from ..database import SyncSessionLocal
from ..models.webhook_models import WebhookEndpoint, WebhookLog, WebhookStatus
from ..services.webhook_handler.retry import retry_manager

logger = logging.getLogger(__name__)


def _sign_payload(secret: str, payload_bytes: bytes) -> str:
    """Generate HMAC-SHA256 signature for webhook payload."""
    return hmac.new(
        secret.encode("utf-8"),
        payload_bytes,
        hashlib.sha256,
    ).hexdigest()


def _deliver_sync(
    endpoint: WebhookEndpoint,
    log: WebhookLog,
    payload: dict,
) -> None:
    """Deliver a single webhook and update the log record (sync)."""
    body_bytes = json.dumps(payload, default=str).encode()
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "Flowmanner-Webhook/1.0",
    }

    # HMAC signing
    if endpoint.secret:
        sig = _sign_payload(endpoint.secret, body_bytes)
        headers["X-Webhook-Signature"] = f"sha256={sig}"
        headers["X-Webhook-ID"] = str(log.id)
        headers["X-Webhook-Timestamp"] = str(int(log.created_at.timestamp())) if log.created_at else ""

    log.status = WebhookStatus.PROCESSING.value

    try:
        with httpx.Client(timeout=endpoint.timeout_seconds or 30) as client:
            resp = client.post(endpoint.path, content=body_bytes, headers=headers)
            log.response_code = resp.status_code
            log.response_body = {"body": resp.text[:5000]}

            if 200 <= resp.status_code < 300:
                log.status = WebhookStatus.SUCCESS.value
            else:
                raise Exception(f"HTTP {resp.status_code}: {resp.text[:200]}")

    except Exception as e:
        log.last_error = str(e)[:1000]
        log.last_error_at = datetime.now(UTC)
        log.retry_count += 1

        if retry_manager.should_retry(str(e), log.retry_count):
            log.status = WebhookStatus.PENDING.value
            next_retry = retry_manager.schedule_retry(log.id, log.retry_count)
            log.next_retry_at = next_retry
            logger.info(
                "Webhook %s scheduled for retry #%s at %s",
                log.id,
                log.retry_count,
                next_retry,
            )
        else:
            log.status = WebhookStatus.FAILED.value
            log.next_retry_at = None
            logger.warning("Webhook %s moved to DLQ after %s retries", log.id, log.retry_count)

    log.processing_completed_at = datetime.now(UTC)


@shared_task(name="app.tasks.webhook_tasks.deliver_webhook", max_retries=0, acks_late=True)
def deliver_webhook(log_id: int) -> dict:
    """Deliver a single webhook by log ID."""
    db = SyncSessionLocal()
    try:
        log = db.get(WebhookLog, log_id)
        if not log:
            return {"error": "log not found", "log_id": log_id}

        if log.status not in (
            WebhookStatus.PENDING.value,
            WebhookStatus.PROCESSING.value,
        ):
            return {"skipped": True, "status": log.status, "log_id": log_id}

        ep = db.get(WebhookEndpoint, log.endpoint_id)
        if not ep or not ep.is_active:
            log.status = WebhookStatus.FAILED.value
            log.last_error = "Endpoint not found or inactive"
            db.commit()
            return {"error": "endpoint inactive", "log_id": log_id}

        _deliver_sync(ep, log, log.payload or {})
        db.commit()

        return {"log_id": log_id, "status": log.status, "retry_count": log.retry_count}

    except Exception as e:
        logger.exception("deliver_webhook task failed for log %s: %s", log_id, e)
        db.rollback()
        raise
    finally:
        db.close()


@shared_task(name="app.tasks.webhook_tasks.process_due_retries")
def process_due_retries() -> dict:
    """Process all webhook logs that are due for retry.

    Runs via Celery beat every 30 seconds. Finds PENDING logs where
    next_retry_at <= now and dispatches delivery tasks.
    """
    db = SyncSessionLocal()
    try:
        now = datetime.now(UTC)
        q = (
            select(WebhookLog)
            .where(
                and_(
                    WebhookLog.status == WebhookStatus.PENDING.value,
                    WebhookLog.next_retry_at.isnot(None),
                    WebhookLog.next_retry_at <= now,
                    WebhookLog.retry_count < WebhookLog.max_retries,
                )
            )
            .limit(50)
        )
        result = db.execute(q)
        due_logs = result.scalars().all()

        dispatched = 0
        for log in due_logs:
            deliver_webhook.delay(log.id)
            dispatched += 1

        if dispatched:
            logger.info("Dispatched %s due webhook retries", dispatched)

        return {"dispatched": dispatched, "checked_at": now.isoformat()}

    except Exception as e:
        logger.exception("process_due_retries failed: %s", e)
        raise
    finally:
        db.close()
