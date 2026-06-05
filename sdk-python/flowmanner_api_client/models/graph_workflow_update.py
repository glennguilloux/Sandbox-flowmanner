from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.graph_workflow_update_graph_definition_type_0 import (
        GraphWorkflowUpdateGraphDefinitionType0,
    )


T = TypeVar("T", bound="GraphWorkflowUpdate")


@_attrs_define
class GraphWorkflowUpdate:
    """
    Attributes:
        name (None | str | Unset):
        description (None | str | Unset):
        graph_definition (GraphWorkflowUpdateGraphDefinitionType0 | None | Unset):
        status (None | str | Unset):
    """

    name: None | str | Unset = UNSET
    description: None | str | Unset = UNSET
    graph_definition: GraphWorkflowUpdateGraphDefinitionType0 | None | Unset = UNSET
    status: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.graph_workflow_update_graph_definition_type_0 import (
            GraphWorkflowUpdateGraphDefinitionType0,
        )

        name: None | str | Unset
        if isinstance(self.name, Unset):
            name = UNSET
        else:
            name = self.name

        description: None | str | Unset
        if isinstance(self.description, Unset):
            description = UNSET
        else:
            description = self.description

        graph_definition: dict[str, Any] | None | Unset
        if isinstance(self.graph_definition, Unset):
            graph_definition = UNSET
        elif isinstance(self.graph_definition, GraphWorkflowUpdateGraphDefinitionType0):
            graph_definition = self.graph_definition.to_dict()
        else:
            graph_definition = self.graph_definition

        status: None | str | Unset
        if isinstance(self.status, Unset):
            status = UNSET
        else:
            status = self.status

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if name is not UNSET:
            field_dict["name"] = name
        if description is not UNSET:
            field_dict["description"] = description
        if graph_definition is not UNSET:
            field_dict["graph_definition"] = graph_definition
        if status is not UNSET:
            field_dict["status"] = status

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.graph_workflow_update_graph_definition_type_0 import (
            GraphWorkflowUpdateGraphDefinitionType0,
        )

        d = dict(src_dict)

        def _parse_name(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        name = _parse_name(d.pop("name", UNSET))

        def _parse_description(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        description = _parse_description(d.pop("description", UNSET))

        def _parse_graph_definition(
            data: object,
        ) -> GraphWorkflowUpdateGraphDefinitionType0 | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                graph_definition_type_0 = (
                    GraphWorkflowUpdateGraphDefinitionType0.from_dict(data)
                )

                return graph_definition_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(GraphWorkflowUpdateGraphDefinitionType0 | None | Unset, data)

        graph_definition = _parse_graph_definition(d.pop("graph_definition", UNSET))

        def _parse_status(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        status = _parse_status(d.pop("status", UNSET))

        graph_workflow_update = cls(
            name=name,
            description=description,
            graph_definition=graph_definition,
            status=status,
        )

        graph_workflow_update.additional_properties = d
        return graph_workflow_update

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
