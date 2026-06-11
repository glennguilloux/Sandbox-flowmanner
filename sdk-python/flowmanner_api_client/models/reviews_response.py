from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.marketplace_review import MarketplaceReview
    from ..models.reviews_response_rating_breakdown import (
        ReviewsResponseRatingBreakdown,
    )


T = TypeVar("T", bound="ReviewsResponse")


@_attrs_define
class ReviewsResponse:
    """
    Attributes:
        reviews (list[MarketplaceReview]):
        total (int):
        page (int):
        per_page (int):
        has_more (bool):
        rating_breakdown (ReviewsResponseRatingBreakdown | Unset):
    """

    reviews: list[MarketplaceReview]
    total: int
    page: int
    per_page: int
    has_more: bool
    rating_breakdown: ReviewsResponseRatingBreakdown | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        reviews = []
        for reviews_item_data in self.reviews:
            reviews_item = reviews_item_data.to_dict()
            reviews.append(reviews_item)

        total = self.total

        page = self.page

        per_page = self.per_page

        has_more = self.has_more

        rating_breakdown: dict[str, Any] | Unset = UNSET
        if not isinstance(self.rating_breakdown, Unset):
            rating_breakdown = self.rating_breakdown.to_dict()

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "reviews": reviews,
                "total": total,
                "page": page,
                "per_page": per_page,
                "has_more": has_more,
            }
        )
        if rating_breakdown is not UNSET:
            field_dict["rating_breakdown"] = rating_breakdown

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.marketplace_review import MarketplaceReview
        from ..models.reviews_response_rating_breakdown import (
            ReviewsResponseRatingBreakdown,
        )

        d = dict(src_dict)
        reviews = []
        _reviews = d.pop("reviews")
        for reviews_item_data in _reviews:
            reviews_item = MarketplaceReview.from_dict(reviews_item_data)

            reviews.append(reviews_item)

        total = d.pop("total")

        page = d.pop("page")

        per_page = d.pop("per_page")

        has_more = d.pop("has_more")

        _rating_breakdown = d.pop("rating_breakdown", UNSET)
        rating_breakdown: ReviewsResponseRatingBreakdown | Unset
        if isinstance(_rating_breakdown, Unset):
            rating_breakdown = UNSET
        else:
            rating_breakdown = ReviewsResponseRatingBreakdown.from_dict(_rating_breakdown)

        reviews_response = cls(
            reviews=reviews,
            total=total,
            page=page,
            per_page=per_page,
            has_more=has_more,
            rating_breakdown=rating_breakdown,
        )

        reviews_response.additional_properties = d
        return reviews_response

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
