from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="TypeRequest")


@_attrs_define
class TypeRequest:
    """
    Attributes:
        ref (str):
        text (str):
        submit (bool | Unset):  Default: False.
    """

    ref: str
    text: str
    submit: bool | Unset = False
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        ref = self.ref

        text = self.text

        submit = self.submit

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "ref": ref,
                "text": text,
            }
        )
        if submit is not UNSET:
            field_dict["submit"] = submit

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        ref = d.pop("ref")

        text = d.pop("text")

        submit = d.pop("submit", UNSET)

        type_request = cls(
            ref=ref,
            text=text,
            submit=submit,
        )

        type_request.additional_properties = d
        return type_request

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
