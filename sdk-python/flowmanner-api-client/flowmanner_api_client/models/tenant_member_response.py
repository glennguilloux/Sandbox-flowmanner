from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

T = TypeVar("T", bound="TenantMemberResponse")


@_attrs_define
class TenantMemberResponse:
    """
    Attributes:
        id (int):
        user_email (str):
        role (str):
        can_create_missions (bool):
        can_manage_members (bool):
        can_view_billing (bool):
        is_active (bool):
    """

    id: int
    user_email: str
    role: str
    can_create_missions: bool
    can_manage_members: bool
    can_view_billing: bool
    is_active: bool
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        id = self.id

        user_email = self.user_email

        role = self.role

        can_create_missions = self.can_create_missions

        can_manage_members = self.can_manage_members

        can_view_billing = self.can_view_billing

        is_active = self.is_active

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "id": id,
                "user_email": user_email,
                "role": role,
                "can_create_missions": can_create_missions,
                "can_manage_members": can_manage_members,
                "can_view_billing": can_view_billing,
                "is_active": is_active,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        id = d.pop("id")

        user_email = d.pop("user_email")

        role = d.pop("role")

        can_create_missions = d.pop("can_create_missions")

        can_manage_members = d.pop("can_manage_members")

        can_view_billing = d.pop("can_view_billing")

        is_active = d.pop("is_active")

        tenant_member_response = cls(
            id=id,
            user_email=user_email,
            role=role,
            can_create_missions=can_create_missions,
            can_manage_members=can_manage_members,
            can_view_billing=can_view_billing,
            is_active=is_active,
        )

        tenant_member_response.additional_properties = d
        return tenant_member_response

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
