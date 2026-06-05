import os
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

os.environ.setdefault("STRIPE_SECRET_KEY", "sk_test_xxx")

@pytest.mark.asyncio
async def test_get_partner_dashboard():
    """Test partner dashboard endpoint."""
    from app.api.v1.partner import get_partner_dashboard
    
    user = SimpleNamespace(**{"id": 1, "is_partner_admin": True, "partner_id": 1})
    
    mock_db = MagicMock()
    mock_db.execute = AsyncMock()
    execute_result = MagicMock()
    mock_db.execute.return_value = execute_result
    
    # Mock partner
    partner = MagicMock()
    partner.id = 1
    
    # Mock revenues
    execute_result.scalars.return_value.first.return_value = partner
    # scalar side effects: current_month, total_volume, total_referrals, pending, then 6 months of trend
    execute_result.scalar.side_effect = [100.0, 50, 10, 25.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
    
    with patch("app.api.v1.partner.get_current_user", return_value=user):
        result = await get_partner_dashboard(user=user, db=mock_db)
    
    assert result["current_month_revenue"] == 100.0
    assert result["total_mission_volume"] == 50
    assert result["total_referrals"] == 10
    assert result["pending_payout"] == 25.0
    assert len(result["revenue_trend"]) == 6


@pytest.mark.asyncio
async def test_get_partner_dashboard_not_admin():
    """Test that non-partner-admins cannot access dashboard."""
    from fastapi import HTTPException

    from app.api.v1.partner import get_partner_dashboard
    
    user = SimpleNamespace(**{"id": 1, "is_partner_admin": False})
    
    with pytest.raises(HTTPException) as exc_info:
        await get_partner_dashboard(user=user, db=MagicMock())
    
    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_list_partner_revenues():
    """Test listing partner revenue records."""
    from app.api.v1.partner import list_revenues
    
    user = SimpleNamespace(**{"id": 1, "is_partner_admin": True, "partner_id": 1})
    
    mock_db = MagicMock()
    mock_db.execute = AsyncMock()
    execute_result = MagicMock()
    mock_db.execute.return_value = execute_result
    
    mock_revenue = MagicMock()
    mock_revenue.id = 1
    mock_revenue.mission_id = "abc-123"
    mock_revenue.mission_volume = 5
    mock_revenue.revenue_amount = 50.0
    mock_revenue.period_month = "2026-04"
    mock_revenue.is_paid = False
    mock_revenue.paid_at = None
    
    execute_result.scalars.return_value.all.return_value = [mock_revenue]
    
    with patch("app.api.v1.partner.get_current_user", return_value=user):
        result = await list_revenues(user=user, db=mock_db)
    
    assert len(result) == 1
    assert result[0]["revenue_amount"] == 50.0


@pytest.mark.asyncio
async def test_request_payout_success():
    """Test successful payout request."""
    from app.api.v1.partner import PayoutRequest, request_payout
    
    user = SimpleNamespace(**{"id": 1, "is_partner_admin": True, "partner_id": 1})
    
    mock_db = MagicMock()
    mock_db.execute = AsyncMock()
    mock_db.commit = AsyncMock()
    
    # Mock partner with Stripe account
    partner = MagicMock()
    partner.id = 1
    partner.stripe_account_id = "acct_123456"
    
    execute_result = MagicMock()
    mock_db.execute.return_value = execute_result
    execute_result.scalars.return_value.first.return_value = partner
    # scalar side effects: pending amount
    execute_result.scalar.side_effect = [100.0]
    # scalars().all() for unpaid revenues
    unpaid_revenue = MagicMock()
    unpaid_revenue.revenue_amount = 100.0
    execute_result.scalars.return_value.all.return_value = [unpaid_revenue]
    
    payout_request = PayoutRequest(amount=100.0)
    
    with patch("app.api.v1.partner.get_current_user", return_value=user), \
         patch("stripe.Transfer.create") as mock_transfer:
        mock_transfer.return_value = MagicMock(id="po_mock_12345")
        result = await request_payout(payout_request, user=user, db=mock_db)
    
    assert result.success == True
    assert result.amount == 100.0
    assert result.payout_id is not None


@pytest.mark.asyncio
async def test_request_payout_no_stripe():
    """Test payout request fails without Stripe account."""
    from fastapi import HTTPException

    from app.api.v1.partner import PayoutRequest, request_payout
    
    user = SimpleNamespace(**{"id": 1, "is_partner_admin": True, "partner_id": 1})
    
    mock_db = MagicMock()
    mock_db.execute = AsyncMock()
    execute_result = MagicMock()
    mock_db.execute.return_value = execute_result
    
    # Mock partner without Stripe account
    partner = MagicMock()
    partner.stripe_account_id = None
    execute_result.scalars.return_value.first.return_value = partner
    
    payout_request = PayoutRequest(amount=100.0)
    
    with patch("app.api.v1.partner.get_current_user", return_value=user), pytest.raises(HTTPException) as exc_info:
        await request_payout(payout_request, user=user, db=mock_db)
    
    assert exc_info.value.status_code == 400
