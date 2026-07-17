from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="ClaimResponse")


@_attrs_define
class ClaimResponse:
    """
    Attributes:
        sandbox_id (str):
        claimed (bool | Unset):  Default: True.
        message (str | Unset):  Default: 'Sandbox claimed successfully'.
    """

    sandbox_id: str
    claimed: bool | Unset = True
    message: str | Unset = "Sandbox claimed successfully"
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        sandbox_id = self.sandbox_id

        claimed = self.claimed

        message = self.message

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "sandbox_id": sandbox_id,
            }
        )
        if claimed is not UNSET:
            field_dict["claimed"] = claimed
        if message is not UNSET:
            field_dict["message"] = message

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        sandbox_id = d.pop("sandbox_id")

        claimed = d.pop("claimed", UNSET)

        message = d.pop("message", UNSET)

        claim_response = cls(
            sandbox_id=sandbox_id,
            claimed=claimed,
            message=message,
        )

        claim_response.additional_properties = d
        return claim_response

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
