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






T = TypeVar("T", bound="MissionExecutionStatus")



@_attrs_define
class MissionExecutionStatus:
    """ 
        Attributes:
            mission_id (None | Unset | UUID):
            status (None | str | Unset):
            current_task_index (int | None | Unset):
            total_tasks (int | Unset):  Default: 0.
            completed_tasks (int | Unset):  Default: 0.
            failed_tasks (int | Unset):  Default: 0.
            total_tokens_used (int | Unset):  Default: 0.
            started_at (datetime.datetime | None | Unset):
            estimated_completion (datetime.datetime | None | Unset):
     """

    mission_id: None | Unset | UUID = UNSET
    status: None | str | Unset = UNSET
    current_task_index: int | None | Unset = UNSET
    total_tasks: int | Unset = 0
    completed_tasks: int | Unset = 0
    failed_tasks: int | Unset = 0
    total_tokens_used: int | Unset = 0
    started_at: datetime.datetime | None | Unset = UNSET
    estimated_completion: datetime.datetime | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        mission_id: None | str | Unset
        if isinstance(self.mission_id, Unset):
            mission_id = UNSET
        elif isinstance(self.mission_id, UUID):
            mission_id = str(self.mission_id)
        else:
            mission_id = self.mission_id

        status: None | str | Unset
        if isinstance(self.status, Unset):
            status = UNSET
        else:
            status = self.status

        current_task_index: int | None | Unset
        if isinstance(self.current_task_index, Unset):
            current_task_index = UNSET
        else:
            current_task_index = self.current_task_index

        total_tasks = self.total_tasks

        completed_tasks = self.completed_tasks

        failed_tasks = self.failed_tasks

        total_tokens_used = self.total_tokens_used

        started_at: None | str | Unset
        if isinstance(self.started_at, Unset):
            started_at = UNSET
        elif isinstance(self.started_at, datetime.datetime):
            started_at = self.started_at.isoformat()
        else:
            started_at = self.started_at

        estimated_completion: None | str | Unset
        if isinstance(self.estimated_completion, Unset):
            estimated_completion = UNSET
        elif isinstance(self.estimated_completion, datetime.datetime):
            estimated_completion = self.estimated_completion.isoformat()
        else:
            estimated_completion = self.estimated_completion


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
        })
        if mission_id is not UNSET:
            field_dict["mission_id"] = mission_id
        if status is not UNSET:
            field_dict["status"] = status
        if current_task_index is not UNSET:
            field_dict["current_task_index"] = current_task_index
        if total_tasks is not UNSET:
            field_dict["total_tasks"] = total_tasks
        if completed_tasks is not UNSET:
            field_dict["completed_tasks"] = completed_tasks
        if failed_tasks is not UNSET:
            field_dict["failed_tasks"] = failed_tasks
        if total_tokens_used is not UNSET:
            field_dict["total_tokens_used"] = total_tokens_used
        if started_at is not UNSET:
            field_dict["started_at"] = started_at
        if estimated_completion is not UNSET:
            field_dict["estimated_completion"] = estimated_completion

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        def _parse_mission_id(data: object) -> None | Unset | UUID:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                mission_id_type_0 = UUID(data)



                return mission_id_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | Unset | UUID, data)

        mission_id = _parse_mission_id(d.pop("mission_id", UNSET))


        def _parse_status(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        status = _parse_status(d.pop("status", UNSET))


        def _parse_current_task_index(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        current_task_index = _parse_current_task_index(d.pop("current_task_index", UNSET))


        total_tasks = d.pop("total_tasks", UNSET)

        completed_tasks = d.pop("completed_tasks", UNSET)

        failed_tasks = d.pop("failed_tasks", UNSET)

        total_tokens_used = d.pop("total_tokens_used", UNSET)

        def _parse_started_at(data: object) -> datetime.datetime | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                started_at_type_0 = isoparse(data)



                return started_at_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(datetime.datetime | None | Unset, data)

        started_at = _parse_started_at(d.pop("started_at", UNSET))


        def _parse_estimated_completion(data: object) -> datetime.datetime | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                estimated_completion_type_0 = isoparse(data)



                return estimated_completion_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(datetime.datetime | None | Unset, data)

        estimated_completion = _parse_estimated_completion(d.pop("estimated_completion", UNSET))


        mission_execution_status = cls(
            mission_id=mission_id,
            status=status,
            current_task_index=current_task_index,
            total_tasks=total_tasks,
            completed_tasks=completed_tasks,
            failed_tasks=failed_tasks,
            total_tokens_used=total_tokens_used,
            started_at=started_at,
            estimated_completion=estimated_completion,
        )


        mission_execution_status.additional_properties = d
        return mission_execution_status

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
