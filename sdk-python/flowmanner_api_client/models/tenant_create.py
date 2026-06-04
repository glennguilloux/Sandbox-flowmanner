from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..types import UNSET, Unset
from typing import cast






T = TypeVar("T", bound="TenantCreate")



@_attrs_define
class TenantCreate:
    """ 
        Attributes:
            name (str):
            slug (str):
            description (None | str | Unset):
            max_members (int | Unset):  Default: 10.
            max_missions_per_day (int | Unset):  Default: 100.
     """

    name: str
    slug: str
    description: None | str | Unset = UNSET
    max_members: int | Unset = 10
    max_missions_per_day: int | Unset = 100
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        name = self.name

        slug = self.slug

        description: None | str | Unset
        if isinstance(self.description, Unset):
            description = UNSET
        else:
            description = self.description

        max_members = self.max_members

        max_missions_per_day = self.max_missions_per_day


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "name": name,
            "slug": slug,
        })
        if description is not UNSET:
            field_dict["description"] = description
        if max_members is not UNSET:
            field_dict["max_members"] = max_members
        if max_missions_per_day is not UNSET:
            field_dict["max_missions_per_day"] = max_missions_per_day

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        name = d.pop("name")

        slug = d.pop("slug")

        def _parse_description(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        description = _parse_description(d.pop("description", UNSET))


        max_members = d.pop("max_members", UNSET)

        max_missions_per_day = d.pop("max_missions_per_day", UNSET)

        tenant_create = cls(
            name=name,
            slug=slug,
            description=description,
            max_members=max_members,
            max_missions_per_day=max_missions_per_day,
        )


        tenant_create.additional_properties = d
        return tenant_create

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
