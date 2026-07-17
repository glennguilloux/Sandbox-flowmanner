from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="BlueprintBudgetDefinition")


@_attrs_define
class BlueprintBudgetDefinition:
    """Budget constraints for a blueprint run.

    Attributes:
        max_cost_usd (float | Unset):  Default: 10.0.
        max_wall_time_seconds (int | Unset):  Default: 300.
        max_iterations (int | Unset):  Default: 100.
        max_depth (int | Unset):  Default: 5.
    """

    max_cost_usd: float | Unset = 10.0
    max_wall_time_seconds: int | Unset = 300
    max_iterations: int | Unset = 100
    max_depth: int | Unset = 5
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        max_cost_usd = self.max_cost_usd

        max_wall_time_seconds = self.max_wall_time_seconds

        max_iterations = self.max_iterations

        max_depth = self.max_depth

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if max_cost_usd is not UNSET:
            field_dict["max_cost_usd"] = max_cost_usd
        if max_wall_time_seconds is not UNSET:
            field_dict["max_wall_time_seconds"] = max_wall_time_seconds
        if max_iterations is not UNSET:
            field_dict["max_iterations"] = max_iterations
        if max_depth is not UNSET:
            field_dict["max_depth"] = max_depth

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        max_cost_usd = d.pop("max_cost_usd", UNSET)

        max_wall_time_seconds = d.pop("max_wall_time_seconds", UNSET)

        max_iterations = d.pop("max_iterations", UNSET)

        max_depth = d.pop("max_depth", UNSET)

        blueprint_budget_definition = cls(
            max_cost_usd=max_cost_usd,
            max_wall_time_seconds=max_wall_time_seconds,
            max_iterations=max_iterations,
            max_depth=max_depth,
        )

        blueprint_budget_definition.additional_properties = d
        return blueprint_budget_definition

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
