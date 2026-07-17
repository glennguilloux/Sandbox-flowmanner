from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="SandboxPreviewResponse")


@_attrs_define
class SandboxPreviewResponse:
    """Preview info for a running sandbox.

    Attributes:
        sandbox_id (str):
        status (str):
        preview_url (None | str | Unset):
        preview_status (None | str | Unset):
    """

    sandbox_id: str
    status: str
    preview_url: None | str | Unset = UNSET
    preview_status: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        sandbox_id = self.sandbox_id

        status = self.status

        preview_url: None | str | Unset
        if isinstance(self.preview_url, Unset):
            preview_url = UNSET
        else:
            preview_url = self.preview_url

        preview_status: None | str | Unset
        if isinstance(self.preview_status, Unset):
            preview_status = UNSET
        else:
            preview_status = self.preview_status

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "sandbox_id": sandbox_id,
                "status": status,
            }
        )
        if preview_url is not UNSET:
            field_dict["preview_url"] = preview_url
        if preview_status is not UNSET:
            field_dict["preview_status"] = preview_status

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        sandbox_id = d.pop("sandbox_id")

        status = d.pop("status")

        def _parse_preview_url(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        preview_url = _parse_preview_url(d.pop("preview_url", UNSET))

        def _parse_preview_status(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        preview_status = _parse_preview_status(d.pop("preview_status", UNSET))

        sandbox_preview_response = cls(
            sandbox_id=sandbox_id,
            status=status,
            preview_url=preview_url,
            preview_status=preview_status,
        )

        sandbox_preview_response.additional_properties = d
        return sandbox_preview_response

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
