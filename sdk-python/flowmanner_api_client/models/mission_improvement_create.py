from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define

from ..types import UNSET, Unset

T = TypeVar("T", bound="MissionImprovementCreate")


@_attrs_define
class MissionImprovementCreate:
    """
    Attributes:
        failure_type (str):
        failure_context (None | str | Unset):
    """

    failure_type: str
    failure_context: None | str | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        failure_type = self.failure_type

        failure_context: None | str | Unset
        if isinstance(self.failure_context, Unset):
            failure_context = UNSET
        else:
            failure_context = self.failure_context

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "failure_type": failure_type,
            }
        )
        if failure_context is not UNSET:
            field_dict["failure_context"] = failure_context

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        failure_type = d.pop("failure_type")

        def _parse_failure_context(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        failure_context = _parse_failure_context(d.pop("failure_context", UNSET))

        mission_improvement_create = cls(
            failure_type=failure_type,
            failure_context=failure_context,
        )

        return mission_improvement_create
