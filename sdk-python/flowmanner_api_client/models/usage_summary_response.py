from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.usage_by_model import UsageByModel


T = TypeVar("T", bound="UsageSummaryResponse")


@_attrs_define
class UsageSummaryResponse:
    """
    Attributes:
        total_tokens (int):
        total_cost (float):
        period (str):
        breakdown (list[UsageByModel]):
    """

    total_tokens: int
    total_cost: float
    period: str
    breakdown: list[UsageByModel]
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        total_tokens = self.total_tokens

        total_cost = self.total_cost

        period = self.period

        breakdown = []
        for breakdown_item_data in self.breakdown:
            breakdown_item = breakdown_item_data.to_dict()
            breakdown.append(breakdown_item)

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "total_tokens": total_tokens,
                "total_cost": total_cost,
                "period": period,
                "breakdown": breakdown,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.usage_by_model import UsageByModel

        d = dict(src_dict)
        total_tokens = d.pop("total_tokens")

        total_cost = d.pop("total_cost")

        period = d.pop("period")

        breakdown = []
        _breakdown = d.pop("breakdown")
        for breakdown_item_data in _breakdown:
            breakdown_item = UsageByModel.from_dict(breakdown_item_data)

            breakdown.append(breakdown_item)

        usage_summary_response = cls(
            total_tokens=total_tokens,
            total_cost=total_cost,
            period=period,
            breakdown=breakdown,
        )

        usage_summary_response.additional_properties = d
        return usage_summary_response

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
