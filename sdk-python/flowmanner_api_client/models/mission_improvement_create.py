from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..types import UNSET, Unset
from typing import cast






T = TypeVar("T", bound="MissionImprovementCreate")



@_attrs_define
class MissionImprovementCreate:
    """ 
        Attributes:
            failure_type (str):
            failure_context (None | str | Unset):
     """

    failure_type: str
    failure_context: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        failure_type = self.failure_type

        failure_context: None | str | Unset
        if isinstance(self.failure_context, Unset):
            failure_context = UNSET
        else:
            failure_context = self.failure_context


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "failure_type": failure_type,
        })
        if failure_context is not UNSET:
            field_dict["failure_context"] = failure_context

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        failure_type = d.pop("failure_type")

        def _parse_failure_context(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        failure_context = _parse_failure_context(d.pop("failure_context", UNSET))


        mission_improvement_create = cls(
            failure_type=failure_type,
            failure_context=failure_context,
        )


        mission_improvement_create.additional_properties = d
        return mission_improvement_create

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
