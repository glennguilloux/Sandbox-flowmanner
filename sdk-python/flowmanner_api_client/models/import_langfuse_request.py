from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..types import UNSET, Unset
from typing import cast

if TYPE_CHECKING:
  from ..models.import_langfuse_request_traces_item import ImportLangfuseRequestTracesItem





T = TypeVar("T", bound="ImportLangfuseRequest")



@_attrs_define
class ImportLangfuseRequest:
    """ 
        Attributes:
            dataset_name (str):
            traces (list[ImportLangfuseRequestTracesItem]):
            category (str | Unset):  Default: 'imported'.
     """

    dataset_name: str
    traces: list[ImportLangfuseRequestTracesItem]
    category: str | Unset = 'imported'
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        from ..models.import_langfuse_request_traces_item import ImportLangfuseRequestTracesItem
        dataset_name = self.dataset_name

        traces = []
        for traces_item_data in self.traces:
            traces_item = traces_item_data.to_dict()
            traces.append(traces_item)



        category = self.category


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "dataset_name": dataset_name,
            "traces": traces,
        })
        if category is not UNSET:
            field_dict["category"] = category

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.import_langfuse_request_traces_item import ImportLangfuseRequestTracesItem
        d = dict(src_dict)
        dataset_name = d.pop("dataset_name")

        traces = []
        _traces = d.pop("traces")
        for traces_item_data in (_traces):
            traces_item = ImportLangfuseRequestTracesItem.from_dict(traces_item_data)



            traces.append(traces_item)


        category = d.pop("category", UNSET)

        import_langfuse_request = cls(
            dataset_name=dataset_name,
            traces=traces,
            category=category,
        )


        import_langfuse_request.additional_properties = d
        return import_langfuse_request

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
