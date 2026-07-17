from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

T = TypeVar("T", bound="DepthDecisionResponse")


@_attrs_define
class DepthDecisionResponse:
    """Response body for a depth decision.

    Attributes:
        level (str):
        reason (str):
        escalate_to_hitl (bool):
        hitl_reason (None | str):
        policy_version (str):
        estimated_reflection_iterations (int):
    """

    level: str
    reason: str
    escalate_to_hitl: bool
    hitl_reason: None | str
    policy_version: str
    estimated_reflection_iterations: int
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        level = self.level

        reason = self.reason

        escalate_to_hitl = self.escalate_to_hitl

        hitl_reason: None | str
        hitl_reason = self.hitl_reason

        policy_version = self.policy_version

        estimated_reflection_iterations = self.estimated_reflection_iterations

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "level": level,
                "reason": reason,
                "escalate_to_hitl": escalate_to_hitl,
                "hitl_reason": hitl_reason,
                "policy_version": policy_version,
                "estimated_reflection_iterations": estimated_reflection_iterations,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        level = d.pop("level")

        reason = d.pop("reason")

        escalate_to_hitl = d.pop("escalate_to_hitl")

        def _parse_hitl_reason(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        hitl_reason = _parse_hitl_reason(d.pop("hitl_reason"))

        policy_version = d.pop("policy_version")

        estimated_reflection_iterations = d.pop("estimated_reflection_iterations")

        depth_decision_response = cls(
            level=level,
            reason=reason,
            escalate_to_hitl=escalate_to_hitl,
            hitl_reason=hitl_reason,
            policy_version=policy_version,
            estimated_reflection_iterations=estimated_reflection_iterations,
        )

        depth_decision_response.additional_properties = d
        return depth_decision_response

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
