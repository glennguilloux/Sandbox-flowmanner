from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

T = TypeVar("T", bound="BodyIngestBookApiV1RagIngestPost")


@_attrs_define
class BodyIngestBookApiV1RagIngestPost:
    """
    Attributes:
        book_title (str):
        text (str):
    """

    book_title: str
    text: str
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        book_title = self.book_title

        text = self.text

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "book_title": book_title,
                "text": text,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        book_title = d.pop("book_title")

        text = d.pop("text")

        body_ingest_book_api_v1_rag_ingest_post = cls(
            book_title=book_title,
            text=text,
        )

        body_ingest_book_api_v1_rag_ingest_post.additional_properties = d
        return body_ingest_book_api_v1_rag_ingest_post

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
