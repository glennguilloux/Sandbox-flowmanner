from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="CircuitBreakerDefaults")


@_attrs_define
class CircuitBreakerDefaults:
    """
    Attributes:
        max_llm_calls (int | Unset):  Default: 100.
        max_cost_usd (float | Unset):  Default: 10.0.
        max_duration_seconds (int | Unset):  Default: 3600.
        max_tool_calls (int | Unset):  Default: 200.
        destructive_actions_require_approval (bool | Unset):  Default: True.
    """

    max_llm_calls: int | Unset = 100
    max_cost_usd: float | Unset = 10.0
    max_duration_seconds: int | Unset = 3600
    max_tool_calls: int | Unset = 200
    destructive_actions_require_approval: bool | Unset = True
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        max_llm_calls = self.max_llm_calls

        max_cost_usd = self.max_cost_usd

        max_duration_seconds = self.max_duration_seconds

        max_tool_calls = self.max_tool_calls

        destructive_actions_require_approval = self.destructive_actions_require_approval

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if max_llm_calls is not UNSET:
            field_dict["max_llm_calls"] = max_llm_calls
        if max_cost_usd is not UNSET:
            field_dict["max_cost_usd"] = max_cost_usd
        if max_duration_seconds is not UNSET:
            field_dict["max_duration_seconds"] = max_duration_seconds
        if max_tool_calls is not UNSET:
            field_dict["max_tool_calls"] = max_tool_calls
        if destructive_actions_require_approval is not UNSET:
            field_dict["destructive_actions_require_approval"] = destructive_actions_require_approval

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        max_llm_calls = d.pop("max_llm_calls", UNSET)

        max_cost_usd = d.pop("max_cost_usd", UNSET)

        max_duration_seconds = d.pop("max_duration_seconds", UNSET)

        max_tool_calls = d.pop("max_tool_calls", UNSET)

        destructive_actions_require_approval = d.pop("destructive_actions_require_approval", UNSET)

        circuit_breaker_defaults = cls(
            max_llm_calls=max_llm_calls,
            max_cost_usd=max_cost_usd,
            max_duration_seconds=max_duration_seconds,
            max_tool_calls=max_tool_calls,
            destructive_actions_require_approval=destructive_actions_require_approval,
        )

        circuit_breaker_defaults.additional_properties = d
        return circuit_breaker_defaults

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
