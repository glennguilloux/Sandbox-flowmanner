from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.revenue_response_revenue_trend_item import (
        RevenueResponseRevenueTrendItem,
    )


T = TypeVar("T", bound="RevenueResponse")


@_attrs_define
class RevenueResponse:
    """
    Attributes:
        current_month_revenue (float):
        total_mission_volume (int):
        total_referrals (int):
        pending_payout (float):
        revenue_trend (list[RevenueResponseRevenueTrendItem]):
        currency (str | Unset):  Default: 'USD'.
    """

    current_month_revenue: float
    total_mission_volume: int
    total_referrals: int
    pending_payout: float
    revenue_trend: list[RevenueResponseRevenueTrendItem]
    currency: str | Unset = "USD"
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        current_month_revenue = self.current_month_revenue

        total_mission_volume = self.total_mission_volume

        total_referrals = self.total_referrals

        pending_payout = self.pending_payout

        revenue_trend = []
        for revenue_trend_item_data in self.revenue_trend:
            revenue_trend_item = revenue_trend_item_data.to_dict()
            revenue_trend.append(revenue_trend_item)

        currency = self.currency

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "current_month_revenue": current_month_revenue,
                "total_mission_volume": total_mission_volume,
                "total_referrals": total_referrals,
                "pending_payout": pending_payout,
                "revenue_trend": revenue_trend,
            }
        )
        if currency is not UNSET:
            field_dict["currency"] = currency

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.revenue_response_revenue_trend_item import (
            RevenueResponseRevenueTrendItem,
        )

        d = dict(src_dict)
        current_month_revenue = d.pop("current_month_revenue")

        total_mission_volume = d.pop("total_mission_volume")

        total_referrals = d.pop("total_referrals")

        pending_payout = d.pop("pending_payout")

        revenue_trend = []
        _revenue_trend = d.pop("revenue_trend")
        for revenue_trend_item_data in _revenue_trend:
            revenue_trend_item = RevenueResponseRevenueTrendItem.from_dict(revenue_trend_item_data)

            revenue_trend.append(revenue_trend_item)

        currency = d.pop("currency", UNSET)

        revenue_response = cls(
            current_month_revenue=current_month_revenue,
            total_mission_volume=total_mission_volume,
            total_referrals=total_referrals,
            pending_payout=pending_payout,
            revenue_trend=revenue_trend,
            currency=currency,
        )

        revenue_response.additional_properties = d
        return revenue_response

    @property
    def additional_keys(self) -> list[str]:
        return list(self.additional_properties.keys())

    def __getitem__(self, key: str) -> Any:
        return self.additional_properties[key]

    def __setitem__(self, key: str, value: Any) -> None:
        self.additional_properties[key] = value

    def __delitem__(self, key: str) -> None:
        del self.additional_properties[key]

    def __contains__(self, key: str) -> bool:
        return key in self.additional_properties
