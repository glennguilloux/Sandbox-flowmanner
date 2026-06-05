from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="ProviderHealth")


@_attrs_define
class ProviderHealth:
    """
    Attributes:
        name (str):
        healthy (bool | Unset):  Default: True.
        error_count (int | Unset):  Default: 0.
    """

    name: str
    healthy: bool | Unset = True
    error_count: int | Unset = 0
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        name = self.name

        healthy = self.healthy

        error_count = self.error_count

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "name": name,
            }
        )
        if healthy is not UNSET:
            field_dict["healthy"] = healthy
        if error_count is not UNSET:
            field_dict["error_count"] = error_count

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        name = d.pop("name")

        healthy = d.pop("healthy", UNSET)

        error_count = d.pop("error_count", UNSET)

        provider_health = cls(
            name=name,
            healthy=healthy,
            error_count=error_count,
        )

        provider_health.additional_properties = d
        return provider_health

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
