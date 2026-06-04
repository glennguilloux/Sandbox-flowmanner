from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset







T = TypeVar("T", bound="FileResponse")



@_attrs_define
class FileResponse:
    """ 
        Attributes:
            id (str):
            filename (str):
            content_type (str):
            size (int):
            user_id (str):
            created_at (str):
     """

    id: str
    filename: str
    content_type: str
    size: int
    user_id: str
    created_at: str
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        id = self.id

        filename = self.filename

        content_type = self.content_type

        size = self.size

        user_id = self.user_id

        created_at = self.created_at


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "id": id,
            "filename": filename,
            "content_type": content_type,
            "size": size,
            "user_id": user_id,
            "created_at": created_at,
        })

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        id = d.pop("id")

        filename = d.pop("filename")

        content_type = d.pop("content_type")

        size = d.pop("size")

        user_id = d.pop("user_id")

        created_at = d.pop("created_at")

        file_response = cls(
            id=id,
            filename=filename,
            content_type=content_type,
            size=size,
            user_id=user_id,
            created_at=created_at,
        )


        file_response.additional_properties = d
        return file_response

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
