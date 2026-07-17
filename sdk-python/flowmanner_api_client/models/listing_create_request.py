from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="ListingCreateRequest")


@_attrs_define
class ListingCreateRequest:
    """
    Attributes:
        name (str):
        description (str | Unset):  Default: ''.
        listing_type (str | Unset):  Default: 'tool'.
        item_id (str | Unset):  Default: ''.
        price (float | Unset):  Default: 0.0.
        category (str | Unset):  Default: 'general'.
        tags (list[str] | Unset):
        documentation_url (None | str | Unset):
        repository_url (None | str | Unset):
        icon_url (None | str | Unset):
    """

    name: str
    description: str | Unset = ""
    listing_type: str | Unset = "tool"
    item_id: str | Unset = ""
    price: float | Unset = 0.0
    category: str | Unset = "general"
    tags: list[str] | Unset = UNSET
    documentation_url: None | str | Unset = UNSET
    repository_url: None | str | Unset = UNSET
    icon_url: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        name = self.name

        description = self.description

        listing_type = self.listing_type

        item_id = self.item_id

        price = self.price

        category = self.category

        tags: list[str] | Unset = UNSET
        if not isinstance(self.tags, Unset):
            tags = self.tags

        documentation_url: None | str | Unset
        if isinstance(self.documentation_url, Unset):
            documentation_url = UNSET
        else:
            documentation_url = self.documentation_url

        repository_url: None | str | Unset
        if isinstance(self.repository_url, Unset):
            repository_url = UNSET
        else:
            repository_url = self.repository_url

        icon_url: None | str | Unset
        if isinstance(self.icon_url, Unset):
            icon_url = UNSET
        else:
            icon_url = self.icon_url

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "name": name,
            }
        )
        if description is not UNSET:
            field_dict["description"] = description
        if listing_type is not UNSET:
            field_dict["listing_type"] = listing_type
        if item_id is not UNSET:
            field_dict["item_id"] = item_id
        if price is not UNSET:
            field_dict["price"] = price
        if category is not UNSET:
            field_dict["category"] = category
        if tags is not UNSET:
            field_dict["tags"] = tags
        if documentation_url is not UNSET:
            field_dict["documentation_url"] = documentation_url
        if repository_url is not UNSET:
            field_dict["repository_url"] = repository_url
        if icon_url is not UNSET:
            field_dict["icon_url"] = icon_url

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        name = d.pop("name")

        description = d.pop("description", UNSET)

        listing_type = d.pop("listing_type", UNSET)

        item_id = d.pop("item_id", UNSET)

        price = d.pop("price", UNSET)

        category = d.pop("category", UNSET)

        tags = cast(list[str], d.pop("tags", UNSET))

        def _parse_documentation_url(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        documentation_url = _parse_documentation_url(d.pop("documentation_url", UNSET))

        def _parse_repository_url(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        repository_url = _parse_repository_url(d.pop("repository_url", UNSET))

        def _parse_icon_url(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        icon_url = _parse_icon_url(d.pop("icon_url", UNSET))

        listing_create_request = cls(
            name=name,
            description=description,
            listing_type=listing_type,
            item_id=item_id,
            price=price,
            category=category,
            tags=tags,
            documentation_url=documentation_url,
            repository_url=repository_url,
            icon_url=icon_url,
        )

        listing_create_request.additional_properties = d
        return listing_create_request

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
