from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.top_failed_mission import TopFailedMission


T = TypeVar("T", bound="DashboardAnalyticsResponse")


@_attrs_define
class DashboardAnalyticsResponse:
    """
    Attributes:
        seven_day_success_rate (float):
        avg_runtime_seconds (float):
        current_queue_depth (int):
        top_failed_missions (list[TopFailedMission]):
    """

    seven_day_success_rate: float
    avg_runtime_seconds: float
    current_queue_depth: int
    top_failed_missions: list[TopFailedMission]
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        seven_day_success_rate = self.seven_day_success_rate

        avg_runtime_seconds = self.avg_runtime_seconds

        current_queue_depth = self.current_queue_depth

        top_failed_missions = []
        for top_failed_missions_item_data in self.top_failed_missions:
            top_failed_missions_item = top_failed_missions_item_data.to_dict()
            top_failed_missions.append(top_failed_missions_item)

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "sevenDaySuccessRate": seven_day_success_rate,
                "avgRuntimeSeconds": avg_runtime_seconds,
                "currentQueueDepth": current_queue_depth,
                "topFailedMissions": top_failed_missions,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.top_failed_mission import TopFailedMission

        d = dict(src_dict)
        seven_day_success_rate = d.pop("sevenDaySuccessRate")

        avg_runtime_seconds = d.pop("avgRuntimeSeconds")

        current_queue_depth = d.pop("currentQueueDepth")

        top_failed_missions = []
        _top_failed_missions = d.pop("topFailedMissions")
        for top_failed_missions_item_data in _top_failed_missions:
            top_failed_missions_item = TopFailedMission.from_dict(top_failed_missions_item_data)

            top_failed_missions.append(top_failed_missions_item)

        dashboard_analytics_response = cls(
            seven_day_success_rate=seven_day_success_rate,
            avg_runtime_seconds=avg_runtime_seconds,
            current_queue_depth=current_queue_depth,
            top_failed_missions=top_failed_missions,
        )

        dashboard_analytics_response.additional_properties = d
        return dashboard_analytics_response

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
