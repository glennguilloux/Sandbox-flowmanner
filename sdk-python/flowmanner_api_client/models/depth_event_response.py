from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.depth_event_response_payload import DepthEventResponsePayload


T = TypeVar("T", bound="DepthEventResponse")


@_attrs_define
class DepthEventResponse:
    """Response body for a depth audit event.

    Attributes:
        id (str):
        sequence (int):
        type_ (str):
        payload (DepthEventResponsePayload):
        actor (str):
        timestamp (str):
        mission_id (None | str):
        task_id (None | str):
    """

    id: str
    sequence: int
    type_: str
    payload: DepthEventResponsePayload
    actor: str
    timestamp: str
    mission_id: None | str
    task_id: None | str
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        id = self.id

        sequence = self.sequence

        type_ = self.type_

        payload = self.payload.to_dict()

        actor = self.actor

        timestamp = self.timestamp

        mission_id: None | str
        mission_id = self.mission_id

        task_id: None | str
        task_id = self.task_id

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "id": id,
                "sequence": sequence,
                "type": type_,
                "payload": payload,
                "actor": actor,
                "timestamp": timestamp,
                "mission_id": mission_id,
                "task_id": task_id,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.depth_event_response_payload import DepthEventResponsePayload

        d = dict(src_dict)
        id = d.pop("id")

        sequence = d.pop("sequence")

        type_ = d.pop("type")

        payload = DepthEventResponsePayload.from_dict(d.pop("payload"))

        actor = d.pop("actor")

        timestamp = d.pop("timestamp")

        def _parse_mission_id(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        mission_id = _parse_mission_id(d.pop("mission_id"))

        def _parse_task_id(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        task_id = _parse_task_id(d.pop("task_id"))

        depth_event_response = cls(
            id=id,
            sequence=sequence,
            type_=type_,
            payload=payload,
            actor=actor,
            timestamp=timestamp,
            mission_id=mission_id,
            task_id=task_id,
        )

        depth_event_response.additional_properties = d
        return depth_event_response

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
