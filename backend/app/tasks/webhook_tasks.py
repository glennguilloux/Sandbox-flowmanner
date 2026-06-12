"""DISABLED 2026-06-12 — missing sync session factory.

The original `webhook_tasks.py` is preserved in `_disabled/` for revival.
The blocker is `from ..database import SyncSessionLocal` — `app/database.py`
only exposes the async `AsyncSessionLocal` and an alias `SessionLocal =
AsyncSessionLocal`.  The two tasks in the original file (`deliver_webhook`
and `process_due_retries`) are sync functions that need a sync SQLAlchemy
session.

To revive this module, you need:
  1. Add a sync SQLAlchemy engine + `SyncSessionLocal` factory to
     `app/database.py`.  The sync engine should reuse the same DB URL
     but a different driver (psycopg2 instead of asyncpg) and no
     async-specific pool options.  Wire it via a new setting
     `settings.DATABASE_SYNC_URL` (or fall back to translating the
     async URL by swapping `+asyncpg` → `+psycopg2`).
  2. Verify `app.models.webhook_models.WebhookEndpoint` and
     `WebhookLog` columns match the call sites in the original
     `_disabled/webhook_tasks.py` (the disabled code uses `endpoint.path`
     for delivery, but `WebhookEndpoint.path` is the inbound path
     (e.g. `/wh/inbound/stripe`), not the outbound destination URL —
     see `WebhookEndpoint` model definition; the URL the code delivers
     to is `subscription.endpoint_url` from the *other* webhook module).
  3. `app.services.webhook_handler.retry.retry_manager` exists and is
     ready to use.

Until then this stub keeps the celery worker import graph clean.
"""
