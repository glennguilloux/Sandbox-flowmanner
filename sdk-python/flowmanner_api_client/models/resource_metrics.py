from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from typing import cast

if TYPE_CHECKING:
  from ..models.resource_metrics_cpu import ResourceMetricsCpu
  from ..models.resource_metrics_disk import ResourceMetricsDisk
  from ..models.resource_metrics_memory import ResourceMetricsMemory





T = TypeVar("T", bound="ResourceMetrics")



@_attrs_define
class ResourceMetrics:
    """ 
        Attributes:
            cpu (ResourceMetricsCpu):
            memory (ResourceMetricsMemory):
            disk (ResourceMetricsDisk):
     """

    cpu: ResourceMetricsCpu
    memory: ResourceMetricsMemory
    disk: ResourceMetricsDisk
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        from ..models.resource_metrics_cpu import ResourceMetricsCpu
        from ..models.resource_metrics_disk import ResourceMetricsDisk
        from ..models.resource_metrics_memory import ResourceMetricsMemory
        cpu = self.cpu.to_dict()

        memory = self.memory.to_dict()

        disk = self.disk.to_dict()


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "cpu": cpu,
            "memory": memory,
            "disk": disk,
        })

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.resource_metrics_cpu import ResourceMetricsCpu
        from ..models.resource_metrics_disk import ResourceMetricsDisk
        from ..models.resource_metrics_memory import ResourceMetricsMemory
        d = dict(src_dict)
        cpu = ResourceMetricsCpu.from_dict(d.pop("cpu"))




        memory = ResourceMetricsMemory.from_dict(d.pop("memory"))




        disk = ResourceMetricsDisk.from_dict(d.pop("disk"))




        resource_metrics = cls(
            cpu=cpu,
            memory=memory,
            disk=disk,
        )


        resource_metrics.additional_properties = d
        return resource_metrics

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
