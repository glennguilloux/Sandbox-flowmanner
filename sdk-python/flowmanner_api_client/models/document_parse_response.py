from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="DocumentParseResponse")


@_attrs_define
class DocumentParseResponse:
    """Response from document parsing.

    Attributes:
        filename (str):
        mime_type (str):
        text_content (str | Unset):  Default: ''.
        structured_data (Any | Unset):
        page_count (int | None | Unset):
        error (None | str | Unset):
    """

    filename: str
    mime_type: str
    text_content: str | Unset = ""
    structured_data: Any | Unset = UNSET
    page_count: int | None | Unset = UNSET
    error: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        filename = self.filename

        mime_type = self.mime_type

        text_content = self.text_content

        structured_data = self.structured_data

        page_count: int | None | Unset
        if isinstance(self.page_count, Unset):
            page_count = UNSET
        else:
            page_count = self.page_count

        error: None | str | Unset
        if isinstance(self.error, Unset):
            error = UNSET
        else:
            error = self.error

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "filename": filename,
                "mime_type": mime_type,
            }
        )
        if text_content is not UNSET:
            field_dict["text_content"] = text_content
        if structured_data is not UNSET:
            field_dict["structured_data"] = structured_data
        if page_count is not UNSET:
            field_dict["page_count"] = page_count
        if error is not UNSET:
            field_dict["error"] = error

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        filename = d.pop("filename")

        mime_type = d.pop("mime_type")

        text_content = d.pop("text_content", UNSET)

        structured_data = d.pop("structured_data", UNSET)

        def _parse_page_count(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        page_count = _parse_page_count(d.pop("page_count", UNSET))

        def _parse_error(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        error = _parse_error(d.pop("error", UNSET))

        document_parse_response = cls(
            filename=filename,
            mime_type=mime_type,
            text_content=text_content,
            structured_data=structured_data,
            page_count=page_count,
            error=error,
        )

        document_parse_response.additional_properties = d
        return document_parse_response

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
