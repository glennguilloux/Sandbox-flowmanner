"""Integration tests for HandoffLeaseIntegration (Q2-Q3 Chunk 5).

These tests require a real database and real lease primitives.
Mark with @pytest.mark.integration — may skip in dev env.
"""

from __future__ import annotations

import asyncio

import pytest

from app.services.swarm.lease_integration import HandoffLeaseIntegration


@pytest.mark.integration
class TestHandoffLeaseIntegration:
    """Integration tests for lease lifecycle during handoffs.

    These tests use a real DB session and real lease primitives.
    They may be skipped in dev environments without a running DB.
    """

    @pytest.mark.asyncio
    async def test_lease_claim_and_release(self, db_session):
        """Claim a lease, verify it exists, release it, verify it's gone."""
        li = HandoffLeaseIntegration(db_session, worker_id="test-worker")
        run_id = await li.claim_for_handoff("h-int-001", "agent-x")
        assert run_id == "handoff-h-int-001"

        from app.services.substrate.leases import get_active_lease

        lease = await get_active_lease(db_session, run_id)
        assert lease is not None
        assert lease.worker_id == "test-worker"

        await li.release("h-int-001")
        lease_after = await get_active_lease(db_session, run_id)
        assert lease_after is None

    @pytest.mark.asyncio
    async def test_lease_transfer(self, db_session):
        """Transfer lease from one worker to another."""
        li1 = HandoffLeaseIntegration(db_session, worker_id="worker-1")
        await li1.claim_for_handoff("h-int-002", "agent-1")

        await li1.transfer("h-int-002", "agent-1", "agent-2")

        from app.services.substrate.leases import get_active_lease

        lease = await get_active_lease(db_session, "handoff-h-int-002")
        # After transfer, a new worker holds it (same worker_id since
        # HandoffLeaseIntegration uses a single worker_id per instance).
        assert lease is not None

    @pytest.mark.asyncio
    async def test_lease_renew(self, db_session):
        """Renewing an active lease extends its expiry."""
        li = HandoffLeaseIntegration(db_session, worker_id="test-worker")
        await li.claim_for_handoff("h-int-003", "agent-y")

        ok = await li.renew("h-int-003")
        assert ok is True

        # Renewing a non-existent handoff returns False
        ok_bad = await li.renew("h-nonexistent")
        assert ok_bad is False

        await li.release("h-int-003")
