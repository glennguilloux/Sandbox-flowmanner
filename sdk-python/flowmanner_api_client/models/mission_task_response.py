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
  from ..models.mission_task_response_dependencies_type_1 import MissionTaskResponseDependenciesType1
  from ..models.mission_task_response_input_data_type_0 import MissionTaskResponseInputDataType0
  from ..models.mission_task_response_output_data_type_0 import MissionTaskResponseOutputDataType0





T = TypeVar("T", bound="MissionTaskResponse")



@_attrs_define
class MissionTaskResponse:
    """ 
        Attributes:
            id (UUID):
            mission_id (UUID):
            title (str):
            task_type (str):
            description (None | str | Unset):
            order_index (int | None | Unset):
            assigned_agent_id (None | str | Unset):
            assigned_model (None | str | Unset):
            status (None | str | Unset):
            input_data (MissionTaskResponseInputDataType0 | None | Unset):
            output_data (MissionTaskResponseOutputDataType0 | None | Unset):
            dependencies (list[Any] | MissionTaskResponseDependenciesType1 | None | Unset):
            retry_count (int | None | Unset):
            max_retries (int | None | Unset):
            timeout_seconds (int | None | Unset):
            tokens_used (int | None | Unset):
            cost (float | None | Unset):
            error_message (None | str | Unset):
            started_at (datetime.datetime | None | Unset):
            completed_at (datetime.datetime | None | Unset):
            created_at (datetime.datetime | None | Unset):
     """

    id: UUID
    mission_id: UUID
    title: str
    task_type: str
    description: None | str | Unset = UNSET
    order_index: int | None | Unset = UNSET
    assigned_agent_id: None | str | Unset = UNSET
    assigned_model: None | str | Unset = UNSET
    status: None | str | Unset = UNSET
    input_data: MissionTaskResponseInputDataType0 | None | Unset = UNSET
    output_data: MissionTaskResponseOutputDataType0 | None | Unset = UNSET
    dependencies: list[Any] | MissionTaskResponseDependenciesType1 | None | Unset = UNSET
    retry_count: int | None | Unset = UNSET
    max_retries: int | None | Unset = UNSET
    timeout_seconds: int | None | Unset = UNSET
    tokens_used: int | None | Unset = UNSET
    cost: float | None | Unset = UNSET
    error_message: None | str | Unset = UNSET
    started_at: datetime.datetime | None | Unset = UNSET
    completed_at: datetime.datetime | None | Unset = UNSET
    created_at: datetime.datetime | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        from ..models.mission_task_response_dependencies_type_1 import MissionTaskResponseDependenciesType1
        from ..models.mission_task_response_input_data_type_0 import MissionTaskResponseInputDataType0
        from ..models.mission_task_response_output_data_type_0 import MissionTaskResponseOutputDataType0
        id = str(self.id)

        mission_id = str(self.mission_id)

        title = self.title

        task_type = self.task_type

        description: None | str | Unset
        if isinstance(self.description, Unset):
            description = UNSET
        else:
            description = self.description

        order_index: int | None | Unset
        if isinstance(self.order_index, Unset):
            order_index = UNSET
        else:
            order_index = self.order_index

        assigned_agent_id: None | str | Unset
        if isinstance(self.assigned_agent_id, Unset):
            assigned_agent_id = UNSET
        else:
            assigned_agent_id = self.assigned_agent_id

        assigned_model: None | str | Unset
        if isinstance(self.assigned_model, Unset):
            assigned_model = UNSET
        else:
            assigned_model = self.assigned_model

        status: None | str | Unset
        if isinstance(self.status, Unset):
            status = UNSET
        else:
            status = self.status

        input_data: dict[str, Any] | None | Unset
        if isinstance(self.input_data, Unset):
            input_data = UNSET
        elif isinstance(self.input_data, MissionTaskResponseInputDataType0):
            input_data = self.input_data.to_dict()
        else:
            input_data = self.input_data

        output_data: dict[str, Any] | None | Unset
        if isinstance(self.output_data, Unset):
            output_data = UNSET
        elif isinstance(self.output_data, MissionTaskResponseOutputDataType0):
            output_data = self.output_data.to_dict()
        else:
            output_data = self.output_data

        dependencies: dict[str, Any] | list[Any] | None | Unset
        if isinstance(self.dependencies, Unset):
            dependencies = UNSET
        elif isinstance(self.dependencies, list):
            dependencies = self.dependencies


        elif isinstance(self.dependencies, MissionTaskResponseDependenciesType1):
            dependencies = self.dependencies.to_dict()
        else:
            dependencies = self.dependencies

        retry_count: int | None | Unset
        if isinstance(self.retry_count, Unset):
            retry_count = UNSET
        else:
            retry_count = self.retry_count

        max_retries: int | None | Unset
        if isinstance(self.max_retries, Unset):
            max_retries = UNSET
        else:
            max_retries = self.max_retries

        timeout_seconds: int | None | Unset
        if isinstance(self.timeout_seconds, Unset):
            timeout_seconds = UNSET
        else:
            timeout_seconds = self.timeout_seconds

        tokens_used: int | None | Unset
        if isinstance(self.tokens_used, Unset):
            tokens_used = UNSET
        else:
            tokens_used = self.tokens_used

        cost: float | None | Unset
        if isinstance(self.cost, Unset):
            cost = UNSET
        else:
            cost = self.cost

        error_message: None | str | Unset
        if isinstance(self.error_message, Unset):
            error_message = UNSET
        else:
            error_message = self.error_message

        started_at: None | str | Unset
        if isinstance(self.started_at, Unset):
            started_at = UNSET
        elif isinstance(self.started_at, datetime.datetime):
            started_at = self.started_at.isoformat()
        else:
            started_at = self.started_at

        completed_at: None | str | Unset
        if isinstance(self.completed_at, Unset):
            completed_at = UNSET
        elif isinstance(self.completed_at, datetime.datetime):
            completed_at = self.completed_at.isoformat()
        else:
            completed_at = self.completed_at

        created_at: None | str | Unset
        if isinstance(self.created_at, Unset):
            created_at = UNSET
        elif isinstance(self.created_at, datetime.datetime):
            created_at = self.created_at.isoformat()
        else:
            created_at = self.created_at


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "id": id,
            "mission_id": mission_id,
            "title": title,
            "task_type": task_type,
        })
        if description is not UNSET:
            field_dict["description"] = description
        if order_index is not UNSET:
            field_dict["order_index"] = order_index
        if assigned_agent_id is not UNSET:
            field_dict["assigned_agent_id"] = assigned_agent_id
        if assigned_model is not UNSET:
            field_dict["assigned_model"] = assigned_model
        if status is not UNSET:
            field_dict["status"] = status
        if input_data is not UNSET:
            field_dict["input_data"] = input_data
        if output_data is not UNSET:
            field_dict["output_data"] = output_data
        if dependencies is not UNSET:
            field_dict["dependencies"] = dependencies
        if retry_count is not UNSET:
            field_dict["retry_count"] = retry_count
        if max_retries is not UNSET:
            field_dict["max_retries"] = max_retries
        if timeout_seconds is not UNSET:
            field_dict["timeout_seconds"] = timeout_seconds
        if tokens_used is not UNSET:
            field_dict["tokens_used"] = tokens_used
        if cost is not UNSET:
            field_dict["cost"] = cost
        if error_message is not UNSET:
            field_dict["error_message"] = error_message
        if started_at is not UNSET:
            field_dict["started_at"] = started_at
        if completed_at is not UNSET:
            field_dict["completed_at"] = completed_at
        if created_at is not UNSET:
            field_dict["created_at"] = created_at

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.mission_task_response_dependencies_type_1 import MissionTaskResponseDependenciesType1
        from ..models.mission_task_response_input_data_type_0 import MissionTaskResponseInputDataType0
        from ..models.mission_task_response_output_data_type_0 import MissionTaskResponseOutputDataType0
        d = dict(src_dict)
        id = UUID(d.pop("id"))




        mission_id = UUID(d.pop("mission_id"))




        title = d.pop("title")

        task_type = d.pop("task_type")

        def _parse_description(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        description = _parse_description(d.pop("description", UNSET))


        def _parse_order_index(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        order_index = _parse_order_index(d.pop("order_index", UNSET))


        def _parse_assigned_agent_id(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        assigned_agent_id = _parse_assigned_agent_id(d.pop("assigned_agent_id", UNSET))


        def _parse_assigned_model(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        assigned_model = _parse_assigned_model(d.pop("assigned_model", UNSET))


        def _parse_status(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        status = _parse_status(d.pop("status", UNSET))


        def _parse_input_data(data: object) -> MissionTaskResponseInputDataType0 | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                input_data_type_0 = MissionTaskResponseInputDataType0.from_dict(data)



                return input_data_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(MissionTaskResponseInputDataType0 | None | Unset, data)

        input_data = _parse_input_data(d.pop("input_data", UNSET))


        def _parse_output_data(data: object) -> MissionTaskResponseOutputDataType0 | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                output_data_type_0 = MissionTaskResponseOutputDataType0.from_dict(data)



                return output_data_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(MissionTaskResponseOutputDataType0 | None | Unset, data)

        output_data = _parse_output_data(d.pop("output_data", UNSET))


        def _parse_dependencies(data: object) -> list[Any] | MissionTaskResponseDependenciesType1 | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, list):
                    raise TypeError()
                dependencies_type_0 = cast(list[Any], data)

                return dependencies_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                dependencies_type_1 = MissionTaskResponseDependenciesType1.from_dict(data)



                return dependencies_type_1
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(list[Any] | MissionTaskResponseDependenciesType1 | None | Unset, data)

        dependencies = _parse_dependencies(d.pop("dependencies", UNSET))


        def _parse_retry_count(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        retry_count = _parse_retry_count(d.pop("retry_count", UNSET))


        def _parse_max_retries(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        max_retries = _parse_max_retries(d.pop("max_retries", UNSET))


        def _parse_timeout_seconds(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        timeout_seconds = _parse_timeout_seconds(d.pop("timeout_seconds", UNSET))


        def _parse_tokens_used(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        tokens_used = _parse_tokens_used(d.pop("tokens_used", UNSET))


        def _parse_cost(data: object) -> float | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(float | None | Unset, data)

        cost = _parse_cost(d.pop("cost", UNSET))


        def _parse_error_message(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        error_message = _parse_error_message(d.pop("error_message", UNSET))


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


        def _parse_completed_at(data: object) -> datetime.datetime | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                completed_at_type_0 = isoparse(data)



                return completed_at_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(datetime.datetime | None | Unset, data)

        completed_at = _parse_completed_at(d.pop("completed_at", UNSET))


        def _parse_created_at(data: object) -> datetime.datetime | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                created_at_type_0 = isoparse(data)



                return created_at_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(datetime.datetime | None | Unset, data)

        created_at = _parse_created_at(d.pop("created_at", UNSET))


        mission_task_response = cls(
            id=id,
            mission_id=mission_id,
            title=title,
            task_type=task_type,
            description=description,
            order_index=order_index,
            assigned_agent_id=assigned_agent_id,
            assigned_model=assigned_model,
            status=status,
            input_data=input_data,
            output_data=output_data,
            dependencies=dependencies,
            retry_count=retry_count,
            max_retries=max_retries,
            timeout_seconds=timeout_seconds,
            tokens_used=tokens_used,
            cost=cost,
            error_message=error_message,
            started_at=started_at,
            completed_at=completed_at,
            created_at=created_at,
        )


        mission_task_response.additional_properties = d
        return mission_task_response

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
