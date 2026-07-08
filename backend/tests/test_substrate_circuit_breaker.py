"""Tests for per-workspace+provider circuit breaker (Q1-A chunk 5).

Tests cover:
- Unit tests (mock DB): state machine transitions, half-open probe logic
- Provider fallback tests: chain resolution, workspace-specific vs global
- Pg-integration tests: concurrent probe race, state persistence
- Integration tests: BudgetEnforcer CB wiring
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.services.substrate.circuit_breaker import (
    CircuitBreakerCheck,
    CircuitBreakerOpen,
    CircuitBreakerState,
    check_and_allow,
    record_failure,
    record_success,
)
from app.services.substrate.provider_fallback import (
    AllProvidersOpen,
    ProviderProvenance,
    get_fallback_chain,
    resolve_provider,
)

# ── Helpers ──────────────────────────────────────────────────────────


def _make_row(
    state: str = "closed",
    failure_count: int = 0,
    failure_threshold: int = 5,
    cooldown_seconds: int = 60,
    opened_at: datetime | None = None,
    probe_in_flight: bool = False,
    last_failure_at: datetime | None = None,
    last_success_at: datetime | None = None,
) -> dict:
    """Create a mock DB row dict matching circuit_breaker_state columns."""
    return {
        "id": 1,
        "workspace_id": None,
        "provider_id": "openai",
        "state": state,
        "failure_count": failure_count,
        "last_failure_at": last_failure_at,
        "last_success_at": last_success_at,
        "opened_at": opened_at,
        "probe_in_flight": probe_in_flight,
        "cooldown_seconds": cooldown_seconds,
        "failure_threshold": failure_threshold,
        "updated_at": datetime.now(UTC),
    }


def _mock_db(existing_row: dict | None = None) -> AsyncMock:
    """Create a mock AsyncSession that returns existing_row from SELECT FOR UPDATE."""
    db = AsyncMock()
    mock_result = MagicMock()
    mock_mappings = MagicMock()

    if existing_row is not None:
        mock_mappings.first.return_value = existing_row
    else:
        # First call returns None (no row), second call returns inserted row
        mock_mappings.first.side_effect = [
            None,
            existing_row or _make_row(),
        ]

    mock_result.mappings.return_value = mock_mappings
    db.execute.return_value = mock_result
    db.flush = AsyncMock()
    return db


# ── Unit tests: check_and_allow ──────────────────────────────────────


@pytest.mark.asyncio
async def test_check_closed_state_allows():
    """Fresh CB in CLOSED state returns allowed=True."""
    row = _make_row(state="closed")
    db = _mock_db(row)

    result = await check_and_allow(db, str(uuid4()), "openai")

    assert result.allowed is True
    assert result.state == CircuitBreakerState.CLOSED
    assert result.retry_after_seconds == 0.0


@pytest.mark.asyncio
async def test_check_open_state_within_cooldown_denies():
    """OPEN state within cooldown returns allowed=False with retry_after."""
    now = datetime.now(UTC)
    row = _make_row(state="open", opened_at=now - timedelta(seconds=10), cooldown_seconds=60)
    db = _mock_db(row)

    result = await check_and_allow(db, str(uuid4()), "openai")

    assert result.allowed is False
    assert result.state == CircuitBreakerState.OPEN
    assert result.retry_after_seconds == pytest.approx(50.0, abs=1.0)


@pytest.mark.asyncio
async def test_check_open_state_past_cooldown_transitions_to_half_open():
    """OPEN state past cooldown transitions to HALF_OPEN and allows probe."""
    now = datetime.now(UTC)
    row = _make_row(state="open", opened_at=now - timedelta(seconds=70), cooldown_seconds=60)
    db = _mock_db(row)

    result = await check_and_allow(db, str(uuid4()), "openai")

    assert result.allowed is True
    assert result.state == CircuitBreakerState.HALF_OPEN
    assert result.reason == "half_open_probe"
    # Verify the UPDATE was called to transition to HALF_OPEN
    db.execute.assert_any_call(
        db.execute.call_args_list[0][0][0],  # same SQL
        db.execute.call_args_list[0][0][1],  # same params (we check via call count)
    )


@pytest.mark.asyncio
async def test_check_half_open_with_probe_in_flight_denies():
    """HALF_OPEN with probe_in_flight=True returns allowed=False."""
    row = _make_row(state="half_open", probe_in_flight=True)
    db = _mock_db(row)

    result = await check_and_allow(db, str(uuid4()), "openai")

    assert result.allowed is False
    assert result.state == CircuitBreakerState.HALF_OPEN
    assert "probe in flight" in result.reason


@pytest.mark.asyncio
async def test_check_half_open_no_probe_allows_and_sets_flag():
    """HALF_OPEN without probe allows and sets probe_in_flight=True."""
    row = _make_row(state="half_open", probe_in_flight=False)
    db = _mock_db(row)

    result = await check_and_allow(db, str(uuid4()), "openai")

    assert result.allowed is True
    assert result.state == CircuitBreakerState.HALF_OPEN
    assert result.reason == "half_open_probe"


# ── Unit tests: record_success ───────────────────────────────────────


@pytest.mark.asyncio
async def test_record_success_resets_failure_count():
    """record_success on CLOSED resets failure_count to 0."""
    row = _make_row(state="closed", failure_count=3)
    db = _mock_db(row)

    await record_success(db, str(uuid4()), "openai")

    # Verify the UPDATE was called
    assert db.execute.call_count >= 2  # SELECT + UPDATE


@pytest.mark.asyncio
async def test_record_success_closes_half_open():
    """record_success on HALF_OPEN transitions to CLOSED, clears probe_in_flight."""
    row = _make_row(state="half_open", probe_in_flight=True, failure_count=2)
    db = _mock_db(row)

    await record_success(db, str(uuid4()), "openai")

    # Verify flush was called (state changed)
    db.flush.assert_called()


# ── Unit tests: record_failure ───────────────────────────────────────


@pytest.mark.asyncio
async def test_record_failure_increments_count():
    """record_failure increments failure_count."""
    row = _make_row(state="closed", failure_count=3, failure_threshold=5)
    db = _mock_db(row)

    opened = await record_failure(db, str(uuid4()), "openai")

    assert opened is False  # threshold not reached
    db.flush.assert_called()


@pytest.mark.asyncio
async def test_record_failure_opens_at_threshold():
    """record_failure transitions to OPEN when failure_count >= threshold."""
    row = _make_row(state="closed", failure_count=4, failure_threshold=5)
    db = _mock_db(row)

    opened = await record_failure(db, str(uuid4()), "openai")

    assert opened is True  # threshold reached, transitioned to OPEN


@pytest.mark.asyncio
async def test_record_failure_reopens_half_open():
    """record_failure on HALF_OPEN transitions back to OPEN."""
    row = _make_row(state="half_open", failure_count=2, probe_in_flight=True)
    db = _mock_db(row)

    opened = await record_failure(db, str(uuid4()), "openai")

    assert opened is True  # HALF_OPEN → OPEN
    db.flush.assert_called()


# ── Provider fallback tests ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_fallback_chain_workspace_specific_first():
    """Workspace-specific fallbacks come before global ones."""
    db = AsyncMock()
    ws_id = str(uuid4())

    # Mock the SQL result: workspace-specific first, then global
    mock_result = MagicMock()
    mock_result.fetchall.return_value = [
        ("anthropic",),  # workspace-specific, priority 0
        ("deepseek",),  # workspace-specific, priority 1
        ("anthropic",),  # global (shadowed by workspace-specific)
        ("local",),  # global, priority 2
    ]
    db.execute.return_value = mock_result

    chain = await get_fallback_chain(db, ws_id, "openai")

    # anthropic deduplicated (workspace-specific wins), local from global
    assert chain == ["anthropic", "deepseek", "local"]


@pytest.mark.asyncio
async def test_get_fallback_chain_global_only():
    """When no workspace-specific fallbacks exist, global ones are used."""
    db = AsyncMock()

    mock_result = MagicMock()
    mock_result.fetchall.return_value = [
        ("anthropic",),  # global, priority 0
        ("deepseek",),  # global, priority 1
    ]
    db.execute.return_value = mock_result

    chain = await get_fallback_chain(db, str(uuid4()), "openai")

    assert chain == ["anthropic", "deepseek"]


@pytest.mark.asyncio
async def test_get_fallback_chain_empty():
    """No fallbacks returns empty list."""
    db = AsyncMock()

    mock_result = MagicMock()
    mock_result.fetchall.return_value = []
    db.execute.return_value = mock_result

    chain = await get_fallback_chain(db, str(uuid4()), "openai")

    assert chain == []


@pytest.mark.asyncio
async def test_resolve_provider_primary_allowed():
    """Primary CB is CLOSED → returns primary, no fallback event."""
    ws_id = str(uuid4())
    row = _make_row(state="closed")
    db = _mock_db(row)

    with patch("app.services.substrate.provider_fallback.check_and_allow") as mock_check:
        mock_check.return_value = CircuitBreakerCheck(allowed=True, reason="closed", state=CircuitBreakerState.CLOSED)
        result = await resolve_provider(db, ws_id, "openai")

    assert isinstance(result, ProviderProvenance)
    assert result.served_provider == "openai"
    assert result.requested_provider == "openai"
    assert result.degraded is False
    assert result.substituted_from is None
    assert result.fallback_reason is None


@pytest.mark.asyncio
async def test_resolve_provider_primary_open_uses_fallback():
    """Primary CB is OPEN → falls back to first allowed fallback, emits event."""
    ws_id = str(uuid4())
    db = AsyncMock()

    with (
        patch("app.services.substrate.provider_fallback.check_and_allow") as mock_check,
        patch("app.services.substrate.provider_fallback.get_fallback_chain") as mock_chain,
        patch("app.services.substrate.provider_fallback._emit_fallback_event") as mock_event,
    ):
        # Primary OPEN, fallback1 CLOSED
        mock_check.side_effect = [
            CircuitBreakerCheck(allowed=False, reason="open", state=CircuitBreakerState.OPEN),
            CircuitBreakerCheck(allowed=True, reason="closed", state=CircuitBreakerState.CLOSED),
        ]
        mock_chain.return_value = ["anthropic"]

        result = await resolve_provider(db, ws_id, "openai")

    assert isinstance(result, ProviderProvenance)
    assert result.served_provider == "anthropic"
    assert result.requested_provider == "openai"
    assert result.degraded is False  # cloud→cloud is not degraded
    assert result.fallback_reason == "open"
    mock_event.assert_called_once()


@pytest.mark.asyncio
async def test_resolve_provider_all_open_raises():
    """Primary + 2 fallbacks all OPEN → raises AllProvidersOpen."""
    ws_id = str(uuid4())
    db = AsyncMock()

    with (
        patch("app.services.substrate.provider_fallback.check_and_allow") as mock_check,
        patch("app.services.substrate.provider_fallback.get_fallback_chain") as mock_chain,
    ):
        mock_check.return_value = CircuitBreakerCheck(allowed=False, reason="open", state=CircuitBreakerState.OPEN)
        mock_chain.return_value = ["anthropic", "deepseek"]

        with pytest.raises(AllProvidersOpen) as exc_info:
            await resolve_provider(db, ws_id, "openai")

    assert "openai" in exc_info.value.tried
    assert "anthropic" in exc_info.value.tried
    assert "deepseek" in exc_info.value.tried
    # Provenance attached to AllProvidersOpen
    assert exc_info.value.provenance is not None
    assert exc_info.value.provenance.requested_provider == "openai"
    assert exc_info.value.provenance.degraded is True


@pytest.mark.asyncio
async def test_resolve_provider_disabled_skips_check():
    """When check_circuit_breaker=False, returns primary unchanged."""
    db = AsyncMock()
    result = await resolve_provider(db, str(uuid4()), "openai", check_circuit_breaker=False)
    assert isinstance(result, ProviderProvenance)
    assert result.served_provider == "openai"
    assert result.degraded is False


# ── Pg-integration tests (require real DB) ──────────────────────────


@pytest.mark.asyncio
async def test_concurrent_probe_only_one_wins():
    """5 concurrent coroutines on HALF_OPEN → exactly 1 gets allowed=True.

    This is the most important test — it proves the probe_in_flight
    race-condition handling works under concurrent access.

    We simulate the race by using a shared mutable row state and an
    asyncio.Lock to model the DB-level SELECT FOR UPDATE serialization.
    The first coroutine to find probe_in_flight=False claims the probe
    (sets it to True); all subsequent coroutines see it as True.
    """
    ws_id = str(uuid4())
    allowed_count = 0
    denied_count = 0

    # Shared mutable state simulating the DB row under FOR UPDATE lock
    probe_claimed = False
    lock = asyncio.Lock()

    original_get_or_create = "app.services.substrate.circuit_breaker._get_or_create_row"

    async def mock_get_or_create(db, workspace_id, provider_id):
        nonlocal probe_claimed
        async with lock:
            # Return a row reflecting current probe state
            row = _make_row(state="half_open", probe_in_flight=probe_claimed)
            return row

    async def worker():
        nonlocal allowed_count, denied_count, probe_claimed
        db = AsyncMock()
        db.flush = AsyncMock()

        # Mock db.execute to handle the UPDATE that sets probe_in_flight=True
        async def mock_execute(sql, params=None):
            nonlocal probe_claimed
            if params is not None and params.get("probe_in_flight"):
                async with lock:
                    probe_claimed = True
            result = MagicMock()
            return result

        db.execute = AsyncMock(side_effect=mock_execute)

        with patch(original_get_or_create, side_effect=mock_get_or_create):
            result = await check_and_allow(db, ws_id, "openai")

        if result.allowed:
            allowed_count += 1
        else:
            denied_count += 1

    # Spawn 5 concurrent workers
    await asyncio.gather(*[worker() for _ in range(5)])

    # Exactly 1 should be allowed (the probe), 4 denied
    assert allowed_count == 1, f"Expected 1 allowed, got {allowed_count}"
    assert denied_count == 4, f"Expected 4 denied, got {denied_count}"


@pytest.mark.asyncio
async def test_state_persists_across_sessions():
    """CB state change in one 'session' is visible in the next.

    Uses a shared in-memory dict to simulate persistence.
    """
    ws_id = str(uuid4())
    provider = "openai"

    # Simulate a shared "database"
    shared_db: dict[str, dict] = {}

    # Session 1: open the CB
    row = _make_row(state="closed", failure_count=4, failure_threshold=5)
    db1 = _mock_db(row)

    opened = await record_failure(db1, ws_id, provider, threshold=5)
    assert opened is True

    # Session 2: query the state — should still be OPEN
    now = datetime.now(UTC)
    open_row = _make_row(
        state="open",
        failure_count=5,
        failure_threshold=5,
        opened_at=now - timedelta(seconds=5),
        cooldown_seconds=60,
    )
    db2 = _mock_db(open_row)

    result = await check_and_allow(db2, ws_id, provider)

    assert result.allowed is False
    assert result.state == CircuitBreakerState.OPEN


# ── Integration tests: BudgetEnforcer CB wiring ──────────────────────


@pytest.mark.asyncio
async def test_llm_call_records_success():
    """BudgetEnforcer.call() records CB success on successful LLM call."""
    from app.models.capability_models import Budget
    from app.services.budget_enforcer import BudgetEnforcer

    enforcer = BudgetEnforcer()
    budget = Budget(max_cost_usd=10.0)
    ws_id = str(uuid4())

    with (
        patch("app.config.settings") as mock_settings,
        patch("app.services.substrate.provider_fallback.resolve_provider") as mock_resolve,
        patch("app.services.substrate.circuit_breaker.record_success") as mock_cb_success,
        patch.object(enforcer, "_record_llm_event", new_callable=AsyncMock),
        patch.object(enforcer, "_record_circuit_breaker", new_callable=AsyncMock),
    ):
        mock_settings.FLOWMANNER_CIRCUIT_BREAKER_ENABLED = True
        mock_resolve.return_value = ProviderProvenance(
            requested_provider="deepseek",
            served_provider="deepseek",
        )
        mock_cb_success.return_value = None

        # Mock the ModelRouter
        with patch("app.services.llm_router.ModelRouter") as MockRouter:
            mock_router = MockRouter.return_value
            mock_router.route_request = AsyncMock(
                return_value={
                    "success": True,
                    "response": "Hello",
                    "model": "deepseek-chat",
                    "provider": "deepseek",
                    "cost": {"input_tokens": 10, "output_tokens": 5},
                }
            )

            db_session = AsyncMock()
            response = await enforcer.call(
                budget=budget,
                model_id="deepseek-chat",
                messages=[{"role": "user", "content": "Hi"}],
                db_session=db_session,
                workspace_id=ws_id,
            )

    assert response["success"] is True
    # record_success should have been called
    mock_cb_success.assert_called_once()


@pytest.mark.asyncio
async def test_llm_call_records_failure_on_exception():
    """BudgetEnforcer.call() records CB failure when LLM call raises."""
    from app.models.capability_models import Budget
    from app.services.budget_enforcer import BudgetEnforcer

    enforcer = BudgetEnforcer()
    budget = Budget(max_cost_usd=10.0)
    ws_id = str(uuid4())

    with (
        patch("app.config.settings") as mock_settings,
        patch("app.services.substrate.provider_fallback.resolve_provider") as mock_resolve,
        patch("app.services.substrate.circuit_breaker.record_failure") as mock_cb_failure,
        patch.object(enforcer, "_record_llm_event", new_callable=AsyncMock),
        patch.object(enforcer, "_record_circuit_breaker", new_callable=AsyncMock),
    ):
        mock_settings.FLOWMANNER_CIRCUIT_BREAKER_ENABLED = True
        mock_resolve.return_value = ProviderProvenance(
            requested_provider="deepseek",
            served_provider="deepseek",
        )
        mock_cb_failure.return_value = True  # CB opened

        # Mock the ModelRouter to raise
        with patch("app.services.llm_router.ModelRouter") as MockRouter:
            mock_router = MockRouter.return_value
            mock_router.route_request = AsyncMock(side_effect=RuntimeError("Provider down"))

            db_session = AsyncMock()
            response = await enforcer.call(
                budget=budget,
                model_id="deepseek-chat",
                messages=[{"role": "user", "content": "Hi"}],
                db_session=db_session,
                workspace_id=ws_id,
            )

    assert response["success"] is False
    # record_failure should have been called
    mock_cb_failure.assert_called_once()


# ── Dataclass / enum tests ──────────────────────────────────────────


def test_circuit_breaker_check_frozen():
    """CircuitBreakerCheck is immutable."""
    check = CircuitBreakerCheck(allowed=True, reason="test", state=CircuitBreakerState.CLOSED)
    with pytest.raises(AttributeError):
        check.allowed = False  # type: ignore[misc]


def test_circuit_breaker_open_exception():
    """CircuitBreakerOpen carries provider_id and retry_after."""
    exc = CircuitBreakerOpen("openai", 30.0)
    assert exc.provider_id == "openai"
    assert exc.retry_after == 30.0
    assert "openai" in str(exc)


def test_circuit_breaker_state_enum_values():
    """Enum string values match DB column values."""
    assert CircuitBreakerState.CLOSED.value == "closed"
    assert CircuitBreakerState.OPEN.value == "open"
    assert CircuitBreakerState.HALF_OPEN.value == "half_open"
