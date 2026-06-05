from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="MarketplaceReview")


@_attrs_define
class MarketplaceReview:
    """
    Attributes:
        id (str):
        listing_id (str):
        user_id (str):
        user_name (str):
        rating (int):
        user_avatar_url (None | str | Unset):
        title (None | str | Unset):
        content (None | str | Unset):
        created_at (str | Unset):  Default: ''.
        updated_at (str | Unset):  Default: ''.
        helpful_count (int | Unset):  Default: 0.
    """

    id: str
    listing_id: str
    user_id: str
    user_name: str
    rating: int
    user_avatar_url: None | str | Unset = UNSET
    title: None | str | Unset = UNSET
    content: None | str | Unset = UNSET
    created_at: str | Unset = ""
    updated_at: str | Unset = ""
    helpful_count: int | Unset = 0
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        id = self.id

        listing_id = self.listing_id

        user_id = self.user_id

        user_name = self.user_name

        rating = self.rating

        user_avatar_url: None | str | Unset
        if isinstance(self.user_avatar_url, Unset):
            user_avatar_url = UNSET
        else:
            user_avatar_url = self.user_avatar_url

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

        created_at = self.created_at

        updated_at = self.updated_at

        helpful_count = self.helpful_count

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "id": id,
                "listing_id": listing_id,
                "user_id": user_id,
                "user_name": user_name,
                "rating": rating,
            }
        )
        if user_avatar_url is not UNSET:
            field_dict["user_avatar_url"] = user_avatar_url
        if title is not UNSET:
            field_dict["title"] = title
        if content is not UNSET:
            field_dict["content"] = content
        if created_at is not UNSET:
            field_dict["created_at"] = created_at
        if updated_at is not UNSET:
            field_dict["updated_at"] = updated_at
        if helpful_count is not UNSET:
            field_dict["helpful_count"] = helpful_count

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        id = d.pop("id")

        listing_id = d.pop("listing_id")

        user_id = d.pop("user_id")

        user_name = d.pop("user_name")

        rating = d.pop("rating")

        def _parse_user_avatar_url(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        user_avatar_url = _parse_user_avatar_url(d.pop("user_avatar_url", UNSET))

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

        created_at = d.pop("created_at", UNSET)

        updated_at = d.pop("updated_at", UNSET)

        helpful_count = d.pop("helpful_count", UNSET)

        marketplace_review = cls(
            id=id,
            listing_id=listing_id,
            user_id=user_id,
            user_name=user_name,
            rating=rating,
            user_avatar_url=user_avatar_url,
            title=title,
            content=content,
            created_at=created_at,
            updated_at=updated_at,
            helpful_count=helpful_count,
        )

        marketplace_review.additional_properties = d
        return marketplace_review

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
