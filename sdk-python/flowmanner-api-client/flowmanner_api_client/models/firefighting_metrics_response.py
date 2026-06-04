from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.error_code_count import ErrorCodeCount
    from ..models.manual_intervention_mission import ManualInterventionMission


T = TypeVar("T", bound="FirefightingMetricsResponse")


@_attrs_define
class FirefightingMetricsResponse:
    """
    Attributes:
        failed_mission_count (int):
        avg_retry_count (float):
        top_error_codes (list[ErrorCodeCount]):
        manual_intervention_missions (list[ManualInterventionMission]):
    """

    failed_mission_count: int
    avg_retry_count: float
    top_error_codes: list[ErrorCodeCount]
    manual_intervention_missions: list[ManualInterventionMission]
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        failed_mission_count = self.failed_mission_count

        avg_retry_count = self.avg_retry_count

        top_error_codes = []
        for top_error_codes_item_data in self.top_error_codes:
            top_error_codes_item = top_error_codes_item_data.to_dict()
            top_error_codes.append(top_error_codes_item)

        manual_intervention_missions = []
        for manual_intervention_missions_item_data in self.manual_intervention_missions:
            manual_intervention_missions_item = manual_intervention_missions_item_data.to_dict()
            manual_intervention_missions.append(manual_intervention_missions_item)

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "failedMissionCount": failed_mission_count,
                "avgRetryCount": avg_retry_count,
                "topErrorCodes": top_error_codes,
                "manualInterventionMissions": manual_intervention_missions,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.error_code_count import ErrorCodeCount
        from ..models.manual_intervention_mission import ManualInterventionMission

        d = dict(src_dict)
        failed_mission_count = d.pop("failedMissionCount")

        avg_retry_count = d.pop("avgRetryCount")

        top_error_codes = []
        _top_error_codes = d.pop("topErrorCodes")
        for top_error_codes_item_data in _top_error_codes:
            top_error_codes_item = ErrorCodeCount.from_dict(top_error_codes_item_data)

            top_error_codes.append(top_error_codes_item)

        manual_intervention_missions = []
        _manual_intervention_missions = d.pop("manualInterventionMissions")
        for manual_intervention_missions_item_data in _manual_intervention_missions:
            manual_intervention_missions_item = ManualInterventionMission.from_dict(
                manual_intervention_missions_item_data
            )

            manual_intervention_missions.append(manual_intervention_missions_item)

        firefighting_metrics_response = cls(
            failed_mission_count=failed_mission_count,
            avg_retry_count=avg_retry_count,
            top_error_codes=top_error_codes,
            manual_intervention_missions=manual_intervention_missions,
        )

        firefighting_metrics_response.additional_properties = d
        return firefighting_metrics_response

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
