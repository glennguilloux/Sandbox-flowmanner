from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

T = TypeVar("T", bound="TierResponse")


@_attrs_define
class TierResponse:
    """
    Attributes:
        id (int):
        name (str):
        display_name (str):
        description (None | str):
        price_monthly (float | None):
        missions_per_day (int):
        missions_per_month (int):
        max_concurrent_missions (int):
        has_priority_support (bool):
        has_api_access (bool):
        has_custom_models (bool):
    """

    id: int
    name: str
    display_name: str
    description: None | str
    price_monthly: float | None
    missions_per_day: int
    missions_per_month: int
    max_concurrent_missions: int
    has_priority_support: bool
    has_api_access: bool
    has_custom_models: bool
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        id = self.id

        name = self.name

        display_name = self.display_name

        description: None | str
        description = self.description

        price_monthly: float | None
        price_monthly = self.price_monthly

        missions_per_day = self.missions_per_day

        missions_per_month = self.missions_per_month

        max_concurrent_missions = self.max_concurrent_missions

        has_priority_support = self.has_priority_support

        has_api_access = self.has_api_access

        has_custom_models = self.has_custom_models

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "id": id,
                "name": name,
                "display_name": display_name,
                "description": description,
                "price_monthly": price_monthly,
                "missions_per_day": missions_per_day,
                "missions_per_month": missions_per_month,
                "max_concurrent_missions": max_concurrent_missions,
                "has_priority_support": has_priority_support,
                "has_api_access": has_api_access,
                "has_custom_models": has_custom_models,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        id = d.pop("id")

        name = d.pop("name")

        display_name = d.pop("display_name")

        def _parse_description(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        description = _parse_description(d.pop("description"))

        def _parse_price_monthly(data: object) -> float | None:
            if data is None:
                return data
            return cast(float | None, data)

        price_monthly = _parse_price_monthly(d.pop("price_monthly"))

        missions_per_day = d.pop("missions_per_day")

        missions_per_month = d.pop("missions_per_month")

        max_concurrent_missions = d.pop("max_concurrent_missions")

        has_priority_support = d.pop("has_priority_support")

        has_api_access = d.pop("has_api_access")

        has_custom_models = d.pop("has_custom_models")

        tier_response = cls(
            id=id,
            name=name,
            display_name=display_name,
            description=description,
            price_monthly=price_monthly,
            missions_per_day=missions_per_day,
            missions_per_month=missions_per_month,
            max_concurrent_missions=max_concurrent_missions,
            has_priority_support=has_priority_support,
            has_api_access=has_api_access,
            has_custom_models=has_custom_models,
        )

        tier_response.additional_properties = d
        return tier_response

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
