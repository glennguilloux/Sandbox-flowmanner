from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast
from uuid import UUID

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.mission_task_create_dependencies_type_1 import (
        MissionTaskCreateDependenciesType1,
    )
    from ..models.mission_task_create_input_data_type_0 import (
        MissionTaskCreateInputDataType0,
    )


T = TypeVar("T", bound="MissionTaskCreate")


@_attrs_define
class MissionTaskCreate:
    """
    Attributes:
        title (str):
        description (None | str | Unset):
        task_type (str | Unset):  Default: 'general'.
        order_index (int | None | Unset):
        input_data (MissionTaskCreateInputDataType0 | None | Unset):
        dependencies (list[Any] | MissionTaskCreateDependenciesType1 | None | Unset):
        assigned_agent_id (None | Unset | UUID):
        assigned_model (None | str | Unset):
    """

    title: str
    description: None | str | Unset = UNSET
    task_type: str | Unset = "general"
    order_index: int | None | Unset = UNSET
    input_data: MissionTaskCreateInputDataType0 | None | Unset = UNSET
    dependencies: list[Any] | MissionTaskCreateDependenciesType1 | None | Unset = UNSET
    assigned_agent_id: None | Unset | UUID = UNSET
    assigned_model: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.mission_task_create_dependencies_type_1 import (
            MissionTaskCreateDependenciesType1,
        )
        from ..models.mission_task_create_input_data_type_0 import (
            MissionTaskCreateInputDataType0,
        )

        title = self.title

        description: None | str | Unset
        if isinstance(self.description, Unset):
            description = UNSET
        else:
            description = self.description

        task_type = self.task_type

        order_index: int | None | Unset
        if isinstance(self.order_index, Unset):
            order_index = UNSET
        else:
            order_index = self.order_index

        input_data: dict[str, Any] | None | Unset
        if isinstance(self.input_data, Unset):
            input_data = UNSET
        elif isinstance(self.input_data, MissionTaskCreateInputDataType0):
            input_data = self.input_data.to_dict()
        else:
            input_data = self.input_data

        dependencies: dict[str, Any] | list[Any] | None | Unset
        if isinstance(self.dependencies, Unset):
            dependencies = UNSET
        elif isinstance(self.dependencies, list):
            dependencies = self.dependencies

        elif isinstance(self.dependencies, MissionTaskCreateDependenciesType1):
            dependencies = self.dependencies.to_dict()
        else:
            dependencies = self.dependencies

        assigned_agent_id: None | str | Unset
        if isinstance(self.assigned_agent_id, Unset):
            assigned_agent_id = UNSET
        elif isinstance(self.assigned_agent_id, UUID):
            assigned_agent_id = str(self.assigned_agent_id)
        else:
            assigned_agent_id = self.assigned_agent_id

        assigned_model: None | str | Unset
        if isinstance(self.assigned_model, Unset):
            assigned_model = UNSET
        else:
            assigned_model = self.assigned_model

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "title": title,
            }
        )
        if description is not UNSET:
            field_dict["description"] = description
        if task_type is not UNSET:
            field_dict["task_type"] = task_type
        if order_index is not UNSET:
            field_dict["order_index"] = order_index
        if input_data is not UNSET:
            field_dict["input_data"] = input_data
        if dependencies is not UNSET:
            field_dict["dependencies"] = dependencies
        if assigned_agent_id is not UNSET:
            field_dict["assigned_agent_id"] = assigned_agent_id
        if assigned_model is not UNSET:
            field_dict["assigned_model"] = assigned_model

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.mission_task_create_dependencies_type_1 import (
            MissionTaskCreateDependenciesType1,
        )
        from ..models.mission_task_create_input_data_type_0 import (
            MissionTaskCreateInputDataType0,
        )

        d = dict(src_dict)
        title = d.pop("title")

        def _parse_description(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        description = _parse_description(d.pop("description", UNSET))

        task_type = d.pop("task_type", UNSET)

        def _parse_order_index(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        order_index = _parse_order_index(d.pop("order_index", UNSET))

        def _parse_input_data(
            data: object,
        ) -> MissionTaskCreateInputDataType0 | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                input_data_type_0 = MissionTaskCreateInputDataType0.from_dict(data)

                return input_data_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(MissionTaskCreateInputDataType0 | None | Unset, data)

        input_data = _parse_input_data(d.pop("input_data", UNSET))

        def _parse_dependencies(
            data: object,
        ) -> list[Any] | MissionTaskCreateDependenciesType1 | None | Unset:
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
                dependencies_type_1 = MissionTaskCreateDependenciesType1.from_dict(data)

                return dependencies_type_1
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(list[Any] | MissionTaskCreateDependenciesType1 | None | Unset, data)

        dependencies = _parse_dependencies(d.pop("dependencies", UNSET))

        def _parse_assigned_agent_id(data: object) -> None | Unset | UUID:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                assigned_agent_id_type_0 = UUID(data)

                return assigned_agent_id_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | Unset | UUID, data)

        assigned_agent_id = _parse_assigned_agent_id(d.pop("assigned_agent_id", UNSET))

        def _parse_assigned_model(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        assigned_model = _parse_assigned_model(d.pop("assigned_model", UNSET))

        mission_task_create = cls(
            title=title,
            description=description,
            task_type=task_type,
            order_index=order_index,
            input_data=input_data,
            dependencies=dependencies,
            assigned_agent_id=assigned_agent_id,
            assigned_model=assigned_model,
        )

        mission_task_create.additional_properties = d
        return mission_task_create

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
