from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from typing import cast






T = TypeVar("T", bound="TenantResponse")



@_attrs_define
class TenantResponse:
    """ 
        Attributes:
            id (int):
            name (str):
            slug (str):
            description (None | str):
            max_members (int):
            max_missions_per_day (int):
            subscription_tier (None | str):
            member_count (int):
            is_active (bool):
     """

    id: int
    name: str
    slug: str
    description: None | str
    max_members: int
    max_missions_per_day: int
    subscription_tier: None | str
    member_count: int
    is_active: bool
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        id = self.id

        name = self.name

        slug = self.slug

        description: None | str
        description = self.description

        max_members = self.max_members

        max_missions_per_day = self.max_missions_per_day

        subscription_tier: None | str
        subscription_tier = self.subscription_tier

        member_count = self.member_count

        is_active = self.is_active


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "id": id,
            "name": name,
            "slug": slug,
            "description": description,
            "max_members": max_members,
            "max_missions_per_day": max_missions_per_day,
            "subscription_tier": subscription_tier,
            "member_count": member_count,
            "is_active": is_active,
        })

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        id = d.pop("id")

        name = d.pop("name")

        slug = d.pop("slug")

        def _parse_description(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        description = _parse_description(d.pop("description"))


        max_members = d.pop("max_members")

        max_missions_per_day = d.pop("max_missions_per_day")

        def _parse_subscription_tier(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        subscription_tier = _parse_subscription_tier(d.pop("subscription_tier"))


        member_count = d.pop("member_count")

        is_active = d.pop("is_active")

        tenant_response = cls(
            id=id,
            name=name,
            slug=slug,
            description=description,
            max_members=max_members,
            max_missions_per_day=max_missions_per_day,
            subscription_tier=subscription_tier,
            member_count=member_count,
            is_active=is_active,
        )


        tenant_response.additional_properties = d
        return tenant_response

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
