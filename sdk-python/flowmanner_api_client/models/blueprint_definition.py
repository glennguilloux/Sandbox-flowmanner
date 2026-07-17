from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.blueprint_budget_definition import BlueprintBudgetDefinition
    from ..models.blueprint_definition_config import BlueprintDefinitionConfig
    from ..models.blueprint_edge_definition import BlueprintEdgeDefinition
    from ..models.blueprint_node_definition import BlueprintNodeDefinition


T = TypeVar("T", bound="BlueprintDefinition")


@_attrs_define
class BlueprintDefinition:
    """The declarative part of a blueprint — stored in definition JSONB.

    This maps directly to the Workflow Pydantic model's static structure.
    At execution time, it's converted via blueprint_to_workflow().

        Attributes:
            blueprint_type (str | Unset):  Default: 'solo'.
            nodes (list[BlueprintNodeDefinition] | Unset):
            edges (list[BlueprintEdgeDefinition] | Unset):
            budget (BlueprintBudgetDefinition | Unset): Budget constraints for a blueprint run.
            config (BlueprintDefinitionConfig | Unset):
    """

    blueprint_type: str | Unset = "solo"
    nodes: list[BlueprintNodeDefinition] | Unset = UNSET
    edges: list[BlueprintEdgeDefinition] | Unset = UNSET
    budget: BlueprintBudgetDefinition | Unset = UNSET
    config: BlueprintDefinitionConfig | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        blueprint_type = self.blueprint_type

        nodes: list[dict[str, Any]] | Unset = UNSET
        if not isinstance(self.nodes, Unset):
            nodes = []
            for nodes_item_data in self.nodes:
                nodes_item = nodes_item_data.to_dict()
                nodes.append(nodes_item)

        edges: list[dict[str, Any]] | Unset = UNSET
        if not isinstance(self.edges, Unset):
            edges = []
            for edges_item_data in self.edges:
                edges_item = edges_item_data.to_dict()
                edges.append(edges_item)

        budget: dict[str, Any] | Unset = UNSET
        if not isinstance(self.budget, Unset):
            budget = self.budget.to_dict()

        config: dict[str, Any] | Unset = UNSET
        if not isinstance(self.config, Unset):
            config = self.config.to_dict()

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if blueprint_type is not UNSET:
            field_dict["blueprint_type"] = blueprint_type
        if nodes is not UNSET:
            field_dict["nodes"] = nodes
        if edges is not UNSET:
            field_dict["edges"] = edges
        if budget is not UNSET:
            field_dict["budget"] = budget
        if config is not UNSET:
            field_dict["config"] = config

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.blueprint_budget_definition import BlueprintBudgetDefinition
        from ..models.blueprint_definition_config import BlueprintDefinitionConfig
        from ..models.blueprint_edge_definition import BlueprintEdgeDefinition
        from ..models.blueprint_node_definition import BlueprintNodeDefinition

        d = dict(src_dict)
        blueprint_type = d.pop("blueprint_type", UNSET)

        _nodes = d.pop("nodes", UNSET)
        nodes: list[BlueprintNodeDefinition] | Unset = UNSET
        if _nodes is not UNSET:
            nodes = []
            for nodes_item_data in _nodes:
                nodes_item = BlueprintNodeDefinition.from_dict(nodes_item_data)

                nodes.append(nodes_item)

        _edges = d.pop("edges", UNSET)
        edges: list[BlueprintEdgeDefinition] | Unset = UNSET
        if _edges is not UNSET:
            edges = []
            for edges_item_data in _edges:
                edges_item = BlueprintEdgeDefinition.from_dict(edges_item_data)

                edges.append(edges_item)

        _budget = d.pop("budget", UNSET)
        budget: BlueprintBudgetDefinition | Unset
        if isinstance(_budget, Unset):
            budget = UNSET
        else:
            budget = BlueprintBudgetDefinition.from_dict(_budget)

        _config = d.pop("config", UNSET)
        config: BlueprintDefinitionConfig | Unset
        if isinstance(_config, Unset):
            config = UNSET
        else:
            config = BlueprintDefinitionConfig.from_dict(_config)

        blueprint_definition = cls(
            blueprint_type=blueprint_type,
            nodes=nodes,
            edges=edges,
            budget=budget,
            config=config,
        )

        blueprint_definition.additional_properties = d
        return blueprint_definition

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
