from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.blueprint_budget_definition import BlueprintBudgetDefinition
    from ..models.run_create_input_data_type_0 import RunCreateInputDataType0


T = TypeVar("T", bound="RunCreate")


@_attrs_define
class RunCreate:
    """Create a run from a blueprint.

    Attributes:
        input_data (None | RunCreateInputDataType0 | Unset):
        budget_override (BlueprintBudgetDefinition | None | Unset):
    """

    input_data: None | RunCreateInputDataType0 | Unset = UNSET
    budget_override: BlueprintBudgetDefinition | None | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        from ..models.blueprint_budget_definition import BlueprintBudgetDefinition
        from ..models.run_create_input_data_type_0 import RunCreateInputDataType0

        input_data: dict[str, Any] | None | Unset
        if isinstance(self.input_data, Unset):
            input_data = UNSET
        elif isinstance(self.input_data, RunCreateInputDataType0):
            input_data = self.input_data.to_dict()
        else:
            input_data = self.input_data

        budget_override: dict[str, Any] | None | Unset
        if isinstance(self.budget_override, Unset):
            budget_override = UNSET
        elif isinstance(self.budget_override, BlueprintBudgetDefinition):
            budget_override = self.budget_override.to_dict()
        else:
            budget_override = self.budget_override

        field_dict: dict[str, Any] = {}

        field_dict.update({})
        if input_data is not UNSET:
            field_dict["input_data"] = input_data
        if budget_override is not UNSET:
            field_dict["budget_override"] = budget_override

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.blueprint_budget_definition import BlueprintBudgetDefinition
        from ..models.run_create_input_data_type_0 import RunCreateInputDataType0

        d = dict(src_dict)

        def _parse_input_data(data: object) -> None | RunCreateInputDataType0 | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                input_data_type_0 = RunCreateInputDataType0.from_dict(data)

                return input_data_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | RunCreateInputDataType0 | Unset, data)

        input_data = _parse_input_data(d.pop("input_data", UNSET))

        def _parse_budget_override(data: object) -> BlueprintBudgetDefinition | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                budget_override_type_0 = BlueprintBudgetDefinition.from_dict(data)

                return budget_override_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(BlueprintBudgetDefinition | None | Unset, data)

        budget_override = _parse_budget_override(d.pop("budget_override", UNSET))

        run_create = cls(
            input_data=input_data,
            budget_override=budget_override,
        )

        return run_create
