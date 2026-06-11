from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.graph_workflow_create_graph_definition_type_0 import (
        GraphWorkflowCreateGraphDefinitionType0,
    )


T = TypeVar("T", bound="GraphWorkflowCreate")


@_attrs_define
class GraphWorkflowCreate:
    """
    Attributes:
        name (str):
        description (None | str | Unset):
        graph_definition (GraphWorkflowCreateGraphDefinitionType0 | None | Unset):
    """

    name: str
    description: None | str | Unset = UNSET
    graph_definition: GraphWorkflowCreateGraphDefinitionType0 | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.graph_workflow_create_graph_definition_type_0 import (
            GraphWorkflowCreateGraphDefinitionType0,
        )

        name = self.name

        description: None | str | Unset
        if isinstance(self.description, Unset):
            description = UNSET
        else:
            description = self.description

        graph_definition: dict[str, Any] | None | Unset
        if isinstance(self.graph_definition, Unset):
            graph_definition = UNSET
        elif isinstance(self.graph_definition, GraphWorkflowCreateGraphDefinitionType0):
            graph_definition = self.graph_definition.to_dict()
        else:
            graph_definition = self.graph_definition

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "name": name,
            }
        )
        if description is not UNSET:
            field_dict["description"] = description
        if graph_definition is not UNSET:
            field_dict["graph_definition"] = graph_definition

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.graph_workflow_create_graph_definition_type_0 import (
            GraphWorkflowCreateGraphDefinitionType0,
        )

        d = dict(src_dict)
        name = d.pop("name")

        def _parse_description(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        description = _parse_description(d.pop("description", UNSET))

        def _parse_graph_definition(
            data: object,
        ) -> GraphWorkflowCreateGraphDefinitionType0 | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                graph_definition_type_0 = GraphWorkflowCreateGraphDefinitionType0.from_dict(data)

                return graph_definition_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(GraphWorkflowCreateGraphDefinitionType0 | None | Unset, data)

        graph_definition = _parse_graph_definition(d.pop("graph_definition", UNSET))

        graph_workflow_create = cls(
            name=name,
            description=description,
            graph_definition=graph_definition,
        )

        graph_workflow_create.additional_properties = d
        return graph_workflow_create

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
