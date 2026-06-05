from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="MissionAnalyticsResponse")


@_attrs_define
class MissionAnalyticsResponse:
    """
    Attributes:
        total_missions (int | Unset):  Default: 0.
        success_rate (float | Unset):  Default: 0.0.
        avg_completion_time (float | None | Unset):
        total_tokens_used (int | Unset):  Default: 0.
    """

    total_missions: int | Unset = 0
    success_rate: float | Unset = 0.0
    avg_completion_time: float | None | Unset = UNSET
    total_tokens_used: int | Unset = 0
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        total_missions = self.total_missions

        success_rate = self.success_rate

        avg_completion_time: float | None | Unset
        if isinstance(self.avg_completion_time, Unset):
            avg_completion_time = UNSET
        else:
            avg_completion_time = self.avg_completion_time

        total_tokens_used = self.total_tokens_used

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if total_missions is not UNSET:
            field_dict["total_missions"] = total_missions
        if success_rate is not UNSET:
            field_dict["success_rate"] = success_rate
        if avg_completion_time is not UNSET:
            field_dict["avg_completion_time"] = avg_completion_time
        if total_tokens_used is not UNSET:
            field_dict["total_tokens_used"] = total_tokens_used

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        total_missions = d.pop("total_missions", UNSET)

        success_rate = d.pop("success_rate", UNSET)

        def _parse_avg_completion_time(data: object) -> float | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(float | None | Unset, data)

        avg_completion_time = _parse_avg_completion_time(
            d.pop("avg_completion_time", UNSET)
        )

        total_tokens_used = d.pop("total_tokens_used", UNSET)

        mission_analytics_response = cls(
            total_missions=total_missions,
            success_rate=success_rate,
            avg_completion_time=avg_completion_time,
            total_tokens_used=total_tokens_used,
        )

        mission_analytics_response.additional_properties = d
        return mission_analytics_response

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
