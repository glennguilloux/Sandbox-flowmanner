from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..types import UNSET, Unset






T = TypeVar("T", bound="SynthesizeRequest")



@_attrs_define
class SynthesizeRequest:
    """ 
        Attributes:
            mode (str | Unset):  Default: 'auto'.
            include_task_analysis (bool | Unset):  Default: True.
            include_patterns (bool | Unset):  Default: True.
     """

    mode: str | Unset = 'auto'
    include_task_analysis: bool | Unset = True
    include_patterns: bool | Unset = True
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        mode = self.mode

        include_task_analysis = self.include_task_analysis

        include_patterns = self.include_patterns


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
        })
        if mode is not UNSET:
            field_dict["mode"] = mode
        if include_task_analysis is not UNSET:
            field_dict["include_task_analysis"] = include_task_analysis
        if include_patterns is not UNSET:
            field_dict["include_patterns"] = include_patterns

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        mode = d.pop("mode", UNSET)

        include_task_analysis = d.pop("include_task_analysis", UNSET)

        include_patterns = d.pop("include_patterns", UNSET)

        synthesize_request = cls(
            mode=mode,
            include_task_analysis=include_task_analysis,
            include_patterns=include_patterns,
        )


        synthesize_request.additional_properties = d
        return synthesize_request

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
