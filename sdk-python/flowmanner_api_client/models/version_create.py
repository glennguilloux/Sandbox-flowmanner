from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..types import UNSET, Unset
from typing import cast

if TYPE_CHECKING:
  from ..models.version_create_flow_data_type_0 import VersionCreateFlowDataType0





T = TypeVar("T", bound="VersionCreate")



@_attrs_define
class VersionCreate:
    """ 
        Attributes:
            change_summary (None | str | Unset):
            flow_data (None | Unset | VersionCreateFlowDataType0):
     """

    change_summary: None | str | Unset = UNSET
    flow_data: None | Unset | VersionCreateFlowDataType0 = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        from ..models.version_create_flow_data_type_0 import VersionCreateFlowDataType0
        change_summary: None | str | Unset
        if isinstance(self.change_summary, Unset):
            change_summary = UNSET
        else:
            change_summary = self.change_summary

        flow_data: dict[str, Any] | None | Unset
        if isinstance(self.flow_data, Unset):
            flow_data = UNSET
        elif isinstance(self.flow_data, VersionCreateFlowDataType0):
            flow_data = self.flow_data.to_dict()
        else:
            flow_data = self.flow_data


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
        })
        if change_summary is not UNSET:
            field_dict["change_summary"] = change_summary
        if flow_data is not UNSET:
            field_dict["flow_data"] = flow_data

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.version_create_flow_data_type_0 import VersionCreateFlowDataType0
        d = dict(src_dict)
        def _parse_change_summary(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        change_summary = _parse_change_summary(d.pop("change_summary", UNSET))


        def _parse_flow_data(data: object) -> None | Unset | VersionCreateFlowDataType0:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                flow_data_type_0 = VersionCreateFlowDataType0.from_dict(data)



                return flow_data_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | Unset | VersionCreateFlowDataType0, data)

        flow_data = _parse_flow_data(d.pop("flow_data", UNSET))


        version_create = cls(
            change_summary=change_summary,
            flow_data=flow_data,
        )


        version_create.additional_properties = d
        return version_create

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
