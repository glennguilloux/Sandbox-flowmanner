from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="MarketplaceListing")


@_attrs_define
class MarketplaceListing:
    """
    Attributes:
        id (str):
        slug (str):
        name (str):
        type_ (str):
        category (str):
        description (None | str | Unset):
        icon_url (None | str | Unset):
        thumbnail_url (None | str | Unset):
        screenshots (list[str] | Unset):
        author_name (None | str | Unset):
        author_id (None | str | Unset):
        pricing_type (str | Unset):  Default: 'free'.
        price_cents (int | None | Unset):
        install_count (int | Unset):  Default: 0.
        rating_avg (float | None | Unset):
        rating_count (int | Unset):  Default: 0.
        status (str | Unset):  Default: 'approved'.
        tags (list[str] | Unset):
        version (None | str | Unset):
        created_at (str | Unset):  Default: ''.
        updated_at (str | Unset):  Default: ''.
        is_featured (bool | Unset):  Default: False.
    """

    id: str
    slug: str
    name: str
    type_: str
    category: str
    description: None | str | Unset = UNSET
    icon_url: None | str | Unset = UNSET
    thumbnail_url: None | str | Unset = UNSET
    screenshots: list[str] | Unset = UNSET
    author_name: None | str | Unset = UNSET
    author_id: None | str | Unset = UNSET
    pricing_type: str | Unset = "free"
    price_cents: int | None | Unset = UNSET
    install_count: int | Unset = 0
    rating_avg: float | None | Unset = UNSET
    rating_count: int | Unset = 0
    status: str | Unset = "approved"
    tags: list[str] | Unset = UNSET
    version: None | str | Unset = UNSET
    created_at: str | Unset = ""
    updated_at: str | Unset = ""
    is_featured: bool | Unset = False
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        id = self.id

        slug = self.slug

        name = self.name

        type_ = self.type_

        category = self.category

        description: None | str | Unset
        if isinstance(self.description, Unset):
            description = UNSET
        else:
            description = self.description

        icon_url: None | str | Unset
        if isinstance(self.icon_url, Unset):
            icon_url = UNSET
        else:
            icon_url = self.icon_url

        thumbnail_url: None | str | Unset
        if isinstance(self.thumbnail_url, Unset):
            thumbnail_url = UNSET
        else:
            thumbnail_url = self.thumbnail_url

        screenshots: list[str] | Unset = UNSET
        if not isinstance(self.screenshots, Unset):
            screenshots = self.screenshots

        author_name: None | str | Unset
        if isinstance(self.author_name, Unset):
            author_name = UNSET
        else:
            author_name = self.author_name

        author_id: None | str | Unset
        if isinstance(self.author_id, Unset):
            author_id = UNSET
        else:
            author_id = self.author_id

        pricing_type = self.pricing_type

        price_cents: int | None | Unset
        if isinstance(self.price_cents, Unset):
            price_cents = UNSET
        else:
            price_cents = self.price_cents

        install_count = self.install_count

        rating_avg: float | None | Unset
        if isinstance(self.rating_avg, Unset):
            rating_avg = UNSET
        else:
            rating_avg = self.rating_avg

        rating_count = self.rating_count

        status = self.status

        tags: list[str] | Unset = UNSET
        if not isinstance(self.tags, Unset):
            tags = self.tags

        version: None | str | Unset
        if isinstance(self.version, Unset):
            version = UNSET
        else:
            version = self.version

        created_at = self.created_at

        updated_at = self.updated_at

        is_featured = self.is_featured

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "id": id,
                "slug": slug,
                "name": name,
                "type": type_,
                "category": category,
            }
        )
        if description is not UNSET:
            field_dict["description"] = description
        if icon_url is not UNSET:
            field_dict["icon_url"] = icon_url
        if thumbnail_url is not UNSET:
            field_dict["thumbnail_url"] = thumbnail_url
        if screenshots is not UNSET:
            field_dict["screenshots"] = screenshots
        if author_name is not UNSET:
            field_dict["author_name"] = author_name
        if author_id is not UNSET:
            field_dict["author_id"] = author_id
        if pricing_type is not UNSET:
            field_dict["pricing_type"] = pricing_type
        if price_cents is not UNSET:
            field_dict["price_cents"] = price_cents
        if install_count is not UNSET:
            field_dict["install_count"] = install_count
        if rating_avg is not UNSET:
            field_dict["rating_avg"] = rating_avg
        if rating_count is not UNSET:
            field_dict["rating_count"] = rating_count
        if status is not UNSET:
            field_dict["status"] = status
        if tags is not UNSET:
            field_dict["tags"] = tags
        if version is not UNSET:
            field_dict["version"] = version
        if created_at is not UNSET:
            field_dict["created_at"] = created_at
        if updated_at is not UNSET:
            field_dict["updated_at"] = updated_at
        if is_featured is not UNSET:
            field_dict["is_featured"] = is_featured

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        id = d.pop("id")

        slug = d.pop("slug")

        name = d.pop("name")

        type_ = d.pop("type")

        category = d.pop("category")

        def _parse_description(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        description = _parse_description(d.pop("description", UNSET))

        def _parse_icon_url(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        icon_url = _parse_icon_url(d.pop("icon_url", UNSET))

        def _parse_thumbnail_url(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        thumbnail_url = _parse_thumbnail_url(d.pop("thumbnail_url", UNSET))

        screenshots = cast(list[str], d.pop("screenshots", UNSET))

        def _parse_author_name(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        author_name = _parse_author_name(d.pop("author_name", UNSET))

        def _parse_author_id(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        author_id = _parse_author_id(d.pop("author_id", UNSET))

        pricing_type = d.pop("pricing_type", UNSET)

        def _parse_price_cents(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        price_cents = _parse_price_cents(d.pop("price_cents", UNSET))

        install_count = d.pop("install_count", UNSET)

        def _parse_rating_avg(data: object) -> float | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(float | None | Unset, data)

        rating_avg = _parse_rating_avg(d.pop("rating_avg", UNSET))

        rating_count = d.pop("rating_count", UNSET)

        status = d.pop("status", UNSET)

        tags = cast(list[str], d.pop("tags", UNSET))

        def _parse_version(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        version = _parse_version(d.pop("version", UNSET))

        created_at = d.pop("created_at", UNSET)

        updated_at = d.pop("updated_at", UNSET)

        is_featured = d.pop("is_featured", UNSET)

        marketplace_listing = cls(
            id=id,
            slug=slug,
            name=name,
            type_=type_,
            category=category,
            description=description,
            icon_url=icon_url,
            thumbnail_url=thumbnail_url,
            screenshots=screenshots,
            author_name=author_name,
            author_id=author_id,
            pricing_type=pricing_type,
            price_cents=price_cents,
            install_count=install_count,
            rating_avg=rating_avg,
            rating_count=rating_count,
            status=status,
            tags=tags,
            version=version,
            created_at=created_at,
            updated_at=updated_at,
            is_featured=is_featured,
        )

        marketplace_listing.additional_properties = d
        return marketplace_listing

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
