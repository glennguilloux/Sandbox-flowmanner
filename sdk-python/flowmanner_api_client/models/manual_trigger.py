from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Literal, TypeVar, cast

from attrs import define as _attrs_define

T = TypeVar("T", bound="ManualTrigger")


@_attrs_define
class ManualTrigger:
    """Manual / on-demand trigger (no schedule).

    Attributes:
        type_ (Literal['manual']):
    """

    type_: Literal["manual"]

    def to_dict(self) -> dict[str, Any]:
        type_ = self.type_

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "type": type_,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        type_ = cast(Literal["manual"], d.pop("type"))
        if type_ != "manual":
            raise ValueError(f"type must match const 'manual', got '{type_}'")

        manual_trigger = cls(
            type_=type_,
        )

        return manual_trigger
