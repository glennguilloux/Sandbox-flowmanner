from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..types import UNSET, Unset
from typing import cast






T = TypeVar("T", bound="MaintenanceStatus")



@_attrs_define
class MaintenanceStatus:
    """ 
        Attributes:
            active (bool):
            message (None | str | Unset):
            estimated_duration (None | str | Unset):
            activated_at (None | str | Unset):
     """

    active: bool
    message: None | str | Unset = UNSET
    estimated_duration: None | str | Unset = UNSET
    activated_at: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        active = self.active

        message: None | str | Unset
        if isinstance(self.message, Unset):
            message = UNSET
        else:
            message = self.message

        estimated_duration: None | str | Unset
        if isinstance(self.estimated_duration, Unset):
            estimated_duration = UNSET
        else:
            estimated_duration = self.estimated_duration

        activated_at: None | str | Unset
        if isinstance(self.activated_at, Unset):
            activated_at = UNSET
        else:
            activated_at = self.activated_at


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "active": active,
        })
        if message is not UNSET:
            field_dict["message"] = message
        if estimated_duration is not UNSET:
            field_dict["estimated_duration"] = estimated_duration
        if activated_at is not UNSET:
            field_dict["activated_at"] = activated_at

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        active = d.pop("active")

        def _parse_message(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        message = _parse_message(d.pop("message", UNSET))


        def _parse_estimated_duration(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        estimated_duration = _parse_estimated_duration(d.pop("estimated_duration", UNSET))


        def _parse_activated_at(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        activated_at = _parse_activated_at(d.pop("activated_at", UNSET))


        maintenance_status = cls(
            active=active,
            message=message,
            estimated_duration=estimated_duration,
            activated_at=activated_at,
        )


        maintenance_status.additional_properties = d
        return maintenance_status

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
