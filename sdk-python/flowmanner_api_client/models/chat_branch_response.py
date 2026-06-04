from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..types import UNSET, Unset
from dateutil.parser import isoparse
from typing import cast
import datetime






T = TypeVar("T", bound="ChatBranchResponse")



@_attrs_define
class ChatBranchResponse:
    """ 
        Attributes:
            id (int):
            thread_id (int):
            parent_thread_id (int):
            parent_message_id (int):
            user_id (int):
            title (str):
            created_at (datetime.datetime | None | Unset):
     """

    id: int
    thread_id: int
    parent_thread_id: int
    parent_message_id: int
    user_id: int
    title: str
    created_at: datetime.datetime | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        id = self.id

        thread_id = self.thread_id

        parent_thread_id = self.parent_thread_id

        parent_message_id = self.parent_message_id

        user_id = self.user_id

        title = self.title

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
            "thread_id": thread_id,
            "parent_thread_id": parent_thread_id,
            "parent_message_id": parent_message_id,
            "user_id": user_id,
            "title": title,
        })
        if created_at is not UNSET:
            field_dict["created_at"] = created_at

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        id = d.pop("id")

        thread_id = d.pop("thread_id")

        parent_thread_id = d.pop("parent_thread_id")

        parent_message_id = d.pop("parent_message_id")

        user_id = d.pop("user_id")

        title = d.pop("title")

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


        chat_branch_response = cls(
            id=id,
            thread_id=thread_id,
            parent_thread_id=parent_thread_id,
            parent_message_id=parent_message_id,
            user_id=user_id,
            title=title,
            created_at=created_at,
        )


        chat_branch_response.additional_properties = d
        return chat_branch_response

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
