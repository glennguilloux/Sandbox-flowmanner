"""Unit tests for the EventBus pipeline.

Covers:
- publish: persists ExternalEvent, dispatches to consumers, sets status
- idempotency: duplicate delivery_id returns existing event without re-processing
- replay: resets status and re-dispatches to consumers
- consumer failure isolation: one consumer failing doesn't prevent others
- failure handler triggering: failure handlers run only on "failed" status
- failure handler isolation: failure handler exceptions are swallowed
- synthetic delivery_id generation
"""

from __future__ import annotations

import os

os.environ.setdefault("OPENAI_API_KEY", "sk-test")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-32-chars-long!!")
os.environ.setdefault("SECRET_KEY", "test-secret-key-32-chars-long!!")
os.environ.setdefault("AES_ENCRYPTION_KEY", "test-aes-key-32-chars-long!!!!!!")
os.environ.setdefault("APP_ENV", "development")

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest
import pytest_asyncio
from sqlalchemy import JSON, Column, DateTime, Integer, MetaData, String, Table, Text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.services.event_bus import EventBus, reset_event_bus

if TYPE_CHECKING:
    from app.models.external_event_model import ExternalEvent

# ── Test-safe table definition ───────────────────────────────────────
# We create a standalone MetaData with a SQLite-compatible version of the
# external_events table (JSON instead of JSONB, no unique index constraints).
# This avoids the JSONB compilation error and the index-already-exists issue.
# Note: queries go through the ExternalEvent ORM model (Base.metadata with
# PostgreSQL UUID type), so this table is only used for DDL. The model's
# UUID type handles uuid.UUID objects natively on SQLite.

_test_metadata = MetaData()

_test_external_events = Table(
    "external_events",
    _test_metadata,
    Column("id", String(36), primary_key=True),
    Column("source", String(64), nullable=False),
    Column("event_type", String(128), nullable=False),
    Column("delivery_id", String(255), nullable=True),
    Column("payload", JSON, nullable=True),
    Column("raw_body", JSON, nullable=True),
    Column("user_id", Integer, nullable=True),
    Column("status", String(20), nullable=False, server_default="pending"),
    Column("error_message", Text, nullable=True),
    Column("triggers_fired", Integer, nullable=False, server_default="0"),
    Column("received_at", DateTime, nullable=False),
    Column("processed_at", DateTime, nullable=True),
    Column("created_at", DateTime, nullable=False),
    Column("updated_at", DateTime, nullable=False),
)


# ── Fixtures ─────────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def db_engine():
    """Create an in-memory SQLite engine with a test-safe external_events table."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(_test_metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(_test_metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def db(db_engine):
    """Create an async session for testing."""
    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session


@pytest.fixture
def bus():
    """Create a fresh EventBus instance (no default consumers)."""
    return EventBus()


# ── Helper consumers for testing ─────────────────────────────────────


async def _noop_consumer(db: AsyncSession, event: ExternalEvent) -> None:
    """A consumer that does nothing (success)."""
    pass


async def _failing_consumer(db: AsyncSession, event: ExternalEvent) -> None:
    """A consumer that always raises."""
    raise RuntimeError("consumer exploded")


def _tracking_consumer():
    """Create a consumer that tracks calls."""
    calls: list[ExternalEvent] = []

    async def consumer(db: AsyncSession, event: ExternalEvent) -> None:
        calls.append(event)

    return consumer, calls


async def _setting_consumer(db: AsyncSession, event: ExternalEvent) -> None:
    """A consumer that sets triggers_fired on the event."""
    event.triggers_fired = 42


# ── Publish tests ────────────────────────────────────────────────────


class TestPublish:
    """Tests for EventBus.publish()."""

    @pytest.mark.asyncio
    async def test_publish_persists_event(self, bus, db):
        """publish() creates an ExternalEvent row in the database."""
        event = await bus.publish(
            db,
            source="github",
            event_type="push",
            payload={"ref": "main"},
            delivery_id="gh-del-1",
        )

        assert event.source == "github"
        assert event.event_type == "push"
        assert event.payload == {"ref": "main"}
        assert event.delivery_id == "gh-del-1"
        assert event.status == "processed"
        assert event.processed_at is not None
        assert event.id is not None

    @pytest.mark.asyncio
    async def test_publish_no_consumers_sets_processed(self, bus, db):
        """With no consumers registered, status is 'processed'."""
        event = await bus.publish(
            db,
            source="stripe",
            event_type="charge.succeeded",
            delivery_id="evt-1",
        )
        assert event.status == "processed"

    @pytest.mark.asyncio
    async def test_publish_dispatches_to_consumers(self, bus, db):
        """publish() calls all registered consumers."""
        consumer, calls = _tracking_consumer()
        bus.add_consumer(consumer)

        event = await bus.publish(
            db,
            source="github",
            event_type="push",
            delivery_id="gh-1",
        )

        assert len(calls) == 1
        assert calls[0].id == event.id
        assert event.status == "processed"

    @pytest.mark.asyncio
    async def test_publish_multiple_consumers(self, bus, db):
        """publish() calls consumers in registration order."""
        consumer1, calls1 = _tracking_consumer()
        consumer2, calls2 = _tracking_consumer()
        bus.add_consumer(consumer1)
        bus.add_consumer(consumer2)

        event = await bus.publish(
            db,
            source="github",
            event_type="push",
            delivery_id="gh-1",
        )

        assert len(calls1) == 1
        assert len(calls2) == 1
        assert calls1[0].id == event.id
        assert calls2[0].id == event.id

    @pytest.mark.asyncio
    async def test_publish_without_delivery_id(self, bus, db):
        """publish() works without a delivery_id (no idempotency check)."""
        event = await bus.publish(
            db,
            source="github",
            event_type="push",
        )
        assert event.status == "processed"
        assert event.delivery_id is None

    @pytest.mark.asyncio
    async def test_publish_with_user_id(self, bus, db):
        """publish() stores user_id on the event."""
        event = await bus.publish(
            db,
            source="github",
            event_type="push",
            user_id=42,
        )
        assert event.user_id == 42

    @pytest.mark.asyncio
    async def test_publish_with_raw_body(self, bus, db):
        """publish() stores raw_body on the event."""
        raw = {"headers": {"x-github-delivery": "abc"}, "body": "..."}
        event = await bus.publish(
            db,
            source="github",
            event_type="push",
            payload={"ref": "main"},
            raw_body=raw,
            delivery_id="gh-1",
        )
        assert event.raw_body == raw
        assert event.payload == {"ref": "main"}

    @pytest.mark.asyncio
    async def test_publish_with_none_payload(self, bus, db):
        """publish() handles None payload gracefully."""
        event = await bus.publish(
            db,
            source="github",
            event_type="push",
            payload=None,
            delivery_id="gh-2",
        )
        assert event.status == "processed"
        assert event.payload is None


# ── Idempotency tests ───────────────────────────────────────────────


class TestIdempotency:
    """Tests for idempotency via delivery_id."""

    @pytest.mark.asyncio
    async def test_duplicate_delivery_id_returns_existing(self, bus, db):
        """Second publish with same delivery_id returns the first event."""
        event1 = await bus.publish(
            db,
            source="stripe",
            event_type="charge.succeeded",
            delivery_id="evt-abc",
            payload={"amount": 100},
        )
        event2 = await bus.publish(
            db,
            source="stripe",
            event_type="charge.succeeded",
            delivery_id="evt-abc",
            payload={"amount": 100},
        )

        assert event1.id == event2.id
        assert event2.status == "processed"

    @pytest.mark.asyncio
    async def test_same_delivery_id_different_source_not_duplicate(self, bus, db):
        """Same delivery_id with different source creates a new event."""
        event1 = await bus.publish(
            db,
            source="stripe",
            event_type="charge.succeeded",
            delivery_id="evt-abc",
        )
        event2 = await bus.publish(
            db,
            source="github",
            event_type="charge.succeeded",
            delivery_id="evt-abc",
        )

        assert event1.id != event2.id

    @pytest.mark.asyncio
    async def test_duplicate_does_not_rerun_consumers(self, bus, db):
        """Duplicate delivery_id returns existing event without running consumers."""
        consumer, calls = _tracking_consumer()
        bus.add_consumer(consumer)

        await bus.publish(
            db,
            source="stripe",
            event_type="charge.succeeded",
            delivery_id="evt-abc",
        )
        await bus.publish(
            db,
            source="stripe",
            event_type="charge.succeeded",
            delivery_id="evt-abc",
        )

        # Consumer should only be called once
        assert len(calls) == 1


# ── Replay tests ────────────────────────────────────────────────────


class TestReplay:
    """Tests for EventBus.replay()."""

    @pytest.mark.asyncio
    async def test_replay_resets_status(self, bus, db):
        """replay() resets event to 'pending' then reprocesses."""
        event = await bus.publish(
            db,
            source="github",
            event_type="push",
            delivery_id="gh-1",
        )
        assert event.status == "processed"

        replayed = await bus.replay(db, event.id)

        assert replayed is not None
        assert replayed.id == event.id
        assert replayed.status == "processed"  # Re-processed successfully

    @pytest.mark.asyncio
    async def test_replay_returns_none_for_missing(self, bus, db):
        """replay() returns None for a non-existent event_id."""
        result = await bus.replay(db, uuid.uuid4())
        assert result is None

    @pytest.mark.asyncio
    async def test_replay_reruns_consumers(self, bus, db):
        """replay() re-dispatches to all registered consumers."""
        consumer, calls = _tracking_consumer()
        bus.add_consumer(consumer)

        event = await bus.publish(
            db,
            source="github",
            event_type="push",
            delivery_id="gh-1",
        )
        assert len(calls) == 1

        await bus.replay(db, event.id)
        assert len(calls) == 2  # Called again on replay

    @pytest.mark.asyncio
    async def test_replay_resets_triggers_fired(self, bus, db):
        """replay() resets triggers_fired to 0 before re-dispatch."""
        seen_values: list[int] = []

        async def recording_consumer(db: AsyncSession, event: ExternalEvent) -> None:
            seen_values.append(event.triggers_fired)
            event.triggers_fired = 42

        bus.add_consumer(recording_consumer)

        event = await bus.publish(
            db,
            source="github",
            event_type="push",
            delivery_id="gh-1",
        )
        assert event.triggers_fired == 42
        assert seen_values == [0]  # First call saw 0

        replayed = await bus.replay(db, event.id)
        assert replayed.triggers_fired == 42
        assert seen_values == [0, 0]  # Replay also saw 0 (was reset)

    @pytest.mark.asyncio
    async def test_replay_failed_event_succeeds(self, bus, db):
        """replay() can recover a previously failed event."""
        call_count = 0

        async def flaky_consumer(db: AsyncSession, event: ExternalEvent) -> None:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("first call fails")

        bus.add_consumer(flaky_consumer)

        event = await bus.publish(
            db,
            source="github",
            event_type="push",
            delivery_id="gh-1",
        )
        assert event.status == "failed"

        replayed = await bus.replay(db, event.id)
        assert replayed.status == "processed"  # Second call succeeds

    @pytest.mark.asyncio
    async def test_replay_does_not_run_failure_handlers(self, bus, db):
        """replay() does NOT trigger failure handlers (they are publish-time only)."""
        handler, handler_calls = _tracking_consumer()
        bus.add_consumer(_failing_consumer)
        bus.add_failure_handler(handler)

        event = await bus.publish(
            db,
            source="github",
            event_type="push",
            delivery_id="gh-1",
        )
        assert event.status == "failed"
        assert len(handler_calls) == 1  # Handler fired on publish

        replayed = await bus.replay(db, event.id)
        assert replayed.status == "failed"  # Replay also fails
        assert len(handler_calls) == 1  # Handler NOT fired on replay


# ── Consumer failure isolation tests ─────────────────────────────────


class TestConsumerIsolation:
    """Tests for consumer failure isolation."""

    @pytest.mark.asyncio
    async def test_failing_consumer_sets_failed_status(self, bus, db):
        """A failing consumer causes event.status to be 'failed'."""
        bus.add_consumer(_failing_consumer)

        event = await bus.publish(
            db,
            source="github",
            event_type="push",
            delivery_id="gh-1",
        )

        assert event.status == "failed"
        assert "consumer exploded" in event.error_message

    @pytest.mark.asyncio
    async def test_failing_consumer_does_not_block_siblings(self, bus, db):
        """A failing consumer doesn't prevent subsequent consumers from running."""
        consumer, calls = _tracking_consumer()
        bus.add_consumer(_failing_consumer)
        bus.add_consumer(consumer)

        event = await bus.publish(
            db,
            source="github",
            event_type="push",
            delivery_id="gh-1",
        )

        # Both consumers ran — the tracking consumer got called
        assert len(calls) == 1
        # But status is "failed" because one consumer raised
        assert event.status == "failed"

    @pytest.mark.asyncio
    async def test_multiple_failures_concatenated(self, bus, db):
        """Multiple consumer failures are joined in error_message."""

        async def fail_a(db, event):
            raise RuntimeError("error A")

        async def fail_b(db, event):
            raise RuntimeError("error B")

        bus.add_consumer(fail_a)
        bus.add_consumer(fail_b)

        event = await bus.publish(
            db,
            source="github",
            event_type="push",
            delivery_id="gh-1",
        )

        assert event.status == "failed"
        assert "error A" in event.error_message
        assert "error B" in event.error_message

    @pytest.mark.asyncio
    async def test_consumer_can_mutate_event(self, bus, db):
        """Consumers can mutate the event (e.g. set triggers_fired)."""
        bus.add_consumer(_setting_consumer)

        event = await bus.publish(
            db,
            source="github",
            event_type="push",
            delivery_id="gh-1",
        )

        assert event.triggers_fired == 42


# ── Failure handler tests ────────────────────────────────────────────


class TestFailureHandlers:
    """Tests for failure handler triggering."""

    @pytest.mark.asyncio
    async def test_failure_handler_runs_on_failure(self, bus, db):
        """Failure handlers run when event.status is 'failed'."""
        handler, calls = _tracking_consumer()
        bus.add_consumer(_failing_consumer)
        bus.add_failure_handler(handler)

        event = await bus.publish(
            db,
            source="github",
            event_type="push",
            delivery_id="gh-1",
        )

        assert event.status == "failed"
        assert len(calls) == 1
        assert calls[0].id == event.id

    @pytest.mark.asyncio
    async def test_failure_handler_does_not_run_on_success(self, bus, db):
        """Failure handlers do NOT run when event.status is 'processed'."""
        handler, calls = _tracking_consumer()
        bus.add_consumer(_noop_consumer)
        bus.add_failure_handler(handler)

        event = await bus.publish(
            db,
            source="github",
            event_type="push",
            delivery_id="gh-1",
        )

        assert event.status == "processed"
        assert len(calls) == 0

    @pytest.mark.asyncio
    async def test_failure_handler_exception_is_swallowed(self, bus, db):
        """Exceptions from failure handlers are logged and swallowed."""

        async def exploding_handler(db: AsyncSession, event: ExternalEvent) -> None:
            raise RuntimeError("handler exploded")

        bus.add_consumer(_failing_consumer)
        bus.add_failure_handler(exploding_handler)

        # Should not raise — the handler exception is swallowed
        event = await bus.publish(
            db,
            source="github",
            event_type="push",
            delivery_id="gh-1",
        )

        assert event.status == "failed"

    @pytest.mark.asyncio
    async def test_failure_handler_receives_final_event(self, bus, db):
        """Failure handler sees the event with error_message already set."""
        received_events: list[ExternalEvent] = []

        async def capturing_handler(db: AsyncSession, event: ExternalEvent) -> None:
            received_events.append(event)

        bus.add_consumer(_failing_consumer)
        bus.add_failure_handler(capturing_handler)

        await bus.publish(
            db,
            source="github",
            event_type="push",
            delivery_id="gh-1",
        )

        assert len(received_events) == 1
        assert received_events[0].status == "failed"
        assert received_events[0].error_message is not None

    @pytest.mark.asyncio
    async def test_multiple_failure_handlers_all_run(self, bus, db):
        """All registered failure handlers run on failure."""
        handler1, calls1 = _tracking_consumer()
        handler2, calls2 = _tracking_consumer()
        bus.add_consumer(_failing_consumer)
        bus.add_failure_handler(handler1)
        bus.add_failure_handler(handler2)

        await bus.publish(
            db,
            source="github",
            event_type="push",
            delivery_id="gh-1",
        )

        assert len(calls1) == 1
        assert len(calls2) == 1


# ── add_consumer / add_failure_handler tests ─────────────────────────


class TestRegistration:
    """Tests for consumer and failure handler registration."""

    def test_add_consumer(self, bus):
        bus.add_consumer(_noop_consumer)
        assert len(bus._consumers) == 1
        assert bus._consumers[0] is _noop_consumer

    def test_add_failure_handler(self, bus):
        bus.add_failure_handler(_noop_consumer)
        assert len(bus._on_failure) == 1
        assert bus._on_failure[0] is _noop_consumer

    def test_consumers_and_handlers_independent(self, bus):
        bus.add_consumer(_noop_consumer)
        bus.add_failure_handler(_noop_consumer)
        assert len(bus._consumers) == 1
        assert len(bus._on_failure) == 1

    def test_reset_event_bus(self):
        """reset_event_bus() clears the singleton."""
        from app.services.event_bus import get_event_bus

        bus1 = get_event_bus()
        reset_event_bus()
        bus2 = get_event_bus()
        assert bus1 is not bus2


# ── Synthetic delivery_id tests ──────────────────────────────────────


class TestSyntheticDeliveryId:
    """Tests for _synthetic_delivery_id()."""

    def test_deterministic(self):
        from app.services.event_router import _synthetic_delivery_id

        d1 = _synthetic_delivery_id("github", "push", {"ref": "main"})
        d2 = _synthetic_delivery_id("github", "push", {"ref": "main"})
        assert d1 == d2

    def test_different_event_type(self):
        from app.services.event_router import _synthetic_delivery_id

        d1 = _synthetic_delivery_id("github", "push", {"ref": "main"})
        d2 = _synthetic_delivery_id("github", "pull_request", {"ref": "main"})
        assert d1 != d2

    def test_different_source(self):
        from app.services.event_router import _synthetic_delivery_id

        d1 = _synthetic_delivery_id("github", "push", {"ref": "main"})
        d2 = _synthetic_delivery_id("gitlab", "push", {"ref": "main"})
        assert d1 != d2

    def test_key_order_independent(self):
        from app.services.event_router import _synthetic_delivery_id

        d1 = _synthetic_delivery_id("github", "push", {"a": 1, "b": 2})
        d2 = _synthetic_delivery_id("github", "push", {"b": 2, "a": 1})
        assert d1 == d2

    def test_format(self):
        from app.services.event_router import _synthetic_delivery_id

        d = _synthetic_delivery_id("github", "push", {"ref": "main"})
        assert d.startswith("syn:")
        assert len(d) == 36  # syn: + 32 hex chars

    def test_nested_payload_deterministic(self):
        from app.services.event_router import _synthetic_delivery_id

        payload = {"repo": {"name": "test"}, "commits": [{"id": "abc"}]}
        d1 = _synthetic_delivery_id("github", "push", payload)
        d2 = _synthetic_delivery_id("github", "push", payload)
        assert d1 == d2
