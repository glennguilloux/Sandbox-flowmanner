from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="CircuitBreakerUpdate")


@_attrs_define
class CircuitBreakerUpdate:
    """
    Attributes:
        max_llm_calls (int | None | Unset):
        max_cost_usd (float | None | Unset):
        max_duration_seconds (int | None | Unset):
        max_tool_calls (int | None | Unset):
        destructive_actions_require_approval (bool | None | Unset):
        destructive_actions (list[str] | None | Unset):
    """

    max_llm_calls: int | None | Unset = UNSET
    max_cost_usd: float | None | Unset = UNSET
    max_duration_seconds: int | None | Unset = UNSET
    max_tool_calls: int | None | Unset = UNSET
    destructive_actions_require_approval: bool | None | Unset = UNSET
    destructive_actions: list[str] | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        max_llm_calls: int | None | Unset
        if isinstance(self.max_llm_calls, Unset):
            max_llm_calls = UNSET
        else:
            max_llm_calls = self.max_llm_calls

        max_cost_usd: float | None | Unset
        if isinstance(self.max_cost_usd, Unset):
            max_cost_usd = UNSET
        else:
            max_cost_usd = self.max_cost_usd

        max_duration_seconds: int | None | Unset
        if isinstance(self.max_duration_seconds, Unset):
            max_duration_seconds = UNSET
        else:
            max_duration_seconds = self.max_duration_seconds

        max_tool_calls: int | None | Unset
        if isinstance(self.max_tool_calls, Unset):
            max_tool_calls = UNSET
        else:
            max_tool_calls = self.max_tool_calls

        destructive_actions_require_approval: bool | None | Unset
        if isinstance(self.destructive_actions_require_approval, Unset):
            destructive_actions_require_approval = UNSET
        else:
            destructive_actions_require_approval = self.destructive_actions_require_approval

        destructive_actions: list[str] | None | Unset
        if isinstance(self.destructive_actions, Unset):
            destructive_actions = UNSET
        elif isinstance(self.destructive_actions, list):
            destructive_actions = self.destructive_actions

        else:
            destructive_actions = self.destructive_actions

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
        if destructive_actions is not UNSET:
            field_dict["destructive_actions"] = destructive_actions

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)

        def _parse_max_llm_calls(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        max_llm_calls = _parse_max_llm_calls(d.pop("max_llm_calls", UNSET))

        def _parse_max_cost_usd(data: object) -> float | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(float | None | Unset, data)

        max_cost_usd = _parse_max_cost_usd(d.pop("max_cost_usd", UNSET))

        def _parse_max_duration_seconds(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        max_duration_seconds = _parse_max_duration_seconds(d.pop("max_duration_seconds", UNSET))

        def _parse_max_tool_calls(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        max_tool_calls = _parse_max_tool_calls(d.pop("max_tool_calls", UNSET))

        def _parse_destructive_actions_require_approval(data: object) -> bool | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(bool | None | Unset, data)

        destructive_actions_require_approval = _parse_destructive_actions_require_approval(
            d.pop("destructive_actions_require_approval", UNSET)
        )

        def _parse_destructive_actions(data: object) -> list[str] | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, list):
                    raise TypeError()
                destructive_actions_type_0 = cast(list[str], data)

                return destructive_actions_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(list[str] | None | Unset, data)

        destructive_actions = _parse_destructive_actions(d.pop("destructive_actions", UNSET))

        circuit_breaker_update = cls(
            max_llm_calls=max_llm_calls,
            max_cost_usd=max_cost_usd,
            max_duration_seconds=max_duration_seconds,
            max_tool_calls=max_tool_calls,
            destructive_actions_require_approval=destructive_actions_require_approval,
            destructive_actions=destructive_actions,
        )

        circuit_breaker_update.additional_properties = d
        return circuit_breaker_update

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
