from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

T = TypeVar("T", bound="UsageBreakdown")


@_attrs_define
class UsageBreakdown:
    """
    Attributes:
        model (str):
        provider (str):
        requests (int):
        tokens (int):
        cost (float):
    """

    model: str
    provider: str
    requests: int
    tokens: int
    cost: float
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        model = self.model

        provider = self.provider

        requests = self.requests

        tokens = self.tokens

        cost = self.cost

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "model": model,
                "provider": provider,
                "requests": requests,
                "tokens": tokens,
                "cost": cost,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        model = d.pop("model")

        provider = d.pop("provider")

        requests = d.pop("requests")

        tokens = d.pop("tokens")

        cost = d.pop("cost")

        usage_breakdown = cls(
            model=model,
            provider=provider,
            requests=requests,
            tokens=tokens,
            cost=cost,
        )

        usage_breakdown.additional_properties = d
        return usage_breakdown

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
