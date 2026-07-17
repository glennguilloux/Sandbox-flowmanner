from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Literal, TypeVar, cast

from attrs import define as _attrs_define

from ..types import UNSET, Unset

T = TypeVar("T", bound="CronTrigger")


@_attrs_define
class CronTrigger:
    """Cron-style recurring trigger.

    Attributes:
        type_ (Literal['cron']):
        expression (str):
        timezone (str | Unset):  Default: 'UTC'.
    """

    type_: Literal["cron"]
    expression: str
    timezone: str | Unset = "UTC"

    def to_dict(self) -> dict[str, Any]:
        type_ = self.type_

        expression = self.expression

        timezone = self.timezone

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "type": type_,
                "expression": expression,
            }
        )
        if timezone is not UNSET:
            field_dict["timezone"] = timezone

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        type_ = cast(Literal["cron"], d.pop("type"))
        if type_ != "cron":
            raise ValueError(f"type must match const 'cron', got '{type_}'")

        expression = d.pop("expression")

        timezone = d.pop("timezone", UNSET)

        cron_trigger = cls(
            type_=type_,
            expression=expression,
            timezone=timezone,
        )

        return cron_trigger
