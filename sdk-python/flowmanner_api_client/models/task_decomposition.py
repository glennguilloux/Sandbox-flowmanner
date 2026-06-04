from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..types import UNSET, Unset
from typing import cast






T = TypeVar("T", bound="TaskDecomposition")



@_attrs_define
class TaskDecomposition:
    """ 
        Attributes:
            title (str):
            description (str | Unset):  Default: ''.
            task_type (str | Unset):  Default: 'general'.
            depends_on (list[int] | Unset):
            assigned_model (None | str | Unset):
     """

    title: str
    description: str | Unset = ''
    task_type: str | Unset = 'general'
    depends_on: list[int] | Unset = UNSET
    assigned_model: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        title = self.title

        description = self.description

        task_type = self.task_type

        depends_on: list[int] | Unset = UNSET
        if not isinstance(self.depends_on, Unset):
            depends_on = self.depends_on



        assigned_model: None | str | Unset
        if isinstance(self.assigned_model, Unset):
            assigned_model = UNSET
        else:
            assigned_model = self.assigned_model


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "title": title,
        })
        if description is not UNSET:
            field_dict["description"] = description
        if task_type is not UNSET:
            field_dict["task_type"] = task_type
        if depends_on is not UNSET:
            field_dict["depends_on"] = depends_on
        if assigned_model is not UNSET:
            field_dict["assigned_model"] = assigned_model

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        title = d.pop("title")

        description = d.pop("description", UNSET)

        task_type = d.pop("task_type", UNSET)

        depends_on = cast(list[int], d.pop("depends_on", UNSET))


        def _parse_assigned_model(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        assigned_model = _parse_assigned_model(d.pop("assigned_model", UNSET))


        task_decomposition = cls(
            title=title,
            description=description,
            task_type=task_type,
            depends_on=depends_on,
            assigned_model=assigned_model,
        )


        task_decomposition.additional_properties = d
        return task_decomposition

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
