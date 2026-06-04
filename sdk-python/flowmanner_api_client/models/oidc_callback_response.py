from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..types import UNSET, Unset






T = TypeVar("T", bound="OIDCCallbackResponse")



@_attrs_define
class OIDCCallbackResponse:
    """ 
        Attributes:
            access_token (str):
            refresh_token (str):
            user_id (int):
            email (str):
            username (str):
            token_type (str | Unset):  Default: 'bearer'.
     """

    access_token: str
    refresh_token: str
    user_id: int
    email: str
    username: str
    token_type: str | Unset = 'bearer'
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        access_token = self.access_token

        refresh_token = self.refresh_token

        user_id = self.user_id

        email = self.email

        username = self.username

        token_type = self.token_type


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "access_token": access_token,
            "refresh_token": refresh_token,
            "user_id": user_id,
            "email": email,
            "username": username,
        })
        if token_type is not UNSET:
            field_dict["token_type"] = token_type

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        access_token = d.pop("access_token")

        refresh_token = d.pop("refresh_token")

        user_id = d.pop("user_id")

        email = d.pop("email")

        username = d.pop("username")

        token_type = d.pop("token_type", UNSET)

        oidc_callback_response = cls(
            access_token=access_token,
            refresh_token=refresh_token,
            user_id=user_id,
            email=email,
            username=username,
            token_type=token_type,
        )


        oidc_callback_response.additional_properties = d
        return oidc_callback_response

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
