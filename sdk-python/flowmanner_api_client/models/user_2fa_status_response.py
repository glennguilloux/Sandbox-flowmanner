from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="User2FAStatusResponse")


@_attrs_define
class User2FAStatusResponse:
    """2FA status for current user.

    Attributes:
        totp_enabled (bool):
        backup_codes_count (int):
        totp_verified_at (None | str | Unset):
    """

    totp_enabled: bool
    backup_codes_count: int
    totp_verified_at: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        totp_enabled = self.totp_enabled

        backup_codes_count = self.backup_codes_count

        totp_verified_at: None | str | Unset
        if isinstance(self.totp_verified_at, Unset):
            totp_verified_at = UNSET
        else:
            totp_verified_at = self.totp_verified_at

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "totp_enabled": totp_enabled,
                "backup_codes_count": backup_codes_count,
            }
        )
        if totp_verified_at is not UNSET:
            field_dict["totp_verified_at"] = totp_verified_at

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        totp_enabled = d.pop("totp_enabled")

        backup_codes_count = d.pop("backup_codes_count")

        def _parse_totp_verified_at(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        totp_verified_at = _parse_totp_verified_at(d.pop("totp_verified_at", UNSET))

        user_2fa_status_response = cls(
            totp_enabled=totp_enabled,
            backup_codes_count=backup_codes_count,
            totp_verified_at=totp_verified_at,
        )

        user_2fa_status_response.additional_properties = d
        return user_2fa_status_response

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
