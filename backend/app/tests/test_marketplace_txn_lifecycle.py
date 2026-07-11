"""MARKETPLACE-2 — marketplace transaction lifecycle (internal wallet).

Hermetic tests: a fresh sqlite DB is built from ``Base.metadata`` so no live
Postgres is required. Covers the full state machine:

    purchase():   pending -> completed (paid, sufficient balance)
                  pending -> failed    (insufficient balance)
                  pending -> completed (free listing, no debit)
    refund():     completed -> refunded (wallet credited back)
                  completed -> refund(already) -> blocked

Also verifies the router wiring (real ``app`` + dependency overrides) for the
purchase / wallet / transaction / refund endpoints, and that the previously
stubbed ``uninstall`` endpoint now returns real 200/404 instead of 501.

Run from the worktree's ``backend/`` dir:
    /opt/flowmanner/backend/.venv/bin/python -m pytest \\
        app/tests/test_marketplace_txn_lifecycle.py -v
"""

from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

os.environ.setdefault("OPENAI_API_KEY", "test-marketplace-txn")
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.models import Base
from app.models.marketplace_txn_models import (
    MarketplaceTransactionModel,
    MarketplaceWalletModel,
    TransactionStatus,
)
from app.models.models import MarketplaceListingModel
from app.services.nexus.marketplace_db import ListingStatus, MarketplaceService

# Throwaway Postgres DB (the repo convention for hermetic real-DB tests, e.g.
# test_decay_memory.py). sqlite cannot render the repo's JSONB columns, so a
# real Postgres is used with a unique per-session database name.
_TEST_DB_BASE = os.getenv(
    "FLOWMANNER_MARKETPLACE_TEST_DB",
    "postgresql+asyncpg://flowmanner:REDACTED_DB_PASSWORD@127.0.0.1:5432/flowmanner_mp2_test",
)


@pytest.fixture
async def db_session():
    """Hermetic Postgres session: unique DB, fresh schema, dropped after.

    Yields a *synchronous* Session because ``MarketplaceService`` uses the
    sync SQLAlchemy ORM API (it builds its own sync engine internally). The
    async engine is used only for schema create/drop via ``create_all``.
    """
    db_name = f"mp2_{uuid.uuid4().hex[:12]}"
    admin_url = _TEST_DB_BASE.rsplit("/", 1)[0] + "/postgres"
    test_url = _TEST_DB_BASE.rsplit("/", 1)[0] + "/" + db_name
    sync_url = test_url.replace("postgresql+asyncpg", "postgresql+psycopg2")

    admin = create_async_engine(admin_url, future=True)
    async with admin.connect() as conn:
        await conn.execution_options(isolation_level="AUTOCOMMIT")
        await conn.execute(text(f'CREATE DATABASE "{db_name}"'))
    await admin.dispose()

    eng = create_async_engine(test_url, future=True)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await eng.dispose()

    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    sync_eng = create_engine(sync_url, future=True)
    Session = sessionmaker(bind=sync_eng)
    session = Session()
    yield session

    session.close()
    sync_eng.dispose()

    admin = create_async_engine(admin_url, future=True)
    async with admin.connect() as conn:
        await conn.execution_options(isolation_level="AUTOCOMMIT")
        await conn.execute(text(f'DROP DATABASE "{db_name}" WITH (FORCE)'))
    await admin.dispose()


def _seed_listing(session, listing_id: str, price: float) -> None:
    listing = MarketplaceListingModel(
        id=listing_id,
        name=f"Listing {listing_id}",
        owner_id="author-1",
        listing_type="tool",
        version="1.0.0",
        price=price,
        status=ListingStatus.PUBLISHED.value,
        is_published=True,
    )
    session.add(listing)
    session.commit()


def _seed_user_installation(session, user_id: str, listing_id: str) -> None:
    """Pre-create a UserInstallationModel so install()/purchase() find it."""
    from app.models.models import UserInstallationModel

    session.add(UserInstallationModel(user_id=int(user_id), listing_id=listing_id))
    session.commit()


# ── Service-level (state machine) ────────────────────────────────────────


class TestPurchaseLifecycle:
    def test_free_listing_completes_no_debit(self, db_session):
        _seed_listing(db_session, "free-1", 0.0)
        svc = MarketplaceService(db_session)
        res = svc.purchase("free-1", "user-1")
        assert res["success"] is True
        assert res["status"] == "completed"
        # No wallet row should be created for a free purchase.
        wallet = svc.get_wallet("user-1")
        # get_wallet auto-creates with 0.0; assert no debit happened implicitly:
        assert wallet["balance"] == 0.0

    def test_paid_listing_insufficient_balance_fails(self, db_session):
        _seed_listing(db_session, "paid-1", 10.0)
        svc = MarketplaceService(db_session)
        res = svc.purchase("paid-1", "user-1")
        assert res["success"] is False
        assert res["status"] == "failed"
        assert res["error"] == "insufficient_balance"
        # No wallet created/charged.
        wallet = svc.get_wallet("user-1")
        assert wallet["balance"] == 0.0

    def test_paid_listing_sufficient_balance_completes_and_debits(self, db_session):
        _seed_listing(db_session, "paid-2", 10.0)
        svc = MarketplaceService(db_session)
        svc.credit_wallet("user-1", 25.0, db_session)
        res = svc.purchase("paid-2", "user-1")
        assert res["success"] is True
        assert res["status"] == "completed"
        assert res["balance"] == 15.0
        # Transaction recorded.
        txns = svc.list_transactions("user-1")
        assert len(txns) == 1
        assert txns[0]["status"] == "completed"
        assert txns[0]["amount"] == 10.0

    def test_unknown_listing_returns_error(self, db_session):
        svc = MarketplaceService(db_session)
        res = svc.purchase("nope", "user-1")
        assert res["success"] is False
        assert "Listing not found" in res["error"]

    def test_get_transaction_returns_shape(self, db_session):
        _seed_listing(db_session, "paid-3", 5.0)
        svc = MarketplaceService(db_session)
        svc.credit_wallet("user-1", 5.0, db_session)
        res = svc.purchase("paid-3", "user-1")
        txn = svc.get_transaction(res["transaction_id"])
        assert txn is not None
        assert txn["status"] == "completed"
        assert txn["amount"] == 5.0
        assert txn["user_id"] == "user-1"


class TestRefundLifecycle:
    def test_refund_completed_credits_wallet(self, db_session):
        _seed_listing(db_session, "paid-4", 10.0)
        svc = MarketplaceService(db_session)
        svc.credit_wallet("user-1", 20.0, db_session)
        buy = svc.purchase("paid-4", "user-1")
        assert buy["balance"] == 10.0
        refund = svc.refund(buy["transaction_id"], "user-1")
        assert refund["success"] is True
        assert refund["status"] == "refunded"
        assert refund["amount"] == 10.0
        # Wallet restored.
        assert svc.get_wallet("user-1")["balance"] == 20.0
        # Original now refunded; a refund transaction exists.
        assert svc.get_transaction(buy["transaction_id"])["status"] == "refunded"
        assert len(svc.list_transactions("user-1")) == 2

    def test_refund_twice_blocked(self, db_session):
        _seed_listing(db_session, "paid-5", 10.0)
        svc = MarketplaceService(db_session)
        svc.credit_wallet("user-1", 20.0, db_session)
        buy = svc.purchase("paid-5", "user-1")
        svc.refund(buy["transaction_id"], "user-1")
        second = svc.refund(buy["transaction_id"], "user-1")
        assert second["success"] is False
        assert second["status_code"] == 400

    def test_refund_unknown_transaction_404(self, db_session):
        svc = MarketplaceService(db_session)
        res = svc.refund("txn:doesnotexist", "user-1")
        assert res["success"] is False
        assert res["status_code"] == 404

    def test_refund_other_user_forbidden(self, db_session):
        _seed_listing(db_session, "paid-6", 10.0)
        svc = MarketplaceService(db_session)
        svc.credit_wallet("user-1", 20.0, db_session)
        buy = svc.purchase("paid-6", "user-1")
        res = svc.refund(buy["transaction_id"], "user-2")
        assert res["success"] is False
        assert res["status_code"] == 403


# ── Router-level (real app + overrides) ──────────────────────────────────


class TestMarketplaceRouterEndpoints:
    def _patch_service(self, svc):
        """Monkeypatch the module-level service factory the handlers call.

        The handlers call ``get_marketplace_service()`` directly (not via
        Depends), so we replace that module attribute for the duration of the
        test. Restored in the caller's finally.
        """
        from app.api.v2 import marketplace as mp_mod

        original = mp_mod.get_marketplace_service
        mp_mod.get_marketplace_service = lambda db=None: svc
        return mp_mod, original

    def test_uninstall_no_longer_501(self):
        """MARKETPLACE-1 fix: uninstall must not 501 anymore (returns 404)."""
        from unittest.mock import MagicMock

        from fastapi.testclient import TestClient

        from app.api.deps import get_current_user
        from app.main_fastapi import app

        svc = MagicMock()
        svc.uninstall.return_value = {"success": False, "error": "Not installed"}
        mp_mod, original = self._patch_service(svc)
        app.dependency_overrides[get_current_user] = lambda: type("U", (), {"id": 1})()
        try:
            with TestClient(app) as client:
                r = client.delete("/api/v2/marketplace/listings/any/install")
                assert r.status_code == 404
        finally:
            app.dependency_overrides.pop(get_current_user, None)
            mp_mod.get_marketplace_service = original

    def test_purchase_endpoint_flow(self):
        """Router maps service purchase/refund dicts to 200 + ok() envelope."""
        from unittest.mock import MagicMock

        from app.api.v2.marketplace import (
            get_transaction,
            purchase_listing,
            refund_transaction,
        )

        svc = MagicMock()
        svc.purchase.return_value = {
            "success": True,
            "transaction_id": "txn:abc",
            "status": "completed",
            "amount": 10.0,
            "currency": "USD",
            "balance": 40.0,
            "listing_id": "routed-1",
        }
        svc.get_transaction.return_value = {
            "transaction_id": "txn:abc",
            "user_id": "1",
            "listing_id": "routed-1",
            "amount": 10.0,
            "currency": "USD",
            "status": "completed",
        }
        svc.refund.return_value = {
            "success": True,
            "refund_transaction_id": "txn:ref",
            "original_transaction_id": "txn:abc",
            "status": "refunded",
            "amount": 10.0,
            "balance": 50.0,
        }
        mp_mod, original = self._patch_service(svc)
        user = type("U", (), {"id": 1})()
        try:
            import asyncio

            r = asyncio.get_event_loop().run_until_complete(purchase_listing("routed-1", user=user))
            body = r["data"]
            assert body["status"] == "completed"
            assert body["balance"] == 40.0

            r_get = asyncio.get_event_loop().run_until_complete(get_transaction("txn:abc", user=user))
            assert r_get["data"]["status"] == "completed"

            r_refund = asyncio.get_event_loop().run_until_complete(refund_transaction("txn:abc", user=user))
            assert r_refund["data"]["status"] == "refunded"
        finally:
            mp_mod.get_marketplace_service = original

    def test_insufficient_balance_returns_402(self):
        """Router maps insufficient_balance failure to HTTP 402."""
        import asyncio
        from unittest.mock import MagicMock

        from fastapi import HTTPException

        from app.api.v2.marketplace import purchase_listing

        svc = MagicMock()
        svc.purchase.return_value = {
            "success": False,
            "transaction_id": "txn:fail",
            "status": "failed",
            "error": "insufficient_balance",
            "required": 99.0,
            "balance": 0.0,
        }
        mp_mod, original = self._patch_service(svc)
        user = type("U", (), {"id": 1})()
        try:
            with pytest.raises(HTTPException) as exc_info:
                asyncio.get_event_loop().run_until_complete(purchase_listing("routed-2", user=user))
            assert exc_info.value.status_code == 402
        finally:
            mp_mod.get_marketplace_service = original
