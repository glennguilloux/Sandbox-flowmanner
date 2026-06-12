"""DISABLED 2026-06-12 — wrong import path, completely different schema.

The original `webhook_dispatcher.py` is preserved in `_disabled/` for
revival.  It imports `WebhookSubscription`, `WebhookDelivery`, and
`WebhookEventType` from a non-existent `app.models.webhook_subscription`
module.  The actual webhook models live in `app.models.webhook_models`
(consolidated module) but export a **different shape**:

  Existing in `app.models.webhook_models`:
    - WebhookEndpoint (id, name, source, path, secret, retry_count, ...)
    - WebhookLog (id, endpoint_id, event_type, status, response_code, ...)
    - WebhookStatus (enum: PENDING, PROCESSING, SUCCESS, FAILED, RETRYING)

  Required by the original code (does NOT exist):
    - WebhookSubscription (event_types list, method, endpoint_url, ...)
    - WebhookDelivery (attempt_number, next_retry_at, response_body, ...)
    - WebhookEventType (enum with WORKFLOW_*, AGENT_*, RAG_*, CHAT_*)

To revive this module, you need to:
  1. Create a new alembic migration adding a `webhook_subscriptions`
     table (event_types, method, endpoint_url, headers, retry_count,
     retry_delay_seconds, timeout_seconds, consecutive_failures, ...).
  2. Create a new alembic migration adding a `webhook_deliveries` table
     (subscription_id, attempt_number, response_body, next_retry_at, ...).
  3. Add the `WebhookSubscription`, `WebhookDelivery`, and
     `WebhookEventType` models to `app/models/webhook_models.py` (or a
     new `app/models/webhook_subscription.py`).
  4. Migrate `app.tasks._disabled.webhook_dispatcher.py` to use the
     new ORM models.

Until then this stub keeps the celery worker import graph clean.
"""
