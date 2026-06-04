from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..types import UNSET, Unset






T = TypeVar("T", bound="TestResponse")



@_attrs_define
class TestResponse:
    """ 
        Attributes:
            success (bool):
            content (str | Unset):  Default: ''.
            model (str | Unset):  Default: ''.
            token_count (int | Unset):  Default: 0.
            error (str | Unset):  Default: ''.
     """

    success: bool
    content: str | Unset = ''
    model: str | Unset = ''
    token_count: int | Unset = 0
    error: str | Unset = ''
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        success = self.success

        content = self.content

        model = self.model

        token_count = self.token_count

        error = self.error


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "success": success,
        })
        if content is not UNSET:
            field_dict["content"] = content
        if model is not UNSET:
            field_dict["model"] = model
        if token_count is not UNSET:
            field_dict["token_count"] = token_count
        if error is not UNSET:
            field_dict["error"] = error

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        success = d.pop("success")

        content = d.pop("content", UNSET)

        model = d.pop("model", UNSET)

        token_count = d.pop("token_count", UNSET)

        error = d.pop("error", UNSET)

        test_response = cls(
            success=success,
            content=content,
            model=model,
            token_count=token_count,
            error=error,
        )


        test_response.additional_properties = d
        return test_response

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
