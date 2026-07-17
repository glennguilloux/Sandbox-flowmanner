from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="PlaygroundSandboxResponse")


@_attrs_define
class PlaygroundSandboxResponse:
    """
    Attributes:
        sandbox_id (str):
        session_token (str):
        status (str):
        template (str):
        expires_at (str):
        preview_url (None | str | Unset):
        claimed (bool | Unset):  Default: False.
    """

    sandbox_id: str
    session_token: str
    status: str
    template: str
    expires_at: str
    preview_url: None | str | Unset = UNSET
    claimed: bool | Unset = False
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        sandbox_id = self.sandbox_id

        session_token = self.session_token

        status = self.status

        template = self.template

        expires_at = self.expires_at

        preview_url: None | str | Unset
        if isinstance(self.preview_url, Unset):
            preview_url = UNSET
        else:
            preview_url = self.preview_url

        claimed = self.claimed

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "sandbox_id": sandbox_id,
                "session_token": session_token,
                "status": status,
                "template": template,
                "expires_at": expires_at,
            }
        )
        if preview_url is not UNSET:
            field_dict["preview_url"] = preview_url
        if claimed is not UNSET:
            field_dict["claimed"] = claimed

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        sandbox_id = d.pop("sandbox_id")

        session_token = d.pop("session_token")

        status = d.pop("status")

        template = d.pop("template")

        expires_at = d.pop("expires_at")

        def _parse_preview_url(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        preview_url = _parse_preview_url(d.pop("preview_url", UNSET))

        claimed = d.pop("claimed", UNSET)

        playground_sandbox_response = cls(
            sandbox_id=sandbox_id,
            session_token=session_token,
            status=status,
            template=template,
            expires_at=expires_at,
            preview_url=preview_url,
            claimed=claimed,
        )

        playground_sandbox_response.additional_properties = d
        return playground_sandbox_response

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
