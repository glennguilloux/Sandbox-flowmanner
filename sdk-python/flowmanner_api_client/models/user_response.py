from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="UserResponse")


@_attrs_define
class UserResponse:
    """
    Attributes:
        id (int):
        email (str):
        full_name (None | str):
        role (str):
        is_admin (bool):
        is_active (bool):
        created_at (datetime.datetime):
        username (None | str | Unset):
        avatar_url (None | str | Unset):
    """

    id: int
    email: str
    full_name: None | str
    role: str
    is_admin: bool
    is_active: bool
    created_at: datetime.datetime
    username: None | str | Unset = UNSET
    avatar_url: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        id = self.id

        email = self.email

        full_name: None | str
        full_name = self.full_name

        role = self.role

        is_admin = self.is_admin

        is_active = self.is_active

        created_at = self.created_at.isoformat()

        username: None | str | Unset
        if isinstance(self.username, Unset):
            username = UNSET
        else:
            username = self.username

        avatar_url: None | str | Unset
        if isinstance(self.avatar_url, Unset):
            avatar_url = UNSET
        else:
            avatar_url = self.avatar_url

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "id": id,
                "email": email,
                "full_name": full_name,
                "role": role,
                "is_admin": is_admin,
                "is_active": is_active,
                "created_at": created_at,
            }
        )
        if username is not UNSET:
            field_dict["username"] = username
        if avatar_url is not UNSET:
            field_dict["avatar_url"] = avatar_url

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        id = d.pop("id")

        email = d.pop("email")

        def _parse_full_name(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        full_name = _parse_full_name(d.pop("full_name"))

        role = d.pop("role")

        is_admin = d.pop("is_admin")

        is_active = d.pop("is_active")

        created_at = datetime.datetime.fromisoformat(d.pop("created_at"))

        def _parse_username(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        username = _parse_username(d.pop("username", UNSET))

        def _parse_avatar_url(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        avatar_url = _parse_avatar_url(d.pop("avatar_url", UNSET))

        user_response = cls(
            id=id,
            email=email,
            full_name=full_name,
            role=role,
            is_admin=is_admin,
            is_active=is_active,
            created_at=created_at,
            username=username,
            avatar_url=avatar_url,
        )

        user_response.additional_properties = d
        return user_response

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
