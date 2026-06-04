from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from typing import cast

if TYPE_CHECKING:
  from ..models.system_health_components import SystemHealthComponents





T = TypeVar("T", bound="SystemHealth")



@_attrs_define
class SystemHealth:
    """ 
        Attributes:
            status (str):
            components (SystemHealthComponents):
     """

    status: str
    components: SystemHealthComponents
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        from ..models.system_health_components import SystemHealthComponents
        status = self.status

        components = self.components.to_dict()


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "status": status,
            "components": components,
        })

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.system_health_components import SystemHealthComponents
        d = dict(src_dict)
        status = d.pop("status")

        components = SystemHealthComponents.from_dict(d.pop("components"))




        system_health = cls(
            status=status,
            components=components,
        )


        system_health.additional_properties = d
        return system_health

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
