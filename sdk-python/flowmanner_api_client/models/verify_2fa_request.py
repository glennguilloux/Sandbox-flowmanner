from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

T = TypeVar("T", bound="Verify2FARequest")


@_attrs_define
class Verify2FARequest:
    """POST /auth/sessions/verify — verify 2FA after login challenge.

    Attributes:
        temp_token (str):
        code (str):
    """

    temp_token: str
    code: str
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        temp_token = self.temp_token

        code = self.code

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "temp_token": temp_token,
                "code": code,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        temp_token = d.pop("temp_token")

        code = d.pop("code")

        verify_2fa_request = cls(
            temp_token=temp_token,
            code=code,
        )

        verify_2fa_request.additional_properties = d
        return verify_2fa_request

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
