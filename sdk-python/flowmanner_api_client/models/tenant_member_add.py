from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..types import UNSET, Unset






T = TypeVar("T", bound="TenantMemberAdd")



@_attrs_define
class TenantMemberAdd:
    """ 
        Attributes:
            email (str):
            role (str | Unset):  Default: 'member'.
            can_create_missions (bool | Unset):  Default: True.
            can_manage_members (bool | Unset):  Default: False.
            can_view_billing (bool | Unset):  Default: False.
     """

    email: str
    role: str | Unset = 'member'
    can_create_missions: bool | Unset = True
    can_manage_members: bool | Unset = False
    can_view_billing: bool | Unset = False
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        email = self.email

        role = self.role

        can_create_missions = self.can_create_missions

        can_manage_members = self.can_manage_members

        can_view_billing = self.can_view_billing


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "email": email,
        })
        if role is not UNSET:
            field_dict["role"] = role
        if can_create_missions is not UNSET:
            field_dict["can_create_missions"] = can_create_missions
        if can_manage_members is not UNSET:
            field_dict["can_manage_members"] = can_manage_members
        if can_view_billing is not UNSET:
            field_dict["can_view_billing"] = can_view_billing

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        email = d.pop("email")

        role = d.pop("role", UNSET)

        can_create_missions = d.pop("can_create_missions", UNSET)

        can_manage_members = d.pop("can_manage_members", UNSET)

        can_view_billing = d.pop("can_view_billing", UNSET)

        tenant_member_add = cls(
            email=email,
            role=role,
            can_create_missions=can_create_missions,
            can_manage_members=can_manage_members,
            can_view_billing=can_view_billing,
        )


        tenant_member_add.additional_properties = d
        return tenant_member_add

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
