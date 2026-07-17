from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="BodyGeneratePromptApiV1RagPromptPost")


@_attrs_define
class BodyGeneratePromptApiV1RagPromptPost:
    """
    Attributes:
        goal (str):
        role_description (None | str | Unset):
        topics (list[str] | None | Unset):
        books (list[str] | None | Unset):
    """

    goal: str
    role_description: None | str | Unset = UNSET
    topics: list[str] | None | Unset = UNSET
    books: list[str] | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        goal = self.goal

        role_description: None | str | Unset
        if isinstance(self.role_description, Unset):
            role_description = UNSET
        else:
            role_description = self.role_description

        topics: list[str] | None | Unset
        if isinstance(self.topics, Unset):
            topics = UNSET
        elif isinstance(self.topics, list):
            topics = self.topics

        else:
            topics = self.topics

        books: list[str] | None | Unset
        if isinstance(self.books, Unset):
            books = UNSET
        elif isinstance(self.books, list):
            books = self.books

        else:
            books = self.books

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "goal": goal,
            }
        )
        if role_description is not UNSET:
            field_dict["role_description"] = role_description
        if topics is not UNSET:
            field_dict["topics"] = topics
        if books is not UNSET:
            field_dict["books"] = books

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        goal = d.pop("goal")

        def _parse_role_description(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        role_description = _parse_role_description(d.pop("role_description", UNSET))

        def _parse_topics(data: object) -> list[str] | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, list):
                    raise TypeError()
                topics_type_0 = cast(list[str], data)

                return topics_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(list[str] | None | Unset, data)

        topics = _parse_topics(d.pop("topics", UNSET))

        def _parse_books(data: object) -> list[str] | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, list):
                    raise TypeError()
                books_type_0 = cast(list[str], data)

                return books_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(list[str] | None | Unset, data)

        books = _parse_books(d.pop("books", UNSET))

        body_generate_prompt_api_v1_rag_prompt_post = cls(
            goal=goal,
            role_description=role_description,
            topics=topics,
            books=books,
        )

        body_generate_prompt_api_v1_rag_prompt_post.additional_properties = d
        return body_generate_prompt_api_v1_rag_prompt_post

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
