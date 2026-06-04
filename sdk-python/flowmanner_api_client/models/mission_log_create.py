from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..types import UNSET, Unset
from typing import cast

if TYPE_CHECKING:
  from ..models.mission_log_create_data_type_0 import MissionLogCreateDataType0





T = TypeVar("T", bound="MissionLogCreate")



@_attrs_define
class MissionLogCreate:
    """ 
        Attributes:
            message (str):
            level (str | Unset):  Default: 'info'.
            data (MissionLogCreateDataType0 | None | Unset):
     """

    message: str
    level: str | Unset = 'info'
    data: MissionLogCreateDataType0 | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        from ..models.mission_log_create_data_type_0 import MissionLogCreateDataType0
        message = self.message

        level = self.level

        data: dict[str, Any] | None | Unset
        if isinstance(self.data, Unset):
            data = UNSET
        elif isinstance(self.data, MissionLogCreateDataType0):
            data = self.data.to_dict()
        else:
            data = self.data


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "message": message,
        })
        if level is not UNSET:
            field_dict["level"] = level
        if data is not UNSET:
            field_dict["data"] = data

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.mission_log_create_data_type_0 import MissionLogCreateDataType0
        d = dict(src_dict)
        message = d.pop("message")

        level = d.pop("level", UNSET)

        def _parse_data(data: object) -> MissionLogCreateDataType0 | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                data_type_0 = MissionLogCreateDataType0.from_dict(data)



                return data_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(MissionLogCreateDataType0 | None | Unset, data)

        data = _parse_data(d.pop("data", UNSET))


        mission_log_create = cls(
            message=message,
            level=level,
            data=data,
        )


        mission_log_create.additional_properties = d
        return mission_log_create

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
