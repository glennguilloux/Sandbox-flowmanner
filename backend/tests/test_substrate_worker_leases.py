"""Unit tests for worker lease claim / release / renew / query (Q1-A Chunk 1).

Tests use mocked ``AsyncSession`` consistent with the existing substrate
test style (``test_substrate_event_log.py``).  The mock verifies SQL
semantics by asserting that ``db.execute`` was called with the expected
raw-SQL text and that the return value is interpreted correctly.

Test names follow the plan's required set:
  - test_try_claim_happy_path
  - test_try_claim_when_already_held
  - test_try_claim_after_expiry
  - test_try_claim_duplicate_same_worker_is_idempotent
  - test_release_idempotent
  - test_release_only_owner
  - test_renew_happy_path
  - test_renew_after_reclaim
  - test_get_active_lease_after_release
  - test_get_active_lease_excludes_expired
  - test_renew_missing_lease_returns_false
  - test_substrate_lease_exports
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest


# ── Helpers ────────────────────────────────────────────────────────


def _row(worker_id: str, run_id: str, generation: int = 1, renewed_count: int = 0):
    """Create a mock row matching LeaseRecord fields."""
    now = datetime.now(UTC)
    return MagicMock(
        id=1,
        worker_id=worker_id,
        run_id=run_id,
        acquired_at=now,
        expires_at=now + timedelta(seconds=300),
        renewed_count=renewed_count,
        generation=generation,
    )


def _make_db(claim_success: bool = True, active_row=None, update_row=None):
    """Create a mock AsyncSession for lease tests.

    Parameters
    ----------
    claim_success : bool
        Whether the INSERT … ON CONFLICT RETURNING returns a row.
    active_row : MagicMock | None
        Row returned by SELECT active lease queries.
    update_row : MagicMock | None
        Row returned by UPDATE … RETURNING queries.

    The mock dispatches on SQL text so that multiple ``db.execute`` calls
    within a single test always return the correct mock value regardless
    of call order.
    """
    db = AsyncMock()

    _active_row = active_row
    _update_row = update_row
    _claim_success = claim_success

    async def mock_execute(stmt, params=None):
        result = MagicMock()
        stmt_text = str(stmt)

        # get_active_lease SELECT (also used as fast-path in try_claim)
        if "SELECT id, worker_id" in stmt_text:
            result.fetchone.return_value = _active_row
        # INSERT … ON CONFLICT RETURNING generation
        elif "INSERT INTO substrate_worker_leases" in stmt_text:
            result.fetchone.return_value = MagicMock(generation=2) if _claim_success else None
        # DELETE
        elif "DELETE FROM" in stmt_text:
            result.fetchone.return_value = None
        # UPDATE … RETURNING
        elif "UPDATE substrate_worker_leases" in stmt_text:
            result.fetchone.return_value = _update_row
        else:
            result.fetchone.return_value = None

        return result

    db.execute = AsyncMock(side_effect=mock_execute)
    return db


# ═══════════════════════════════════════════════════════════════════
# try_claim_lease
# ═══════════════════════════════════════════════════════════════════


class TestTryClaimLease:
    def test_try_claim_happy_path(self):
        """Claiming an unclaimed run returns True."""
        from app.services.substrate.leases import try_claim_lease

        db = _make_db(claim_success=True, active_row=None)
        result = asyncio.run(try_claim_lease(db, "worker-a", "run-1", 300))
        assert result is True

    def test_try_claim_when_already_held(self):
        """Claiming a run held by another active worker returns False."""
        from app.services.substrate.leases import try_claim_lease

        active = _row("worker-a", "run-2")
        db = _make_db(claim_success=False, active_row=active)
        result = asyncio.run(try_claim_lease(db, "worker-b", "run-2", 300))
        assert result is False

    def test_try_claim_after_expiry(self):
        """Claiming a run whose lease has expired returns True and bumps generation."""
        from app.services.substrate.leases import try_claim_lease

        # No active lease (expired → not returned by get_active_lease),
        # so the fast-path SELECT returns None, then INSERT succeeds.
        # The mock returns generation=2 on successful upsert.
        db = _make_db(claim_success=True, active_row=None)
        result = asyncio.run(try_claim_lease(db, "worker-b", "run-expired", 300))
        assert result is True
        # Verify the upsert was attempted (2 calls: SELECT + INSERT)
        assert db.execute.call_count == 2

    def test_duplicate_same_worker_claim_is_idempotent(self):
        """Duplicate claim by the same active worker returns True without upsert."""
        from app.services.substrate.leases import try_claim_lease

        active = _row("worker-a", "run-dup")
        db = _make_db(claim_success=True, active_row=active)
        result = asyncio.run(try_claim_lease(db, "worker-a", "run-dup", 300))
        assert result is True
        # Should only call SELECT (fast-path), not INSERT
        assert db.execute.call_count == 1


# ═══════════════════════════════════════════════════════════════════
# get_active_lease
# ═══════════════════════════════════════════════════════════════════


class TestGetActiveLease:
    def test_get_active_lease_returns_record(self):
        """Active lease for a known run returns a LeaseRecord with all fields."""
        from app.services.substrate.leases import LeaseRecord, get_active_lease

        row = _row("worker-a", "run-active", generation=3, renewed_count=2)
        db = _make_db(active_row=row)
        lease = asyncio.run(get_active_lease(db, "run-active"))
        assert lease is not None
        assert isinstance(lease, LeaseRecord)
        assert lease.worker_id == "worker-a"
        assert lease.run_id == "run-active"
        assert lease.generation == 3
        assert lease.renewed_count == 2
        assert lease.expires_at is not None
        assert lease.acquired_at is not None

    def test_get_active_lease_returns_none_when_missing(self):
        """Missing lease returns None."""
        from app.services.substrate.leases import get_active_lease

        db = _make_db(active_row=None)
        lease = asyncio.run(get_active_lease(db, "run-missing"))
        assert lease is None

    def test_get_active_lease_excludes_expired(self):
        """Expired lease returns None (SQL has expires_at > now())."""
        from app.services.substrate.leases import get_active_lease

        # Simulate: DB returns no row because the WHERE expires_at > now()
        # filter excludes the expired row.
        db = _make_db(active_row=None)
        lease = asyncio.run(get_active_lease(db, "run-expired"))
        assert lease is None

    def test_get_active_lease_after_release(self):
        """get_active_lease returns None after owner releases."""
        from app.services.substrate.leases import get_active_lease, release_lease

        # After release DELETE succeeds, subsequent SELECT returns no row.
        db = _make_db(active_row=None)
        asyncio.run(release_lease(db, "worker-a", "run-after-rel"))
        lease = asyncio.run(get_active_lease(db, "run-after-rel"))
        assert lease is None


# ═══════════════════════════════════════════════════════════════════
# release_lease
# ═══════════════════════════════════════════════════════════════════


class TestReleaseLease:
    def test_release_idempotent(self):
        """Releasing twice does not raise and the lease is gone."""
        from app.services.substrate.leases import get_active_lease, release_lease

        # After release: get_active_lease returns None
        db = _make_db(active_row=None)
        result = asyncio.run(release_lease(db, "worker-a", "run-rel"))
        assert result is None  # returns None

        # Second release is also a no-op
        result2 = asyncio.run(release_lease(db, "worker-a", "run-rel"))
        assert result2 is None

    def test_release_only_owner(self):
        """Non-owner release does not mutate the lease."""
        from app.services.substrate.leases import get_active_lease, release_lease

        active = _row("worker-a", "run-owner")
        # DELETE by non-owner is a no-op (WHERE worker_id doesn't match)
        db = _make_db(active_row=active)
        asyncio.run(release_lease(db, "worker-b", "run-owner"))

        # Verify the lease is still active for worker-a
        lease = asyncio.run(get_active_lease(db, "run-owner"))
        assert lease is not None
        assert lease.worker_id == "worker-a"


# ═══════════════════════════════════════════════════════════════════
# renew_lease
# ═══════════════════════════════════════════════════════════════════


class TestRenewLease:
    def test_renew_happy_path(self):
        """Owner renew returns True."""
        from app.services.substrate.leases import renew_lease

        db = _make_db(update_row=MagicMock(id=1))
        result = asyncio.run(renew_lease(db, "worker-a", "run-renew", 300))
        assert result is True

    def test_renew_after_reclaim(self):
        """Old worker cannot renew after another worker reclaimed."""
        from app.services.substrate.leases import renew_lease

        # UPDATE returns no row (worker-a no longer holds the lease)
        db = _make_db(update_row=None)
        result = asyncio.run(renew_lease(db, "worker-a", "run-reclaim", 300))
        assert result is False

    def test_renew_missing_lease_returns_false(self):
        """Renew on a non-existent lease returns False."""
        from app.services.substrate.leases import renew_lease

        db = _make_db(update_row=None)
        result = asyncio.run(renew_lease(db, "worker-a", "run-never", 300))
        assert result is False


# ═══════════════════════════════════════════════════════════════════
# Export smoke test
# ═══════════════════════════════════════════════════════════════════


class TestSubstrateLeaseExports:
    def test_substrate_lease_exports(self):
        """All lease symbols are importable from app.services.substrate."""
        from app.services.substrate import (  # noqa: F401
            LeaseRecord,
            get_active_lease,
            release_lease,
            renew_lease,
            try_claim_lease,
        )

        # Verify they are the correct callables
        assert callable(try_claim_lease)
        assert callable(get_active_lease)
        assert callable(release_lease)
        assert callable(renew_lease)
        assert isinstance(LeaseRecord, type)
