from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field
from dateutil.parser import isoparse

from ..types import UNSET, Unset

T = TypeVar("T", bound="ChatFileResponse")


@_attrs_define
class ChatFileResponse:
    """
    Attributes:
        id (int):
        chat_id (int):
        filename (str):
        path (str):
        mime_type (None | str | Unset):
        size_bytes (int | None | Unset):
        uploaded_at (datetime.datetime | None | Unset):
    """

    id: int
    chat_id: int
    filename: str
    path: str
    mime_type: None | str | Unset = UNSET
    size_bytes: int | None | Unset = UNSET
    uploaded_at: datetime.datetime | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        id = self.id

        chat_id = self.chat_id

        filename = self.filename

        path = self.path

        mime_type: None | str | Unset
        if isinstance(self.mime_type, Unset):
            mime_type = UNSET
        else:
            mime_type = self.mime_type

        size_bytes: int | None | Unset
        if isinstance(self.size_bytes, Unset):
            size_bytes = UNSET
        else:
            size_bytes = self.size_bytes

        uploaded_at: None | str | Unset
        if isinstance(self.uploaded_at, Unset):
            uploaded_at = UNSET
        elif isinstance(self.uploaded_at, datetime.datetime):
            uploaded_at = self.uploaded_at.isoformat()
        else:
            uploaded_at = self.uploaded_at

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "id": id,
                "chat_id": chat_id,
                "filename": filename,
                "path": path,
            }
        )
        if mime_type is not UNSET:
            field_dict["mime_type"] = mime_type
        if size_bytes is not UNSET:
            field_dict["size_bytes"] = size_bytes
        if uploaded_at is not UNSET:
            field_dict["uploaded_at"] = uploaded_at

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        id = d.pop("id")

        chat_id = d.pop("chat_id")

        filename = d.pop("filename")

        path = d.pop("path")

        def _parse_mime_type(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        mime_type = _parse_mime_type(d.pop("mime_type", UNSET))

        def _parse_size_bytes(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        size_bytes = _parse_size_bytes(d.pop("size_bytes", UNSET))

        def _parse_uploaded_at(data: object) -> datetime.datetime | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                uploaded_at_type_0 = isoparse(data)

                return uploaded_at_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(datetime.datetime | None | Unset, data)

        uploaded_at = _parse_uploaded_at(d.pop("uploaded_at", UNSET))

        chat_file_response = cls(
            id=id,
            chat_id=chat_id,
            filename=filename,
            path=path,
            mime_type=mime_type,
            size_bytes=size_bytes,
            uploaded_at=uploaded_at,
        )

        chat_file_response.additional_properties = d
        return chat_file_response

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
