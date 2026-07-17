from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="ShareResponse2")


@_attrs_define
class ShareResponse2:
    """
    Attributes:
        success (bool):
        session_token (None | str | Unset):
        share_url (None | str | Unset):
        error (None | str | Unset):
    """

    success: bool
    session_token: None | str | Unset = UNSET
    share_url: None | str | Unset = UNSET
    error: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        success = self.success

        session_token: None | str | Unset
        if isinstance(self.session_token, Unset):
            session_token = UNSET
        else:
            session_token = self.session_token

        share_url: None | str | Unset
        if isinstance(self.share_url, Unset):
            share_url = UNSET
        else:
            share_url = self.share_url

        error: None | str | Unset
        if isinstance(self.error, Unset):
            error = UNSET
        else:
            error = self.error

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "success": success,
            }
        )
        if session_token is not UNSET:
            field_dict["session_token"] = session_token
        if share_url is not UNSET:
            field_dict["share_url"] = share_url
        if error is not UNSET:
            field_dict["error"] = error

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        success = d.pop("success")

        def _parse_session_token(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        session_token = _parse_session_token(d.pop("session_token", UNSET))

        def _parse_share_url(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        share_url = _parse_share_url(d.pop("share_url", UNSET))

        def _parse_error(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        error = _parse_error(d.pop("error", UNSET))

        share_response_2 = cls(
            success=success,
            session_token=session_token,
            share_url=share_url,
            error=error,
        )

        share_response_2.additional_properties = d
        return share_response_2

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
