"""Hermetic Postgres tests for the event-bus off-request-path refactor (Q4/Q5/Q6).

These tests prove the three load-bearing guarantees from the implementation
card, using a unique per-test Postgres database (JSONB/UUID columns cannot be
rendered on sqlite):

1. Q4 (post-commit ordering): the durable ExternalEvent row is COMMITTED by the
   request transaction BEFORE the Celery ``process_external_event`` task runs.
   If the row were not committed, the task's ``fresh_session`` lookup would not
   see it.  We simulate the route (publish → commit) then run the task body
   directly and assert it finds + processes the committed row.

2. Q5 (delivery_id dedup / redelivery no-op): a redelivered task for an already
   completed event is a no-op (the claim-step), so triggers are never re-fired.

3. Q6 (failure alerts): ``failure_alert_consumer`` still fires on status
   "failed" — now inside the Celery task — and reaches out to Slack /
   PagerDuty (httpx call mocked + asserted).

Skips cleanly when Postgres is unreachable on the host.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import uuid

import pytest
import pytest_asyncio
from sqlalchemy import text as sql_text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings

os.environ.setdefault("OPENAI_API_KEY", "sk-test")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-32-chars-long!!")
os.environ.setdefault("SECRET_KEY", "test-secret-key-32-chars-long!!")
os.environ.setdefault("AES_ENCRYPTION_KEY", "test-aes-key-32-chars-long!!!!!!")

# Unique per-session hermetic DB.  Maps compose/localhost hosts to 127.0.0.1
# (the homelab host TCP md5 auth rule) so the test runs without /etc/hosts
# edits.  Falls back to the configured DATABASE_URL (same rule applies).
_BASE = os.getenv("FLOWMANNER_EVENTBUS_OFFLOAD_TEST_DB", str(settings.DATABASE_URL))
_BASE = _BASE.replace("@postgres:", "@127.0.0.1:").replace("@localhost:", "@127.0.0.1:")


@pytest_asyncio.fixture
async def engines():
    db_name = f"eventbus_offload_{uuid.uuid4().hex[:12]}"
    admin_url = _BASE.rsplit("/", 1)[0] + "/postgres"
    test_url = _BASE.rsplit("/", 1)[0] + "/" + db_name

    admin = create_async_engine(admin_url, future=True)
    try:
        async with admin.connect() as conn:
            await conn.execution_options(isolation_level="AUTOCOMMIT")
            await conn.execute(sql_text(f'CREATE DATABASE "{db_name}"'))
    except Exception as exc:  # Postgres unreachable on host → skip cleanly.
        await admin.dispose()
        pytest.skip(f"Postgres unavailable for hermetic event-bus offload test: {exc}")
    finally:
        await admin.dispose()

    engine = create_async_engine(test_url, future=True)
    async with engine.begin() as conn:
        from app.models import Base

        await conn.run_sync(Base.metadata.create_all)

    # Patch the module-global sessionmaker so the Celery task's fresh_session()
    # (used by process_external_event._dispatch) hits THIS hermetic database,
    # not the default settings.DATABASE_URL.  This mirrors production: the task
    # runs in the same process/DB as the route.
    import app.database as db_mod

    test_sessionmaker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    # Set directly and restore in teardown (fixture teardown runs after tests).
    _orig = db_mod.AsyncSessionLocal
    db_mod.AsyncSessionLocal = test_sessionmaker

    yield engine

    # Restore + teardown.
    db_mod.AsyncSessionLocal = _orig
    await engine.dispose()
    admin = create_async_engine(admin_url, future=True)
    try:
        async with admin.connect() as conn:
            await conn.execution_options(isolation_level="AUTOCOMMIT")
            await conn.execute(sql_text(f'DROP DATABASE "{db_name}" WITH (FORCE)'))
    except Exception:
        pass
    finally:
        await admin.dispose()


@pytest_asyncio.fixture
def session_factory(engines):
    """Return the (patched) module-global sessionmaker so direct sessions and
    the Celery task's fresh_session() share the hermetic DB."""
    import app.database as db_mod

    return db_mod.AsyncSessionLocal


# ── Helpers ─────────────────────────────────────────────────────────


async def _publish_and_commit(**kwargs):
    """Simulate the webhook route: publish (flush) then commit (get_db owns txn)."""
    import app.database as db_mod
    from app.services.event_bus import get_event_bus

    bus = get_event_bus()
    async with db_mod.AsyncSessionLocal() as db:
        event = await bus.publish(db, **kwargs)
        event_id = str(event.id)
        await db.commit()
    return event_id


# ── Q4: committed-before-task ──────────────────────────────────────


@pytest.mark.asyncio
async def test_event_committed_before_task_runs(session_factory):
    """The task can only see + process the row because the route committed it."""
    from app.tasks.event_bus_tasks import _dispatch

    event_id = await _publish_and_commit(
        source="github",
        event_type="push",
        payload={"ref": "main"},
        delivery_id="q4-deliv-1",
    )

    # Run the task body directly (no broker needed).  It opens its own
    # fresh_session and looks the event up by id — which only works if the
    # row was committed by the simulated route above.
    result = await _dispatch(event_id)
    assert result == "processed"

    # Confirm the committed status persisted.
    async with session_factory() as db:
        from app.models.external_event_model import ExternalEvent

        ev = await db.get(ExternalEvent, event_id)
        assert ev is not None
        assert ev.status == "processed"
        assert ev.processed_at is not None


@pytest.mark.asyncio
async def test_task_sees_nothing_if_not_committed(session_factory):
    """If the route had NOT committed (e.g. crash pre-commit), the task sees no row."""
    from app.services.event_bus import get_event_bus
    from app.tasks.event_bus_tasks import _dispatch

    # Publish WITHOUT committing — simulate a crash before get_db's commit.
    bus = get_event_bus()
    async with session_factory() as db:
        event = await bus.publish(db, source="github", event_type="push", delivery_id="q4-uncommitted")
        event_id = str(event.id)
        # Roll back instead of commit.
        await db.rollback()

    result = await _dispatch(event_id)
    assert result == "not_found"


# ── Q5: delivery_id dedup / redelivery no-op ───────────────────────


@pytest.mark.asyncio
async def test_redelivered_task_is_noop(session_factory):
    """A redelivered task for an already-completed event does not re-run (claim-step)."""
    from app.services.event_bus import get_event_bus
    from app.tasks.event_bus_tasks import _dispatch

    event_id = await _publish_and_commit(
        source="stripe",
        event_type="charge.succeeded",
        payload={"amount": 100},
        delivery_id="q5-redeliv-1",
    )

    # First run processes it.
    assert await _dispatch(event_id) == "processed"

    # Redelivery: the event is already "processed" with processed_at set,
    # so the claim-step makes it a no-op rather than re-firing consumers.
    assert await _dispatch(event_id) == "skipped"


@pytest.mark.asyncio
async def test_publish_dedupes_same_delivery_id(session_factory):
    """publish() returns the existing row for a duplicate delivery_id (no new row)."""
    from sqlalchemy import select

    from app.models.external_event_model import ExternalEvent
    from app.services.event_bus import get_event_bus

    bus = get_event_bus()
    async with session_factory() as db:
        e1 = await bus.publish(db, source="stripe", event_type="charge.succeeded", delivery_id="q5-dup-1")
        e2 = await bus.publish(db, source="stripe", event_type="charge.succeeded", delivery_id="q5-dup-1")
        assert e1.id == e2.id

        count = (await db.execute(select(ExternalEvent).where(ExternalEvent.source == "stripe"))).scalars().all()
        assert len(count) == 1


# ── Q6: failure alert fires on status == "failed" ──────────────────


class _FakeAsyncResponse:
    def __init__(self, status_code: int = 200) -> None:
        self.status_code = status_code


class _FakeAsyncClient:
    """Records POST calls so we can assert Slack / PagerDuty were contacted."""

    captured: list[tuple[str, dict]] = []

    def __init__(self, *args, **kwargs) -> None:
        self._args = (args, kwargs)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def post(self, url: str, json: dict | None = None, **kwargs):
        _FakeAsyncClient.captured.append((url, json or {}))
        return _FakeAsyncResponse(200)


@pytest.mark.asyncio
async def test_failure_alert_fires_on_failed(session_factory, monkeypatch):
    """failure_alert_consumer reaches Slack + PagerDuty when event.status == 'failed'."""
    import httpx

    import app.services.event_bus_consumers as consumers_mod
    from app.services.event_bus import get_event_bus, reset_event_bus
    from app.tasks.event_bus_tasks import _dispatch

    # Point failure_alert_consumer at fake endpoints and capture its httpx calls.
    monkeypatch.setattr(settings, "SLACK_ALERT_WEBHOOK_URL", "https://slack.example/hook")
    monkeypatch.setattr(settings, "PAGERDUTY_ALERT_ROUTING_KEY", "pd-routing-key")
    monkeypatch.setattr(httpx, "AsyncClient", _FakeAsyncClient)

    # Build a fresh bus whose only consumer always fails and whose only
    # failure handler is the REAL failure_alert_consumer.
    reset_event_bus()
    bus = get_event_bus()
    bus._consumers.clear()
    bus._on_failure.clear()

    async def _boom(db, event):
        raise RuntimeError("trigger router exploded")

    bus.add_consumer(_boom)
    bus.add_failure_handler(consumers_mod.failure_alert_consumer)

    event_id = await _publish_and_commit(
        source="github",
        event_type="push",
        payload={"ref": "main"},
        delivery_id="q6-fail-1",
    )

    result = await _dispatch(event_id)
    assert result == "failed"

    # The real failure_alert_consumer must have contacted both channels.
    urls = [url for url, _ in _FakeAsyncClient.captured]
    assert any("slack.example" in u for u in urls), f"no Slack call: {urls}"
    assert any("events.pagerduty.com" in u for u in urls), f"no PagerDuty call: {urls}"

    # Restore the singleton for other tests.
    reset_event_bus()
    _FakeAsyncClient.captured.clear()
