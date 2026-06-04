from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="TOTPVerifySetupResponse")


@_attrs_define
class TOTPVerifySetupResponse:
    """Response after successful 2FA setup.

    Attributes:
        backup_codes (list[str]):
        message (str | Unset):  Default: "2FA enabled successfully. Save your backup codes — they won't be shown
            again.".
    """

    backup_codes: list[str]
    message: str | Unset = "2FA enabled successfully. Save your backup codes — they won't be shown again."
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        backup_codes = self.backup_codes

        message = self.message

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "backup_codes": backup_codes,
            }
        )
        if message is not UNSET:
            field_dict["message"] = message

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        backup_codes = cast(list[str], d.pop("backup_codes"))

        message = d.pop("message", UNSET)

        totp_verify_setup_response = cls(
            backup_codes=backup_codes,
            message=message,
        )

        totp_verify_setup_response.additional_properties = d
        return totp_verify_setup_response

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
