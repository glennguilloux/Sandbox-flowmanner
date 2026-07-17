from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="LoginRequest")


@_attrs_define
class LoginRequest:
    """POST /auth/sessions — create a new session (login).

    When provider='credentials': password is required.
    When provider='oidc': password is ignored (OAuth/SSO flow uses OIDCLoginRequest
    for the authorization URL, and the callback handles token exchange server-side).
    For the initial OIDC login, use POST /auth/oidc/{provider}/login instead.

        Attributes:
            login (str): Email or username
            password (str):
            provider (str | Unset): 'credentials' | 'oidc' Default: 'credentials'.
    """

    login: str
    password: str
    provider: str | Unset = "credentials"
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        login = self.login

        password = self.password

        provider = self.provider

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "login": login,
                "password": password,
            }
        )
        if provider is not UNSET:
            field_dict["provider"] = provider

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        login = d.pop("login")

        password = d.pop("password")

        provider = d.pop("provider", UNSET)

        login_request = cls(
            login=login,
            password=password,
            provider=provider,
        )

        login_request.additional_properties = d
        return login_request

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
