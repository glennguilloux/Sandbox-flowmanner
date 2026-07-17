from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="ReviewCreateRequest")


@_attrs_define
class ReviewCreateRequest:
    """
    Attributes:
        rating (int):
        title (None | str | Unset):
        content (None | str | Unset):
        pros (list[str] | None | Unset):
        cons (list[str] | None | Unset):
    """

    rating: int
    title: None | str | Unset = UNSET
    content: None | str | Unset = UNSET
    pros: list[str] | None | Unset = UNSET
    cons: list[str] | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        rating = self.rating

        title: None | str | Unset
        if isinstance(self.title, Unset):
            title = UNSET
        else:
            title = self.title

        content: None | str | Unset
        if isinstance(self.content, Unset):
            content = UNSET
        else:
            content = self.content

        pros: list[str] | None | Unset
        if isinstance(self.pros, Unset):
            pros = UNSET
        elif isinstance(self.pros, list):
            pros = self.pros

        else:
            pros = self.pros

        cons: list[str] | None | Unset
        if isinstance(self.cons, Unset):
            cons = UNSET
        elif isinstance(self.cons, list):
            cons = self.cons

        else:
            cons = self.cons

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "rating": rating,
            }
        )
        if title is not UNSET:
            field_dict["title"] = title
        if content is not UNSET:
            field_dict["content"] = content
        if pros is not UNSET:
            field_dict["pros"] = pros
        if cons is not UNSET:
            field_dict["cons"] = cons

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        rating = d.pop("rating")

        def _parse_title(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        title = _parse_title(d.pop("title", UNSET))

        def _parse_content(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        content = _parse_content(d.pop("content", UNSET))

        def _parse_pros(data: object) -> list[str] | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, list):
                    raise TypeError()
                pros_type_0 = cast(list[str], data)

                return pros_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(list[str] | None | Unset, data)

        pros = _parse_pros(d.pop("pros", UNSET))

        def _parse_cons(data: object) -> list[str] | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, list):
                    raise TypeError()
                cons_type_0 = cast(list[str], data)

                return cons_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(list[str] | None | Unset, data)

        cons = _parse_cons(d.pop("cons", UNSET))

        review_create_request = cls(
            rating=rating,
            title=title,
            content=content,
            pros=pros,
            cons=cons,
        )

        review_create_request.additional_properties = d
        return review_create_request

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
