from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..types import UNSET, Unset
from typing import cast

if TYPE_CHECKING:
  from ..models.node_group_create_config_type_0 import NodeGroupCreateConfigType0





T = TypeVar("T", bound="NodeGroupCreate")



@_attrs_define
class NodeGroupCreate:
    """ 
        Attributes:
            name (str):
            description (None | str | Unset):
            group_type (None | str | Unset):
            config (NodeGroupCreateConfigType0 | None | Unset):
     """

    name: str
    description: None | str | Unset = UNSET
    group_type: None | str | Unset = UNSET
    config: NodeGroupCreateConfigType0 | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        from ..models.node_group_create_config_type_0 import NodeGroupCreateConfigType0
        name = self.name

        description: None | str | Unset
        if isinstance(self.description, Unset):
            description = UNSET
        else:
            description = self.description

        group_type: None | str | Unset
        if isinstance(self.group_type, Unset):
            group_type = UNSET
        else:
            group_type = self.group_type

        config: dict[str, Any] | None | Unset
        if isinstance(self.config, Unset):
            config = UNSET
        elif isinstance(self.config, NodeGroupCreateConfigType0):
            config = self.config.to_dict()
        else:
            config = self.config


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "name": name,
        })
        if description is not UNSET:
            field_dict["description"] = description
        if group_type is not UNSET:
            field_dict["group_type"] = group_type
        if config is not UNSET:
            field_dict["config"] = config

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.node_group_create_config_type_0 import NodeGroupCreateConfigType0
        d = dict(src_dict)
        name = d.pop("name")

        def _parse_description(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        description = _parse_description(d.pop("description", UNSET))


        def _parse_group_type(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        group_type = _parse_group_type(d.pop("group_type", UNSET))


        def _parse_config(data: object) -> NodeGroupCreateConfigType0 | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                config_type_0 = NodeGroupCreateConfigType0.from_dict(data)



                return config_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(NodeGroupCreateConfigType0 | None | Unset, data)

        config = _parse_config(d.pop("config", UNSET))


        node_group_create = cls(
            name=name,
            description=description,
            group_type=group_type,
            config=config,
        )


        node_group_create.additional_properties = d
        return node_group_create

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
