from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset







T = TypeVar("T", bound="WebhookFireResponse")



@_attrs_define
class WebhookFireResponse:
    """ 
        Attributes:
            trigger_id (str):
            mission_id (str):
            log_id (str):
            status (str):
     """

    trigger_id: str
    mission_id: str
    log_id: str
    status: str
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        trigger_id = self.trigger_id

        mission_id = self.mission_id

        log_id = self.log_id

        status = self.status


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "trigger_id": trigger_id,
            "mission_id": mission_id,
            "log_id": log_id,
            "status": status,
        })

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        trigger_id = d.pop("trigger_id")

        mission_id = d.pop("mission_id")

        log_id = d.pop("log_id")

        status = d.pop("status")

        webhook_fire_response = cls(
            trigger_id=trigger_id,
            mission_id=mission_id,
            log_id=log_id,
            status=status,
        )


        webhook_fire_response.additional_properties = d
        return webhook_fire_response

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
