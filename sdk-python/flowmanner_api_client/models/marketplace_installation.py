from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..types import UNSET, Unset
from typing import cast






T = TypeVar("T", bound="MarketplaceInstallation")



@_attrs_define
class MarketplaceInstallation:
    """ 
        Attributes:
            id (str):
            listing_id (str):
            listing_name (str):
            listing_slug (str):
            installed_at (str):
            listing_icon_url (None | str | Unset):
            version (None | str | Unset):
     """

    id: str
    listing_id: str
    listing_name: str
    listing_slug: str
    installed_at: str
    listing_icon_url: None | str | Unset = UNSET
    version: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        id = self.id

        listing_id = self.listing_id

        listing_name = self.listing_name

        listing_slug = self.listing_slug

        installed_at = self.installed_at

        listing_icon_url: None | str | Unset
        if isinstance(self.listing_icon_url, Unset):
            listing_icon_url = UNSET
        else:
            listing_icon_url = self.listing_icon_url

        version: None | str | Unset
        if isinstance(self.version, Unset):
            version = UNSET
        else:
            version = self.version


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "id": id,
            "listing_id": listing_id,
            "listing_name": listing_name,
            "listing_slug": listing_slug,
            "installed_at": installed_at,
        })
        if listing_icon_url is not UNSET:
            field_dict["listing_icon_url"] = listing_icon_url
        if version is not UNSET:
            field_dict["version"] = version

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        id = d.pop("id")

        listing_id = d.pop("listing_id")

        listing_name = d.pop("listing_name")

        listing_slug = d.pop("listing_slug")

        installed_at = d.pop("installed_at")

        def _parse_listing_icon_url(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        listing_icon_url = _parse_listing_icon_url(d.pop("listing_icon_url", UNSET))


        def _parse_version(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        version = _parse_version(d.pop("version", UNSET))


        marketplace_installation = cls(
            id=id,
            listing_id=listing_id,
            listing_name=listing_name,
            listing_slug=listing_slug,
            installed_at=installed_at,
            listing_icon_url=listing_icon_url,
            version=version,
        )


        marketplace_installation.additional_properties = d
        return marketplace_installation

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
