from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from typing import cast






T = TypeVar("T", bound="ApiStats")



@_attrs_define
class ApiStats:
    """ 
        Attributes:
            requests_per_minute (float):
            avg_latency_ms (float):
            error_rate (float):
            slowest_endpoints (list[Any]):
     """

    requests_per_minute: float
    avg_latency_ms: float
    error_rate: float
    slowest_endpoints: list[Any]
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        requests_per_minute = self.requests_per_minute

        avg_latency_ms = self.avg_latency_ms

        error_rate = self.error_rate

        slowest_endpoints = self.slowest_endpoints




        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "requests_per_minute": requests_per_minute,
            "avg_latency_ms": avg_latency_ms,
            "error_rate": error_rate,
            "slowest_endpoints": slowest_endpoints,
        })

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        requests_per_minute = d.pop("requests_per_minute")

        avg_latency_ms = d.pop("avg_latency_ms")

        error_rate = d.pop("error_rate")

        slowest_endpoints = cast(list[Any], d.pop("slowest_endpoints"))


        api_stats = cls(
            requests_per_minute=requests_per_minute,
            avg_latency_ms=avg_latency_ms,
            error_rate=error_rate,
            slowest_endpoints=slowest_endpoints,
        )


        api_stats.additional_properties = d
        return api_stats

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
