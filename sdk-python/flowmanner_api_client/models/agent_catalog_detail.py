from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

T = TypeVar("T", bound="AgentCatalogDetail")


@_attrs_define
class AgentCatalogDetail:
    """
    Attributes:
        id (str):
        name (str):
        description (None | str):
        agent_type (str):
        system_prompt (None | str):
        emoji (str):
        color (str):
        vibe (str):
        division (str):
        slug (str):
    """

    id: str
    name: str
    description: None | str
    agent_type: str
    system_prompt: None | str
    emoji: str
    color: str
    vibe: str
    division: str
    slug: str
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        id = self.id

        name = self.name

        description: None | str
        description = self.description

        agent_type = self.agent_type

        system_prompt: None | str
        system_prompt = self.system_prompt

        emoji = self.emoji

        color = self.color

        vibe = self.vibe

        division = self.division

        slug = self.slug

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "id": id,
                "name": name,
                "description": description,
                "agent_type": agent_type,
                "system_prompt": system_prompt,
                "emoji": emoji,
                "color": color,
                "vibe": vibe,
                "division": division,
                "slug": slug,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        id = d.pop("id")

        name = d.pop("name")

        def _parse_description(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        description = _parse_description(d.pop("description"))

        agent_type = d.pop("agent_type")

        def _parse_system_prompt(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        system_prompt = _parse_system_prompt(d.pop("system_prompt"))

        emoji = d.pop("emoji")

        color = d.pop("color")

        vibe = d.pop("vibe")

        division = d.pop("division")

        slug = d.pop("slug")

        agent_catalog_detail = cls(
            id=id,
            name=name,
            description=description,
            agent_type=agent_type,
            system_prompt=system_prompt,
            emoji=emoji,
            color=color,
            vibe=vibe,
            division=division,
            slug=slug,
        )

        agent_catalog_detail.additional_properties = d
        return agent_catalog_detail

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
