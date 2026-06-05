from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

T = TypeVar("T", bound="ChatBranchCreate")


@_attrs_define
class ChatBranchCreate:
    """
    Attributes:
        parent_thread_id (int):
        parent_message_id (int):
        title (str):
    """

    parent_thread_id: int
    parent_message_id: int
    title: str
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        parent_thread_id = self.parent_thread_id

        parent_message_id = self.parent_message_id

        title = self.title

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "parent_thread_id": parent_thread_id,
                "parent_message_id": parent_message_id,
                "title": title,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        parent_thread_id = d.pop("parent_thread_id")

        parent_message_id = d.pop("parent_message_id")

        title = d.pop("title")

        chat_branch_create = cls(
            parent_thread_id=parent_thread_id,
            parent_message_id=parent_message_id,
            title=title,
        )

        chat_branch_create.additional_properties = d
        return chat_branch_create

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
