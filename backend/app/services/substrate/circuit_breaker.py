"""Per-workspace+provider circuit breaker (Q1-A chunk 5).

Implements the canonical circuit breaker pattern (Hystrix / Resilience4j school)
at the provider level.  This is a SECOND, parallel circuit breaker layer on top
of the existing per-mission budget guard in circuit_breaker_service.py.

States:
- CLOSED: Normal operation. Failures are counted.
- OPEN: Provider is failing. Requests are denied for cooldown_seconds.
- HALF_OPEN: Cooldown elapsed. One probe request is allowed.

The half-open probe race is handled via the `probe_in_flight` column
+ SELECT FOR UPDATE to serialize concurrent decisions.

NOTE: This module does NOT touch the existing per-mission CircuitBreakerService.
Different concern, different layer, different tables.
"""

from __future__ import annotations

import enum
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import select, text

if TYPE_CHECKING:
    from uuid import UUID

    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


# ── Enums & dataclasses ─────────────────────────────────────────────


class CircuitBreakerState(str, enum.Enum):
    """Circuit breaker states."""

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass(frozen=True)
class CircuitBreakerCheck:
    """Result of a circuit breaker check."""

    allowed: bool
    reason: str
    state: CircuitBreakerState
    retry_after_seconds: float = 0.0


class CircuitBreakerOpen(Exception):
    """Raised when the circuit breaker is OPEN and the caller should fail fast."""

    def __init__(self, provider_id: str, retry_after: float) -> None:
        self.provider_id = provider_id
        self.retry_after = retry_after
        super().__init__(f"Circuit breaker OPEN for provider '{provider_id}'. " f"Retry after {retry_after:.1f}s.")


# ── SQL helpers ──────────────────────────────────────────────────────

# We use raw SQL for the upsert+lock pattern because SQLAlchemy's ORM
# doesn't have a clean SELECT FOR UPDATE + INSERT-if-missing in one shot.
# The COALESCE trick handles NULL workspace_id uniqueness.

_SELECT_FOR_UPDATE_SQL = text("""
    SELECT id, workspace_id, provider_id, state, failure_count,
           last_failure_at, last_success_at, opened_at,
           probe_in_flight, cooldown_seconds, failure_threshold, updated_at
    FROM circuit_breaker_state
    WHERE COALESCE(workspace_id, '00000000-0000-0000-0000-000000000000'::uuid)
          = COALESCE(:ws_id, '00000000-0000-0000-0000-000000000000'::uuid)
      AND provider_id = :provider_id
    FOR UPDATE
""")

_INSERT_CLOSED_SQL = text("""
    INSERT INTO circuit_breaker_state (workspace_id, provider_id, state, updated_at)
    VALUES (:ws_id, :provider_id, 'closed', now())
    ON CONFLICT DO NOTHING
""")

_UPDATE_STATE_SQL = text("""
    UPDATE circuit_breaker_state
    SET state = :state,
        failure_count = :failure_count,
        last_failure_at = :last_failure_at,
        last_success_at = :last_success_at,
        opened_at = :opened_at,
        probe_in_flight = :probe_in_flight,
        updated_at = now()
    WHERE COALESCE(workspace_id, '00000000-0000-0000-0000-000000000000'::uuid)
          = COALESCE(:ws_id, '00000000-0000-0000-0000-000000000000'::uuid)
      AND provider_id = :provider_id
""")


# ── Public API ───────────────────────────────────────────────────────


async def _get_or_create_row(
    db: AsyncSession,
    workspace_id: str | UUID | None,
    provider_id: str,
) -> dict:
    """SELECT FOR UPDATE the CB row, inserting a fresh CLOSED row if missing."""
    ws_id_str = str(workspace_id) if workspace_id is not None else None
    result = await db.execute(_SELECT_FOR_UPDATE_SQL, {"ws_id": ws_id_str, "provider_id": provider_id})
    row = result.mappings().first()
    if row is not None:
        return dict(row)

    # No row exists — insert a fresh CLOSED row
    await db.execute(_INSERT_CLOSED_SQL, {"ws_id": ws_id_str, "provider_id": provider_id})
    await db.flush()

    # Re-select with FOR UPDATE to get the row under lock
    result = await db.execute(_SELECT_FOR_UPDATE_SQL, {"ws_id": ws_id_str, "provider_id": provider_id})
    row = result.mappings().first()
    assert row is not None, "INSERT+SELECT should always find the row"
    return dict(row)


async def check_and_allow(
    db: AsyncSession,
    workspace_id: str | UUID | None,
    provider_id: str,
) -> CircuitBreakerCheck:
    """Check if a provider is allowed for this workspace.

    Under a single transaction (SELECT FOR UPDATE):
    - CLOSED → allowed
    - OPEN within cooldown → denied, retry_after_seconds
    - OPEN past cooldown → transition to HALF_OPEN, allowed (probe)
    - HALF_OPEN with probe_in_flight → denied
    - HALF_OPEN without probe → set probe_in_flight, allowed
    """
    now = datetime.now(UTC)
    row = await _get_or_create_row(db, workspace_id, provider_id)
    ws_id_str = str(workspace_id) if workspace_id is not None else None

    state = CircuitBreakerState(row["state"])

    if state == CircuitBreakerState.CLOSED:
        return CircuitBreakerCheck(allowed=True, reason="closed", state=CircuitBreakerState.CLOSED)

    if state == CircuitBreakerState.OPEN:
        opened_at = row["opened_at"]
        cooldown = row["cooldown_seconds"]
        if opened_at is not None:
            elapsed = (now - opened_at).total_seconds()
            if elapsed < cooldown:
                retry_after = cooldown - elapsed
                return CircuitBreakerCheck(
                    allowed=False,
                    reason=f"provider '{provider_id}' circuit open, retry in {retry_after:.0f}s",
                    state=CircuitBreakerState.OPEN,
                    retry_after_seconds=retry_after,
                )
        # Cooldown elapsed → transition to HALF_OPEN
        await db.execute(
            _UPDATE_STATE_SQL,
            {
                "ws_id": ws_id_str,
                "provider_id": provider_id,
                "state": CircuitBreakerState.HALF_OPEN.value,
                "failure_count": row["failure_count"],
                "last_failure_at": row["last_failure_at"],
                "last_success_at": row["last_success_at"],
                "opened_at": row["opened_at"],
                "probe_in_flight": True,
            },
        )
        await db.flush()
        logger.info("Circuit breaker OPEN→HALF_OPEN for %s/%s (probe)", workspace_id, provider_id)
        return CircuitBreakerCheck(
            allowed=True,
            reason="half_open_probe",
            state=CircuitBreakerState.HALF_OPEN,
        )

    # state == HALF_OPEN
    if row["probe_in_flight"]:
        return CircuitBreakerCheck(
            allowed=False,
            reason=f"provider '{provider_id}' half-open, probe in flight",
            state=CircuitBreakerState.HALF_OPEN,
        )

    # No probe in flight — claim the probe
    await db.execute(
        _UPDATE_STATE_SQL,
        {
            "ws_id": ws_id_str,
            "provider_id": provider_id,
            "state": CircuitBreakerState.HALF_OPEN.value,
            "failure_count": row["failure_count"],
            "last_failure_at": row["last_failure_at"],
            "last_success_at": row["last_success_at"],
            "opened_at": row["opened_at"],
            "probe_in_flight": True,
        },
    )
    await db.flush()
    return CircuitBreakerCheck(
        allowed=True,
        reason="half_open_probe",
        state=CircuitBreakerState.HALF_OPEN,
    )


async def record_success(
    db: AsyncSession,
    workspace_id: str | UUID | None,
    provider_id: str,
) -> None:
    """Record a successful call to a provider.

    - CLOSED: reset failure_count to 0
    - HALF_OPEN: transition to CLOSED, reset failure_count, clear probe_in_flight
    """
    row = await _get_or_create_row(db, workspace_id, provider_id)
    ws_id_str = str(workspace_id) if workspace_id is not None else None
    state = CircuitBreakerState(row["state"])

    if state == CircuitBreakerState.CLOSED:
        await db.execute(
            _UPDATE_STATE_SQL,
            {
                "ws_id": ws_id_str,
                "provider_id": provider_id,
                "state": CircuitBreakerState.CLOSED.value,
                "failure_count": 0,
                "last_failure_at": row["last_failure_at"],
                "last_success_at": datetime.now(UTC),
                "opened_at": None,
                "probe_in_flight": False,
            },
        )
    elif state == CircuitBreakerState.HALF_OPEN:
        await db.execute(
            _UPDATE_STATE_SQL,
            {
                "ws_id": ws_id_str,
                "provider_id": provider_id,
                "state": CircuitBreakerState.CLOSED.value,
                "failure_count": 0,
                "last_failure_at": row["last_failure_at"],
                "last_success_at": datetime.now(UTC),
                "opened_at": None,
                "probe_in_flight": False,
            },
        )
        logger.info(
            "Circuit breaker HALF_OPEN→CLOSED for %s/%s (probe succeeded)",
            workspace_id,
            provider_id,
        )

    await db.flush()


async def record_failure(
    db: AsyncSession,
    workspace_id: str | UUID | None,
    provider_id: str,
    *,
    threshold: int | None = None,
) -> bool:
    """Record a failed call to a provider.

    - CLOSED: increment failure_count. If >= threshold, transition to OPEN.
    - HALF_OPEN: transition back to OPEN, reset opened_at.

    Returns True if the state transitioned to OPEN (event should be emitted).
    Emits a circuit_breaker.opened event ONLY on state transitions to OPEN.
    """
    row = await _get_or_create_row(db, workspace_id, provider_id)
    ws_id_str = str(workspace_id) if workspace_id is not None else None
    state = CircuitBreakerState(row["state"])
    now = datetime.now(UTC)

    effective_threshold = threshold if threshold is not None else row["failure_threshold"]
    new_failure_count = row["failure_count"] + 1
    transitioned_to_open = False

    if state == CircuitBreakerState.CLOSED:
        if new_failure_count >= effective_threshold:
            # Transition to OPEN
            await db.execute(
                _UPDATE_STATE_SQL,
                {
                    "ws_id": ws_id_str,
                    "provider_id": provider_id,
                    "state": CircuitBreakerState.OPEN.value,
                    "failure_count": new_failure_count,
                    "last_failure_at": now,
                    "last_success_at": row["last_success_at"],
                    "opened_at": now,
                    "probe_in_flight": False,
                },
            )
            transitioned_to_open = True
            logger.warning(
                "Circuit breaker CLOSED→OPEN for %s/%s (failures=%d, threshold=%d)",
                workspace_id,
                provider_id,
                new_failure_count,
                effective_threshold,
            )
        else:
            # Stay CLOSED, just increment count
            await db.execute(
                _UPDATE_STATE_SQL,
                {
                    "ws_id": ws_id_str,
                    "provider_id": provider_id,
                    "state": CircuitBreakerState.CLOSED.value,
                    "failure_count": new_failure_count,
                    "last_failure_at": now,
                    "last_success_at": row["last_success_at"],
                    "opened_at": None,
                    "probe_in_flight": False,
                },
            )
    elif state == CircuitBreakerState.HALF_OPEN:
        # Probe failed → back to OPEN
        await db.execute(
            _UPDATE_STATE_SQL,
            {
                "ws_id": ws_id_str,
                "provider_id": provider_id,
                "state": CircuitBreakerState.OPEN.value,
                "failure_count": new_failure_count,
                "last_failure_at": now,
                "last_success_at": row["last_success_at"],
                "opened_at": now,
                "probe_in_flight": False,
            },
        )
        transitioned_to_open = True
        logger.warning(
            "Circuit breaker HALF_OPEN→OPEN for %s/%s (probe failed)",
            workspace_id,
            provider_id,
        )

    await db.flush()

    # Emit circuit_breaker.opened event ONLY on state transition to OPEN
    if transitioned_to_open:
        await _emit_opened_event(db, workspace_id, provider_id, new_failure_count, effective_threshold)

    return transitioned_to_open


async def _emit_opened_event(
    db: AsyncSession,
    workspace_id: str | UUID | None,
    provider_id: str,
    failure_count: int,
    cooldown_seconds: int,
) -> None:
    """Emit a circuit_breaker.opened event to the substrate event log.

    Only called on CLOSED→OPEN or HALF_OPEN→OPEN transitions.
    """
    try:
        from app.models.substrate_models import SubstrateEventType
        from app.services.substrate.event_log import get_event_log

        event_log = get_event_log()
        ws_str = str(workspace_id) if workspace_id else "global"
        await event_log.append(
            db,
            run_id=f"cb-{ws_str}",
            events=[
                {
                    "type": SubstrateEventType.CIRCUIT_BREAKER_OPENED,
                    "payload": {
                        "workspace_id": str(workspace_id) if workspace_id else None,
                        "provider_id": provider_id,
                        "failure_count": failure_count,
                        "cooldown_seconds": cooldown_seconds,
                    },
                    "actor": "circuit_breaker",
                }
            ],
        )
    except Exception as e:
        logger.debug("Failed to emit circuit_breaker.opened event: %s", e)
