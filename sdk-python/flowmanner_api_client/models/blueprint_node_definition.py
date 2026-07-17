from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.blueprint_node_definition_config import BlueprintNodeDefinitionConfig


T = TypeVar("T", bound="BlueprintNodeDefinition")


@_attrs_define
class BlueprintNodeDefinition:
    """Declarative node definition — no runtime fields.

    Attributes:
        id (str):
        type_ (str):
        title (str | Unset):  Default: ''.
        description (str | Unset):  Default: ''.
        config (BlueprintNodeDefinitionConfig | Unset):
        dependencies (list[str] | Unset):
        assigned_model (None | str | Unset):
        assigned_agent_id (None | str | Unset):
        max_retries (int | Unset):  Default: 3.
        fallback_strategy (str | Unset):  Default: 'human_escalate'.
    """

    id: str
    type_: str
    title: str | Unset = ""
    description: str | Unset = ""
    config: BlueprintNodeDefinitionConfig | Unset = UNSET
    dependencies: list[str] | Unset = UNSET
    assigned_model: None | str | Unset = UNSET
    assigned_agent_id: None | str | Unset = UNSET
    max_retries: int | Unset = 3
    fallback_strategy: str | Unset = "human_escalate"
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        id = self.id

        type_ = self.type_

        title = self.title

        description = self.description

        config: dict[str, Any] | Unset = UNSET
        if not isinstance(self.config, Unset):
            config = self.config.to_dict()

        dependencies: list[str] | Unset = UNSET
        if not isinstance(self.dependencies, Unset):
            dependencies = self.dependencies

        assigned_model: None | str | Unset
        if isinstance(self.assigned_model, Unset):
            assigned_model = UNSET
        else:
            assigned_model = self.assigned_model

        assigned_agent_id: None | str | Unset
        if isinstance(self.assigned_agent_id, Unset):
            assigned_agent_id = UNSET
        else:
            assigned_agent_id = self.assigned_agent_id

        max_retries = self.max_retries

        fallback_strategy = self.fallback_strategy

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "id": id,
                "type": type_,
            }
        )
        if title is not UNSET:
            field_dict["title"] = title
        if description is not UNSET:
            field_dict["description"] = description
        if config is not UNSET:
            field_dict["config"] = config
        if dependencies is not UNSET:
            field_dict["dependencies"] = dependencies
        if assigned_model is not UNSET:
            field_dict["assigned_model"] = assigned_model
        if assigned_agent_id is not UNSET:
            field_dict["assigned_agent_id"] = assigned_agent_id
        if max_retries is not UNSET:
            field_dict["max_retries"] = max_retries
        if fallback_strategy is not UNSET:
            field_dict["fallback_strategy"] = fallback_strategy

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.blueprint_node_definition_config import BlueprintNodeDefinitionConfig

        d = dict(src_dict)
        id = d.pop("id")

        type_ = d.pop("type")

        title = d.pop("title", UNSET)

        description = d.pop("description", UNSET)

        _config = d.pop("config", UNSET)
        config: BlueprintNodeDefinitionConfig | Unset
        if isinstance(_config, Unset):
            config = UNSET
        else:
            config = BlueprintNodeDefinitionConfig.from_dict(_config)

        dependencies = cast(list[str], d.pop("dependencies", UNSET))

        def _parse_assigned_model(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        assigned_model = _parse_assigned_model(d.pop("assigned_model", UNSET))

        def _parse_assigned_agent_id(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        assigned_agent_id = _parse_assigned_agent_id(d.pop("assigned_agent_id", UNSET))

        max_retries = d.pop("max_retries", UNSET)

        fallback_strategy = d.pop("fallback_strategy", UNSET)

        blueprint_node_definition = cls(
            id=id,
            type_=type_,
            title=title,
            description=description,
            config=config,
            dependencies=dependencies,
            assigned_model=assigned_model,
            assigned_agent_id=assigned_agent_id,
            max_retries=max_retries,
            fallback_strategy=fallback_strategy,
        )

        blueprint_node_definition.additional_properties = d
        return blueprint_node_definition

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
