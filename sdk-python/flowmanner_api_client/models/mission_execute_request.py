from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define

from ..types import UNSET, Unset

T = TypeVar("T", bound="MissionExecuteRequest")


@_attrs_define
class MissionExecuteRequest:
    """
    Attributes:
        model_preference (None | str | Unset):
        selected_plan_id (None | str | Unset):
    """

    model_preference: None | str | Unset = UNSET
    selected_plan_id: None | str | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        model_preference: None | str | Unset
        if isinstance(self.model_preference, Unset):
            model_preference = UNSET
        else:
            model_preference = self.model_preference

        selected_plan_id: None | str | Unset
        if isinstance(self.selected_plan_id, Unset):
            selected_plan_id = UNSET
        else:
            selected_plan_id = self.selected_plan_id

        field_dict: dict[str, Any] = {}

        field_dict.update({})
        if model_preference is not UNSET:
            field_dict["model_preference"] = model_preference
        if selected_plan_id is not UNSET:
            field_dict["selected_plan_id"] = selected_plan_id

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)

        def _parse_model_preference(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        model_preference = _parse_model_preference(d.pop("model_preference", UNSET))

        def _parse_selected_plan_id(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        selected_plan_id = _parse_selected_plan_id(d.pop("selected_plan_id", UNSET))

        mission_execute_request = cls(
            model_preference=model_preference,
            selected_plan_id=selected_plan_id,
        )

        return mission_execute_request
