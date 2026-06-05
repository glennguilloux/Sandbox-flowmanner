from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.task_decomposition import TaskDecomposition


T = TypeVar("T", bound="DecomposeRequest")


@_attrs_define
class DecomposeRequest:
    """
    Attributes:
        mode (str | Unset):  Default: 'manual'.
        tasks (list[TaskDecomposition] | None | Unset):
    """

    mode: str | Unset = "manual"
    tasks: list[TaskDecomposition] | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        mode = self.mode

        tasks: list[dict[str, Any]] | None | Unset
        if isinstance(self.tasks, Unset):
            tasks = UNSET
        elif isinstance(self.tasks, list):
            tasks = []
            for tasks_type_0_item_data in self.tasks:
                tasks_type_0_item = tasks_type_0_item_data.to_dict()
                tasks.append(tasks_type_0_item)

        else:
            tasks = self.tasks

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if mode is not UNSET:
            field_dict["mode"] = mode
        if tasks is not UNSET:
            field_dict["tasks"] = tasks

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.task_decomposition import TaskDecomposition

        d = dict(src_dict)
        mode = d.pop("mode", UNSET)

        def _parse_tasks(data: object) -> list[TaskDecomposition] | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, list):
                    raise TypeError()
                tasks_type_0 = []
                _tasks_type_0 = data
                for tasks_type_0_item_data in _tasks_type_0:
                    tasks_type_0_item = TaskDecomposition.from_dict(
                        tasks_type_0_item_data
                    )

                    tasks_type_0.append(tasks_type_0_item)

                return tasks_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(list[TaskDecomposition] | None | Unset, data)

        tasks = _parse_tasks(d.pop("tasks", UNSET))

        decompose_request = cls(
            mode=mode,
            tasks=tasks,
        )

        decompose_request.additional_properties = d
        return decompose_request

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
