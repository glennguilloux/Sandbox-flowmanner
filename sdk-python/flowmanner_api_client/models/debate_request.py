from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="DebateRequest")


@_attrs_define
class DebateRequest:
    """
    Attributes:
        topic (str):
        agent_a_id (str):
        agent_a_name (str):
        agent_b_id (str):
        agent_b_name (str):
        max_rounds (int | Unset):  Default: 2.
    """

    topic: str
    agent_a_id: str
    agent_a_name: str
    agent_b_id: str
    agent_b_name: str
    max_rounds: int | Unset = 2
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        topic = self.topic

        agent_a_id = self.agent_a_id

        agent_a_name = self.agent_a_name

        agent_b_id = self.agent_b_id

        agent_b_name = self.agent_b_name

        max_rounds = self.max_rounds

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "topic": topic,
                "agent_a_id": agent_a_id,
                "agent_a_name": agent_a_name,
                "agent_b_id": agent_b_id,
                "agent_b_name": agent_b_name,
            }
        )
        if max_rounds is not UNSET:
            field_dict["max_rounds"] = max_rounds

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        topic = d.pop("topic")

        agent_a_id = d.pop("agent_a_id")

        agent_a_name = d.pop("agent_a_name")

        agent_b_id = d.pop("agent_b_id")

        agent_b_name = d.pop("agent_b_name")

        max_rounds = d.pop("max_rounds", UNSET)

        debate_request = cls(
            topic=topic,
            agent_a_id=agent_a_id,
            agent_a_name=agent_a_name,
            agent_b_id=agent_b_id,
            agent_b_name=agent_b_name,
            max_rounds=max_rounds,
        )

        debate_request.additional_properties = d
        return debate_request

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
