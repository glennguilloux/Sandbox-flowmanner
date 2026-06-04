from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.marketplace_listing import MarketplaceListing


T = TypeVar("T", bound="ListingsResponse")


@_attrs_define
class ListingsResponse:
    """
    Attributes:
        listings (list[MarketplaceListing]):
        total (int):
        page (int):
        per_page (int):
        has_more (bool):
    """

    listings: list[MarketplaceListing]
    total: int
    page: int
    per_page: int
    has_more: bool
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        listings = []
        for listings_item_data in self.listings:
            listings_item = listings_item_data.to_dict()
            listings.append(listings_item)

        total = self.total

        page = self.page

        per_page = self.per_page

        has_more = self.has_more

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "listings": listings,
                "total": total,
                "page": page,
                "per_page": per_page,
                "has_more": has_more,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.marketplace_listing import MarketplaceListing

        d = dict(src_dict)
        listings = []
        _listings = d.pop("listings")
        for listings_item_data in _listings:
            listings_item = MarketplaceListing.from_dict(listings_item_data)

            listings.append(listings_item)

        total = d.pop("total")

        page = d.pop("page")

        per_page = d.pop("per_page")

        has_more = d.pop("has_more")

        listings_response = cls(
            listings=listings,
            total=total,
            page=page,
            per_page=per_page,
            has_more=has_more,
        )

        listings_response.additional_properties = d
        return listings_response

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
