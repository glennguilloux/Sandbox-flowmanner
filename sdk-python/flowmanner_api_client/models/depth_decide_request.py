from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.depth_decide_request_risk import DepthDecideRequestRisk
from ..types import UNSET, Unset

T = TypeVar("T", bound="DepthDecideRequest")


@_attrs_define
class DepthDecideRequest:
    """Request body for the depth decision endpoint.

    Attributes:
        risk (DepthDecideRequestRisk): Risk level: low, medium, or high
        uncertainty (float): Uncertainty signal (0.0-1.0)
        budget_remaining_usd (float): Remaining budget in USD
        prior_failures (int | Unset): Number of prior failures Default: 0.
        tool_requires_approval (bool | Unset): Whether the tool requires HITL approval Default: False.
        retry_count (int | Unset): Number of retries attempted Default: 0.
        policy_override (bool | Unset): Bypass HITL for approval-requiring tools Default: False.
    """

    risk: DepthDecideRequestRisk
    uncertainty: float
    budget_remaining_usd: float
    prior_failures: int | Unset = 0
    tool_requires_approval: bool | Unset = False
    retry_count: int | Unset = 0
    policy_override: bool | Unset = False
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        risk = self.risk.value

        uncertainty = self.uncertainty

        budget_remaining_usd = self.budget_remaining_usd

        prior_failures = self.prior_failures

        tool_requires_approval = self.tool_requires_approval

        retry_count = self.retry_count

        policy_override = self.policy_override

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "risk": risk,
                "uncertainty": uncertainty,
                "budget_remaining_usd": budget_remaining_usd,
            }
        )
        if prior_failures is not UNSET:
            field_dict["prior_failures"] = prior_failures
        if tool_requires_approval is not UNSET:
            field_dict["tool_requires_approval"] = tool_requires_approval
        if retry_count is not UNSET:
            field_dict["retry_count"] = retry_count
        if policy_override is not UNSET:
            field_dict["policy_override"] = policy_override

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        risk = DepthDecideRequestRisk(d.pop("risk"))

        uncertainty = d.pop("uncertainty")

        budget_remaining_usd = d.pop("budget_remaining_usd")

        prior_failures = d.pop("prior_failures", UNSET)

        tool_requires_approval = d.pop("tool_requires_approval", UNSET)

        retry_count = d.pop("retry_count", UNSET)

        policy_override = d.pop("policy_override", UNSET)

        depth_decide_request = cls(
            risk=risk,
            uncertainty=uncertainty,
            budget_remaining_usd=budget_remaining_usd,
            prior_failures=prior_failures,
            tool_requires_approval=tool_requires_approval,
            retry_count=retry_count,
            policy_override=policy_override,
        )

        depth_decide_request.additional_properties = d
        return depth_decide_request

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
