from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..types import UNSET, Unset
from typing import cast

if TYPE_CHECKING:
  from ..models.agent_update_config_type_0 import AgentUpdateConfigType0





T = TypeVar("T", bound="AgentUpdate")



@_attrs_define
class AgentUpdate:
    """ 
        Attributes:
            name (None | str | Unset):
            description (None | str | Unset):
            system_prompt (None | str | Unset):
            model_preference (None | str | Unset):
            config (AgentUpdateConfigType0 | None | Unset):
     """

    name: None | str | Unset = UNSET
    description: None | str | Unset = UNSET
    system_prompt: None | str | Unset = UNSET
    model_preference: None | str | Unset = UNSET
    config: AgentUpdateConfigType0 | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        from ..models.agent_update_config_type_0 import AgentUpdateConfigType0
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
        elif isinstance(self.config, AgentUpdateConfigType0):
            config = self.config.to_dict()
        else:
            config = self.config


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
        })
        if name is not UNSET:
            field_dict["name"] = name
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
        from ..models.agent_update_config_type_0 import AgentUpdateConfigType0
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


        def _parse_config(data: object) -> AgentUpdateConfigType0 | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                config_type_0 = AgentUpdateConfigType0.from_dict(data)



                return config_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(AgentUpdateConfigType0 | None | Unset, data)

        config = _parse_config(d.pop("config", UNSET))


        agent_update = cls(
            name=name,
            description=description,
            system_prompt=system_prompt,
            model_preference=model_preference,
            config=config,
        )


        agent_update.additional_properties = d
        return agent_update

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
