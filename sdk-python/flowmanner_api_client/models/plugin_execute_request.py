from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.plugin_execute_request_config import PluginExecuteRequestConfig
    from ..models.plugin_execute_request_inputs import PluginExecuteRequestInputs


T = TypeVar("T", bound="PluginExecuteRequest")


@_attrs_define
class PluginExecuteRequest:
    """
    Attributes:
        node_type_id (str):
        inputs (PluginExecuteRequestInputs | Unset):
        config (PluginExecuteRequestConfig | Unset):
    """

    node_type_id: str
    inputs: PluginExecuteRequestInputs | Unset = UNSET
    config: PluginExecuteRequestConfig | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        node_type_id = self.node_type_id

        inputs: dict[str, Any] | Unset = UNSET
        if not isinstance(self.inputs, Unset):
            inputs = self.inputs.to_dict()

        config: dict[str, Any] | Unset = UNSET
        if not isinstance(self.config, Unset):
            config = self.config.to_dict()

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "node_type_id": node_type_id,
            }
        )
        if inputs is not UNSET:
            field_dict["inputs"] = inputs
        if config is not UNSET:
            field_dict["config"] = config

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.plugin_execute_request_config import PluginExecuteRequestConfig
        from ..models.plugin_execute_request_inputs import PluginExecuteRequestInputs

        d = dict(src_dict)
        node_type_id = d.pop("node_type_id")

        _inputs = d.pop("inputs", UNSET)
        inputs: PluginExecuteRequestInputs | Unset
        if isinstance(_inputs, Unset):
            inputs = UNSET
        else:
            inputs = PluginExecuteRequestInputs.from_dict(_inputs)

        _config = d.pop("config", UNSET)
        config: PluginExecuteRequestConfig | Unset
        if isinstance(_config, Unset):
            config = UNSET
        else:
            config = PluginExecuteRequestConfig.from_dict(_config)

        plugin_execute_request = cls(
            node_type_id=node_type_id,
            inputs=inputs,
            config=config,
        )

        plugin_execute_request.additional_properties = d
        return plugin_execute_request

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
