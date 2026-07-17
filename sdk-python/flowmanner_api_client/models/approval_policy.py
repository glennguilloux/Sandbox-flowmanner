from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="ApprovalPolicy")


@_attrs_define
class ApprovalPolicy:
    """
    Attributes:
        require_approval_for_deployments (bool | Unset):  Default: False.
        require_approval_for_destructive_actions (bool | Unset):  Default: True.
        require_approval_above_cost_usd (float | Unset):  Default: 5.0.
        auto_approve_low_risk (bool | Unset):  Default: True.
    """

    require_approval_for_deployments: bool | Unset = False
    require_approval_for_destructive_actions: bool | Unset = True
    require_approval_above_cost_usd: float | Unset = 5.0
    auto_approve_low_risk: bool | Unset = True
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        require_approval_for_deployments = self.require_approval_for_deployments

        require_approval_for_destructive_actions = self.require_approval_for_destructive_actions

        require_approval_above_cost_usd = self.require_approval_above_cost_usd

        auto_approve_low_risk = self.auto_approve_low_risk

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if require_approval_for_deployments is not UNSET:
            field_dict["require_approval_for_deployments"] = require_approval_for_deployments
        if require_approval_for_destructive_actions is not UNSET:
            field_dict["require_approval_for_destructive_actions"] = require_approval_for_destructive_actions
        if require_approval_above_cost_usd is not UNSET:
            field_dict["require_approval_above_cost_usd"] = require_approval_above_cost_usd
        if auto_approve_low_risk is not UNSET:
            field_dict["auto_approve_low_risk"] = auto_approve_low_risk

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        require_approval_for_deployments = d.pop("require_approval_for_deployments", UNSET)

        require_approval_for_destructive_actions = d.pop("require_approval_for_destructive_actions", UNSET)

        require_approval_above_cost_usd = d.pop("require_approval_above_cost_usd", UNSET)

        auto_approve_low_risk = d.pop("auto_approve_low_risk", UNSET)

        approval_policy = cls(
            require_approval_for_deployments=require_approval_for_deployments,
            require_approval_for_destructive_actions=require_approval_for_destructive_actions,
            require_approval_above_cost_usd=require_approval_above_cost_usd,
            auto_approve_low_risk=auto_approve_low_risk,
        )

        approval_policy.additional_properties = d
        return approval_policy

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
