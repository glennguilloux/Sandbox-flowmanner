from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.agent_create_config_type_0 import AgentCreateConfigType0


T = TypeVar("T", bound="AgentCreate")


@_attrs_define
class AgentCreate:
    """
    Attributes:
        name (str):
        description (None | str | Unset):
        system_prompt (None | str | Unset):
        model_preference (None | str | Unset):
        config (AgentCreateConfigType0 | None | Unset):
    """

    name: str
    description: None | str | Unset = UNSET
    system_prompt: None | str | Unset = UNSET
    model_preference: None | str | Unset = UNSET
    config: AgentCreateConfigType0 | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.agent_create_config_type_0 import AgentCreateConfigType0

        name = self.name

        description: None | str | Unset
        if isinstance(self.description, Unset):
            description = UNSET
        else:
            description = self.description

        system_prompt: None | str | Unset
        if isinstance(self.system_prompt, Unset):
            system_prompt = UNSET
        else:
            system_prompt = self.system_prompt

        model_preference: None | str | Unset
        if isinstance(self.model_preference, Unset):
            model_preference = UNSET
        else:
            model_preference = self.model_preference

        config: dict[str, Any] | None | Unset
        if isinstance(self.config, Unset):
            config = UNSET
        elif isinstance(self.config, AgentCreateConfigType0):
            config = self.config.to_dict()
        else:
            config = self.config

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "name": name,
            }
        )
        if description is not UNSET:
            field_dict["description"] = description
        if system_prompt is not UNSET:
            field_dict["system_prompt"] = system_prompt
        if model_preference is not UNSET:
            field_dict["model_preference"] = model_preference
        if config is not UNSET:
            field_dict["config"] = config

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.agent_create_config_type_0 import AgentCreateConfigType0

        d = dict(src_dict)
        name = d.pop("name")

        def _parse_description(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        description = _parse_description(d.pop("description", UNSET))

        def _parse_system_prompt(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        system_prompt = _parse_system_prompt(d.pop("system_prompt", UNSET))

        def _parse_model_preference(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        model_preference = _parse_model_preference(d.pop("model_preference", UNSET))

        def _parse_config(data: object) -> AgentCreateConfigType0 | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                config_type_0 = AgentCreateConfigType0.from_dict(data)

                return config_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(AgentCreateConfigType0 | None | Unset, data)

        config = _parse_config(d.pop("config", UNSET))

        agent_create = cls(
            name=name,
            description=description,
            system_prompt=system_prompt,
            model_preference=model_preference,
            config=config,
        )

        agent_create.additional_properties = d
        return agent_create

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
