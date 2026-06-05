from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_list_tiers():
    """Test listing subscription tiers."""
    from app.api.v1.subscription import list_tiers

    mock_db = MagicMock()
    mock_db.execute = AsyncMock()

    mock_result = MagicMock()
    # Use SimpleNamespace instead of MagicMock to avoid the 'name' kwarg conflict
    # (MagicMock's 'name' kwarg sets the mock's repr, not an attribute)
    from types import SimpleNamespace

    tiers = [
        SimpleNamespace(
            id=1,
            name="free",
            display_name="Free",
            description="Free tier",
            price_monthly=0.0,
            missions_per_day=5,
            missions_per_month=150,
            max_concurrent_missions=1,
            has_priority_support=False,
            has_api_access=False,
            has_custom_models=False,
        ),
        SimpleNamespace(
            id=2,
            name="pro",
            display_name="Pro",
            description="Pro tier",
            price_monthly=29.99,
            missions_per_day=50,
            missions_per_month=1500,
            max_concurrent_missions=5,
            has_priority_support=True,
            has_api_access=True,
            has_custom_models=False,
        ),
    ]
    mock_result.scalars.return_value.all.return_value = tiers
    mock_db.execute.return_value = mock_result

    result = await list_tiers(db=mock_db)

    assert len(result) == 2
    assert result[0]["name"] == "free"
    assert result[1]["name"] == "pro"
    assert result[1]["price_monthly"] == 29.99


@pytest.mark.asyncio
async def test_initiate_upgrade():
    """Test initiating subscription upgrade."""
    from app.api.v1.subscription import initiate_upgrade

    mock_db = MagicMock()
    mock_db.execute = AsyncMock()

    mock_result = MagicMock()
    tier = MagicMock()
    tier.name = "pro"
    tier.price_monthly = 29.99
    tier.paypal_plan_id = "plan_mock_pro"
    mock_result.scalars.return_value.first.return_value = tier
    mock_db.execute.return_value = mock_result

    # Use MagicMock for user since subscription.py uses both attribute access AND .get()
    user = MagicMock()
    user.id = 1
    user.role = "free"
    user.email = "test@example.com"
    user.get = MagicMock(
        side_effect=lambda key, default=None: getattr(user, key, default)
    )

    # Mock paypal_client to avoid real PayPal connection
    mock_paypal = AsyncMock()
    mock_paypal.create_subscription = AsyncMock(
        return_value={
            "id": "sub_test_123",
            "links": [{"rel": "approve", "href": "https://paypal.com/approve"}],
        }
    )

    with patch("app.api.v1.subscription.get_current_user", return_value=user), patch(
        "app.api.v1.subscription.paypal_client", mock_paypal
    ):
        result = await initiate_upgrade(
            data=MagicMock(tier_name="pro", success_url=None, cancel_url=None),
            user=user,
            db=mock_db,
        )

    assert result["success"] == True
    assert "checkout_url" in result


@pytest.mark.asyncio
async def test_initiate_upgrade_invalid_tier():
    """Test upgrade with invalid tier name."""
    from fastapi import HTTPException

    from app.api.v1.subscription import initiate_upgrade

    mock_db = MagicMock()
    mock_db.execute = AsyncMock()

    mock_result = MagicMock()
    mock_result.scalars.return_value.first.return_value = None  # Tier not found
    mock_db.execute.return_value = mock_result

    user = SimpleNamespace(**{"id": 1})

    with patch("app.api.v1.subscription.get_current_user", return_value=user):
        with pytest.raises(HTTPException) as exc_info:
            await initiate_upgrade(
                data=MagicMock(tier_name="invalid", success_url=None, cancel_url=None),
                user=user,
                db=mock_db,
            )

        assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_get_my_subscription():
    """Test getting current user's subscription."""
    from app.api.v1.subscription import get_my_subscription

    # Use AsyncMock for db since get_my_subscription does await db.execute()
    user = MagicMock()
    user.id = 1
    user.role = "pro"
    user.get = MagicMock(
        side_effect=lambda key, default=None: getattr(user, key, default)
    )

    mock_db = AsyncMock()
    mock_db_result = MagicMock()
    mock_db_result.first.return_value = None  # No active subscription
    mock_db.execute.return_value = mock_db_result
    mock_db_result.scalars.return_value.first.return_value = SimpleNamespace(
        name="pro",
        missions_per_day=50,
        missions_per_month=1500,
    )

    with patch("app.api.v1.subscription.get_current_user", return_value=user):
        result = await get_my_subscription(user=user, db=mock_db)

    assert result["tier"]["name"] == "pro"
    assert result["tier"]["missions_per_day"] == 50
