from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.node_type_response_inputs import NodeTypeResponseInputs
    from ..models.node_type_response_outputs import NodeTypeResponseOutputs


T = TypeVar("T", bound="NodeTypeResponse")


@_attrs_define
class NodeTypeResponse:
    """
    Attributes:
        node_type_id (str):
        plugin_name (str):
        permissions (list[str] | Unset):
        label (None | str | Unset):
        category (None | str | Unset):
        description (None | str | Unset):
        icon (None | str | Unset):
        color (None | str | Unset):
        inputs (NodeTypeResponseInputs | Unset):
        outputs (NodeTypeResponseOutputs | Unset):
    """

    node_type_id: str
    plugin_name: str
    permissions: list[str] | Unset = UNSET
    label: None | str | Unset = UNSET
    category: None | str | Unset = UNSET
    description: None | str | Unset = UNSET
    icon: None | str | Unset = UNSET
    color: None | str | Unset = UNSET
    inputs: NodeTypeResponseInputs | Unset = UNSET
    outputs: NodeTypeResponseOutputs | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        node_type_id = self.node_type_id

        plugin_name = self.plugin_name

        permissions: list[str] | Unset = UNSET
        if not isinstance(self.permissions, Unset):
            permissions = self.permissions

        label: None | str | Unset
        if isinstance(self.label, Unset):
            label = UNSET
        else:
            label = self.label

        category: None | str | Unset
        if isinstance(self.category, Unset):
            category = UNSET
        else:
            category = self.category

        description: None | str | Unset
        if isinstance(self.description, Unset):
            description = UNSET
        else:
            description = self.description

        icon: None | str | Unset
        if isinstance(self.icon, Unset):
            icon = UNSET
        else:
            icon = self.icon

        color: None | str | Unset
        if isinstance(self.color, Unset):
            color = UNSET
        else:
            color = self.color

        inputs: dict[str, Any] | Unset = UNSET
        if not isinstance(self.inputs, Unset):
            inputs = self.inputs.to_dict()

        outputs: dict[str, Any] | Unset = UNSET
        if not isinstance(self.outputs, Unset):
            outputs = self.outputs.to_dict()

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "node_type_id": node_type_id,
                "plugin_name": plugin_name,
            }
        )
        if permissions is not UNSET:
            field_dict["permissions"] = permissions
        if label is not UNSET:
            field_dict["label"] = label
        if category is not UNSET:
            field_dict["category"] = category
        if description is not UNSET:
            field_dict["description"] = description
        if icon is not UNSET:
            field_dict["icon"] = icon
        if color is not UNSET:
            field_dict["color"] = color
        if inputs is not UNSET:
            field_dict["inputs"] = inputs
        if outputs is not UNSET:
            field_dict["outputs"] = outputs

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.node_type_response_inputs import NodeTypeResponseInputs
        from ..models.node_type_response_outputs import NodeTypeResponseOutputs

        d = dict(src_dict)
        node_type_id = d.pop("node_type_id")

        plugin_name = d.pop("plugin_name")

        permissions = cast(list[str], d.pop("permissions", UNSET))

        def _parse_label(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        label = _parse_label(d.pop("label", UNSET))

        def _parse_category(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        category = _parse_category(d.pop("category", UNSET))

        def _parse_description(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        description = _parse_description(d.pop("description", UNSET))

        def _parse_icon(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        icon = _parse_icon(d.pop("icon", UNSET))

        def _parse_color(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        color = _parse_color(d.pop("color", UNSET))

        _inputs = d.pop("inputs", UNSET)
        inputs: NodeTypeResponseInputs | Unset
        if isinstance(_inputs, Unset):
            inputs = UNSET
        else:
            inputs = NodeTypeResponseInputs.from_dict(_inputs)

        _outputs = d.pop("outputs", UNSET)
        outputs: NodeTypeResponseOutputs | Unset
        if isinstance(_outputs, Unset):
            outputs = UNSET
        else:
            outputs = NodeTypeResponseOutputs.from_dict(_outputs)

        node_type_response = cls(
            node_type_id=node_type_id,
            plugin_name=plugin_name,
            permissions=permissions,
            label=label,
            category=category,
            description=description,
            icon=icon,
            color=color,
            inputs=inputs,
            outputs=outputs,
        )

        node_type_response.additional_properties = d
        return node_type_response

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
