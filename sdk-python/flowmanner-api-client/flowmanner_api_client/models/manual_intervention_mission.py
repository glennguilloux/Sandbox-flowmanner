from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

T = TypeVar("T", bound="ManualInterventionMission")


@_attrs_define
class ManualInterventionMission:
    """
    Attributes:
        mission_id (str):
        error_code (str):
        last_update_timestamp (str):
    """

    mission_id: str
    error_code: str
    last_update_timestamp: str
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        mission_id = self.mission_id

        error_code = self.error_code

        last_update_timestamp = self.last_update_timestamp

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "missionId": mission_id,
                "errorCode": error_code,
                "lastUpdateTimestamp": last_update_timestamp,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        mission_id = d.pop("missionId")

        error_code = d.pop("errorCode")

        last_update_timestamp = d.pop("lastUpdateTimestamp")

        manual_intervention_mission = cls(
            mission_id=mission_id,
            error_code=error_code,
            last_update_timestamp=last_update_timestamp,
        )

        manual_intervention_mission.additional_properties = d
        return manual_intervention_mission

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
