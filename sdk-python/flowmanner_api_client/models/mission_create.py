from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..types import UNSET, Unset
from typing import cast






T = TypeVar("T", bound="MissionCreate")



@_attrs_define
class MissionCreate:
    """ 
        Attributes:
            title (str):
            description (str | Unset):  Default: ''.
            mission_type (None | str | Unset):
            priority (None | str | Unset):
     """

    title: str
    description: str | Unset = ''
    mission_type: None | str | Unset = UNSET
    priority: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        title = self.title

        description = self.description

        mission_type: None | str | Unset
        if isinstance(self.mission_type, Unset):
            mission_type = UNSET
        else:
            mission_type = self.mission_type

        priority: None | str | Unset
        if isinstance(self.priority, Unset):
            priority = UNSET
        else:
            priority = self.priority


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "title": title,
        })
        if description is not UNSET:
            field_dict["description"] = description
        if mission_type is not UNSET:
            field_dict["mission_type"] = mission_type
        if priority is not UNSET:
            field_dict["priority"] = priority

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        title = d.pop("title")

        description = d.pop("description", UNSET)

        def _parse_mission_type(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        mission_type = _parse_mission_type(d.pop("mission_type", UNSET))


        def _parse_priority(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        priority = _parse_priority(d.pop("priority", UNSET))


        mission_create = cls(
            title=title,
            description=description,
            mission_type=mission_type,
            priority=priority,
        )


        mission_create.additional_properties = d
        return mission_create

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
