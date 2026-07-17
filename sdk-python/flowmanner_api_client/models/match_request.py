from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="MatchRequest")


@_attrs_define
class MatchRequest:
    """
    Attributes:
        task_description (str):
        task_type (None | str | Unset):
        required_tools (list[str] | Unset):
    """

    task_description: str
    task_type: None | str | Unset = UNSET
    required_tools: list[str] | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        task_description = self.task_description

        task_type: None | str | Unset
        if isinstance(self.task_type, Unset):
            task_type = UNSET
        else:
            task_type = self.task_type

        required_tools: list[str] | Unset = UNSET
        if not isinstance(self.required_tools, Unset):
            required_tools = self.required_tools

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "task_description": task_description,
            }
        )
        if task_type is not UNSET:
            field_dict["task_type"] = task_type
        if required_tools is not UNSET:
            field_dict["required_tools"] = required_tools

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        task_description = d.pop("task_description")

        def _parse_task_type(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        task_type = _parse_task_type(d.pop("task_type", UNSET))

        required_tools = cast(list[str], d.pop("required_tools", UNSET))

        match_request = cls(
            task_description=task_description,
            task_type=task_type,
            required_tools=required_tools,
        )

        match_request.additional_properties = d
        return match_request

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
