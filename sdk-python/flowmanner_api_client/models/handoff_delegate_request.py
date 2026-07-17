from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="HandoffDelegateRequest")


@_attrs_define
class HandoffDelegateRequest:
    """
    Attributes:
        from_agent_id (str):
        from_agent_name (str):
        task_description (str):
        task_type (str | Unset):  Default: 'general'.
        to_agent_id (None | str | Unset):
        priority (int | Unset):  Default: 0.
    """

    from_agent_id: str
    from_agent_name: str
    task_description: str
    task_type: str | Unset = "general"
    to_agent_id: None | str | Unset = UNSET
    priority: int | Unset = 0
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from_agent_id = self.from_agent_id

        from_agent_name = self.from_agent_name

        task_description = self.task_description

        task_type = self.task_type

        to_agent_id: None | str | Unset
        if isinstance(self.to_agent_id, Unset):
            to_agent_id = UNSET
        else:
            to_agent_id = self.to_agent_id

        priority = self.priority

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "from_agent_id": from_agent_id,
                "from_agent_name": from_agent_name,
                "task_description": task_description,
            }
        )
        if task_type is not UNSET:
            field_dict["task_type"] = task_type
        if to_agent_id is not UNSET:
            field_dict["to_agent_id"] = to_agent_id
        if priority is not UNSET:
            field_dict["priority"] = priority

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        from_agent_id = d.pop("from_agent_id")

        from_agent_name = d.pop("from_agent_name")

        task_description = d.pop("task_description")

        task_type = d.pop("task_type", UNSET)

        def _parse_to_agent_id(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        to_agent_id = _parse_to_agent_id(d.pop("to_agent_id", UNSET))

        priority = d.pop("priority", UNSET)

        handoff_delegate_request = cls(
            from_agent_id=from_agent_id,
            from_agent_name=from_agent_name,
            task_description=task_description,
            task_type=task_type,
            to_agent_id=to_agent_id,
            priority=priority,
        )

        handoff_delegate_request.additional_properties = d
        return handoff_delegate_request

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
