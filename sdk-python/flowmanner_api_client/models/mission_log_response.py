from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..types import UNSET, Unset
from dateutil.parser import isoparse
from typing import cast
from uuid import UUID
import datetime

if TYPE_CHECKING:
  from ..models.mission_log_response_data_type_0 import MissionLogResponseDataType0





T = TypeVar("T", bound="MissionLogResponse")



@_attrs_define
class MissionLogResponse:
    """ 
        Attributes:
            id (UUID):
            mission_id (UUID):
            message (str):
            task_id (None | Unset | UUID):
            level (None | str | Unset):
            data (MissionLogResponseDataType0 | None | Unset):
            timestamp (datetime.datetime | None | Unset):
     """

    id: UUID
    mission_id: UUID
    message: str
    task_id: None | Unset | UUID = UNSET
    level: None | str | Unset = UNSET
    data: MissionLogResponseDataType0 | None | Unset = UNSET
    timestamp: datetime.datetime | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        from ..models.mission_log_response_data_type_0 import MissionLogResponseDataType0
        id = str(self.id)

        mission_id = str(self.mission_id)

        message = self.message

        task_id: None | str | Unset
        if isinstance(self.task_id, Unset):
            task_id = UNSET
        elif isinstance(self.task_id, UUID):
            task_id = str(self.task_id)
        else:
            task_id = self.task_id

        level: None | str | Unset
        if isinstance(self.level, Unset):
            level = UNSET
        else:
            level = self.level

        data: dict[str, Any] | None | Unset
        if isinstance(self.data, Unset):
            data = UNSET
        elif isinstance(self.data, MissionLogResponseDataType0):
            data = self.data.to_dict()
        else:
            data = self.data

        timestamp: None | str | Unset
        if isinstance(self.timestamp, Unset):
            timestamp = UNSET
        elif isinstance(self.timestamp, datetime.datetime):
            timestamp = self.timestamp.isoformat()
        else:
            timestamp = self.timestamp


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "id": id,
            "mission_id": mission_id,
            "message": message,
        })
        if task_id is not UNSET:
            field_dict["task_id"] = task_id
        if level is not UNSET:
            field_dict["level"] = level
        if data is not UNSET:
            field_dict["data"] = data
        if timestamp is not UNSET:
            field_dict["timestamp"] = timestamp

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.mission_log_response_data_type_0 import MissionLogResponseDataType0
        d = dict(src_dict)
        id = UUID(d.pop("id"))




        mission_id = UUID(d.pop("mission_id"))




        message = d.pop("message")

        def _parse_task_id(data: object) -> None | Unset | UUID:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                task_id_type_0 = UUID(data)



                return task_id_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | Unset | UUID, data)

        task_id = _parse_task_id(d.pop("task_id", UNSET))


        def _parse_level(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        level = _parse_level(d.pop("level", UNSET))


        def _parse_data(data: object) -> MissionLogResponseDataType0 | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                data_type_0 = MissionLogResponseDataType0.from_dict(data)



                return data_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(MissionLogResponseDataType0 | None | Unset, data)

        data = _parse_data(d.pop("data", UNSET))


        def _parse_timestamp(data: object) -> datetime.datetime | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                timestamp_type_0 = isoparse(data)



                return timestamp_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(datetime.datetime | None | Unset, data)

        timestamp = _parse_timestamp(d.pop("timestamp", UNSET))


        mission_log_response = cls(
            id=id,
            mission_id=mission_id,
            message=message,
            task_id=task_id,
            level=level,
            data=data,
            timestamp=timestamp,
        )


        mission_log_response.additional_properties = d
        return mission_log_response

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
