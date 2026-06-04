from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset







T = TypeVar("T", bound="OIDCLoginResponse")



@_attrs_define
class OIDCLoginResponse:
    """ 
        Attributes:
            authorization_url (str):
            state (str):
            nonce (str):
            code_verifier (str):
     """

    authorization_url: str
    state: str
    nonce: str
    code_verifier: str
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        authorization_url = self.authorization_url

        state = self.state

        nonce = self.nonce

        code_verifier = self.code_verifier


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "authorization_url": authorization_url,
            "state": state,
            "nonce": nonce,
            "code_verifier": code_verifier,
        })

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        authorization_url = d.pop("authorization_url")

        state = d.pop("state")

        nonce = d.pop("nonce")

        code_verifier = d.pop("code_verifier")

        oidc_login_response = cls(
            authorization_url=authorization_url,
            state=state,
            nonce=nonce,
            code_verifier=code_verifier,
        )


        oidc_login_response.additional_properties = d
        return oidc_login_response

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
