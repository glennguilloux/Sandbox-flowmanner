from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="CodeExecuteRequest")


@_attrs_define
class CodeExecuteRequest:
    """Request to execute a code cell.

    Attributes:
        code (str):
        language (str | Unset):  Default: 'python'.
        timeout_seconds (int | Unset):  Default: 30.
    """

    code: str
    language: str | Unset = "python"
    timeout_seconds: int | Unset = 30
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        code = self.code

        language = self.language

        timeout_seconds = self.timeout_seconds

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "code": code,
            }
        )
        if language is not UNSET:
            field_dict["language"] = language
        if timeout_seconds is not UNSET:
            field_dict["timeout_seconds"] = timeout_seconds

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        code = d.pop("code")

        language = d.pop("language", UNSET)

        timeout_seconds = d.pop("timeout_seconds", UNSET)

        code_execute_request = cls(
            code=code,
            language=language,
            timeout_seconds=timeout_seconds,
        )

        code_execute_request.additional_properties = d
        return code_execute_request

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
