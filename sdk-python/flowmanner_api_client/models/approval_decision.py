from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="ApprovalDecision")


@_attrs_define
class ApprovalDecision:
    """
    Attributes:
        decision (str):
        tool_index (int | None | Unset):
    """

    decision: str
    tool_index: int | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        decision = self.decision

        tool_index: int | None | Unset
        if isinstance(self.tool_index, Unset):
            tool_index = UNSET
        else:
            tool_index = self.tool_index

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "decision": decision,
            }
        )
        if tool_index is not UNSET:
            field_dict["tool_index"] = tool_index

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        decision = d.pop("decision")

        def _parse_tool_index(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        tool_index = _parse_tool_index(d.pop("tool_index", UNSET))

        approval_decision = cls(
            decision=decision,
            tool_index=tool_index,
        )

        approval_decision.additional_properties = d
        return approval_decision

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
