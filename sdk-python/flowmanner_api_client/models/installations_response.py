from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from typing import cast

if TYPE_CHECKING:
  from ..models.marketplace_installation import MarketplaceInstallation





T = TypeVar("T", bound="InstallationsResponse")



@_attrs_define
class InstallationsResponse:
    """ 
        Attributes:
            installations (list[MarketplaceInstallation]):
            total (int):
            page (int):
            per_page (int):
            has_more (bool):
     """

    installations: list[MarketplaceInstallation]
    total: int
    page: int
    per_page: int
    has_more: bool
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        from ..models.marketplace_installation import MarketplaceInstallation
        installations = []
        for installations_item_data in self.installations:
            installations_item = installations_item_data.to_dict()
            installations.append(installations_item)



        total = self.total

        page = self.page

        per_page = self.per_page

        has_more = self.has_more


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "installations": installations,
            "total": total,
            "page": page,
            "per_page": per_page,
            "has_more": has_more,
        })

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.marketplace_installation import MarketplaceInstallation
        d = dict(src_dict)
        installations = []
        _installations = d.pop("installations")
        for installations_item_data in (_installations):
            installations_item = MarketplaceInstallation.from_dict(installations_item_data)



            installations.append(installations_item)


        total = d.pop("total")

        page = d.pop("page")

        per_page = d.pop("per_page")

        has_more = d.pop("has_more")

        installations_response = cls(
            installations=installations,
            total=total,
            page=page,
            per_page=per_page,
            has_more=has_more,
        )


        installations_response.additional_properties = d
        return installations_response

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
