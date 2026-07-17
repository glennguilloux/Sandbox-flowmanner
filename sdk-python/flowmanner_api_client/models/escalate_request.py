from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="EscalateRequest")


@_attrs_define
class EscalateRequest:
    """
    Attributes:
        task_id (str):
        task_description (str):
        error_message (str):
        current_agent_id (None | str | Unset):
        current_agent_name (None | str | Unset):
        policy (str | Unset):  Default: 'default'.
    """

    task_id: str
    task_description: str
    error_message: str
    current_agent_id: None | str | Unset = UNSET
    current_agent_name: None | str | Unset = UNSET
    policy: str | Unset = "default"
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        task_id = self.task_id

        task_description = self.task_description

        error_message = self.error_message

        current_agent_id: None | str | Unset
        if isinstance(self.current_agent_id, Unset):
            current_agent_id = UNSET
        else:
            current_agent_id = self.current_agent_id

        current_agent_name: None | str | Unset
        if isinstance(self.current_agent_name, Unset):
            current_agent_name = UNSET
        else:
            current_agent_name = self.current_agent_name

        policy = self.policy

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "task_id": task_id,
                "task_description": task_description,
                "error_message": error_message,
            }
        )
        if current_agent_id is not UNSET:
            field_dict["current_agent_id"] = current_agent_id
        if current_agent_name is not UNSET:
            field_dict["current_agent_name"] = current_agent_name
        if policy is not UNSET:
            field_dict["policy"] = policy

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        task_id = d.pop("task_id")

        task_description = d.pop("task_description")

        error_message = d.pop("error_message")

        def _parse_current_agent_id(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        current_agent_id = _parse_current_agent_id(d.pop("current_agent_id", UNSET))

        def _parse_current_agent_name(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        current_agent_name = _parse_current_agent_name(d.pop("current_agent_name", UNSET))

        policy = d.pop("policy", UNSET)

        escalate_request = cls(
            task_id=task_id,
            task_description=task_description,
            error_message=error_message,
            current_agent_id=current_agent_id,
            current_agent_name=current_agent_name,
            policy=policy,
        )

        escalate_request.additional_properties = d
        return escalate_request

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
