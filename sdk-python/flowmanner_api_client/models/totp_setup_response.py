from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset







T = TypeVar("T", bound="TOTPSetupResponse")



@_attrs_define
class TOTPSetupResponse:
    """ Response for 2FA setup initiation.

        Attributes:
            secret (str):
            provisioning_uri (str):
            qr_code_base64 (str):
     """

    secret: str
    provisioning_uri: str
    qr_code_base64: str
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        secret = self.secret

        provisioning_uri = self.provisioning_uri

        qr_code_base64 = self.qr_code_base64


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "secret": secret,
            "provisioning_uri": provisioning_uri,
            "qr_code_base64": qr_code_base64,
        })

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        secret = d.pop("secret")

        provisioning_uri = d.pop("provisioning_uri")

        qr_code_base64 = d.pop("qr_code_base64")

        totp_setup_response = cls(
            secret=secret,
            provisioning_uri=provisioning_uri,
            qr_code_base64=qr_code_base64,
        )


        totp_setup_response.additional_properties = d
        return totp_setup_response

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
