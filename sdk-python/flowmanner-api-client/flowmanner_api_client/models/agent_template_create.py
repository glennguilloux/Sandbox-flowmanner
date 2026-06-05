from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.agent_template_create_config_data_type_0 import (
        AgentTemplateCreateConfigDataType0,
    )


T = TypeVar("T", bound="AgentTemplateCreate")


@_attrs_define
class AgentTemplateCreate:
    """
    Attributes:
        name (str):
        description (None | str | Unset):
        system_prompt (None | str | Unset):
        agent_type (str | Unset):  Default: 'domain'.
        config_data (AgentTemplateCreateConfigDataType0 | None | Unset):
        is_active (bool | Unset):  Default: True.
    """

    name: str
    description: None | str | Unset = UNSET
    system_prompt: None | str | Unset = UNSET
    agent_type: str | Unset = "domain"
    config_data: AgentTemplateCreateConfigDataType0 | None | Unset = UNSET
    is_active: bool | Unset = True
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.agent_template_create_config_data_type_0 import (
            AgentTemplateCreateConfigDataType0,
        )

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

        agent_type = self.agent_type

        config_data: dict[str, Any] | None | Unset
        if isinstance(self.config_data, Unset):
            config_data = UNSET
        elif isinstance(self.config_data, AgentTemplateCreateConfigDataType0):
            config_data = self.config_data.to_dict()
        else:
            config_data = self.config_data

        is_active = self.is_active

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
        if agent_type is not UNSET:
            field_dict["agent_type"] = agent_type
        if config_data is not UNSET:
            field_dict["config_data"] = config_data
        if is_active is not UNSET:
            field_dict["is_active"] = is_active

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.agent_template_create_config_data_type_0 import (
            AgentTemplateCreateConfigDataType0,
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

        def _parse_system_prompt(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        system_prompt = _parse_system_prompt(d.pop("system_prompt", UNSET))

        agent_type = d.pop("agent_type", UNSET)

        def _parse_config_data(
            data: object,
        ) -> AgentTemplateCreateConfigDataType0 | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                config_data_type_0 = AgentTemplateCreateConfigDataType0.from_dict(data)

                return config_data_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(AgentTemplateCreateConfigDataType0 | None | Unset, data)

        config_data = _parse_config_data(d.pop("config_data", UNSET))

        is_active = d.pop("is_active", UNSET)

        agent_template_create = cls(
            name=name,
            description=description,
            system_prompt=system_prompt,
            agent_type=agent_type,
            config_data=config_data,
            is_active=is_active,
        )

        agent_template_create.additional_properties = d
        return agent_template_create

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
