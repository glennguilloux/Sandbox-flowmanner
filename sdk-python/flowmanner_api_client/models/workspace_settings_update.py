from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.approval_policy import ApprovalPolicy
    from ..models.circuit_breaker_defaults import CircuitBreakerDefaults


T = TypeVar("T", bound="WorkspaceSettingsUpdate")


@_attrs_define
class WorkspaceSettingsUpdate:
    """
    Attributes:
        circuit_breaker_defaults (CircuitBreakerDefaults | None | Unset):
        approval_policies (ApprovalPolicy | None | Unset):
    """

    circuit_breaker_defaults: CircuitBreakerDefaults | None | Unset = UNSET
    approval_policies: ApprovalPolicy | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.approval_policy import ApprovalPolicy
        from ..models.circuit_breaker_defaults import CircuitBreakerDefaults

        circuit_breaker_defaults: dict[str, Any] | None | Unset
        if isinstance(self.circuit_breaker_defaults, Unset):
            circuit_breaker_defaults = UNSET
        elif isinstance(self.circuit_breaker_defaults, CircuitBreakerDefaults):
            circuit_breaker_defaults = self.circuit_breaker_defaults.to_dict()
        else:
            circuit_breaker_defaults = self.circuit_breaker_defaults

        approval_policies: dict[str, Any] | None | Unset
        if isinstance(self.approval_policies, Unset):
            approval_policies = UNSET
        elif isinstance(self.approval_policies, ApprovalPolicy):
            approval_policies = self.approval_policies.to_dict()
        else:
            approval_policies = self.approval_policies

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if circuit_breaker_defaults is not UNSET:
            field_dict["circuit_breaker_defaults"] = circuit_breaker_defaults
        if approval_policies is not UNSET:
            field_dict["approval_policies"] = approval_policies

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.approval_policy import ApprovalPolicy
        from ..models.circuit_breaker_defaults import CircuitBreakerDefaults

        d = dict(src_dict)

        def _parse_circuit_breaker_defaults(data: object) -> CircuitBreakerDefaults | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                circuit_breaker_defaults_type_0 = CircuitBreakerDefaults.from_dict(data)

                return circuit_breaker_defaults_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(CircuitBreakerDefaults | None | Unset, data)

        circuit_breaker_defaults = _parse_circuit_breaker_defaults(d.pop("circuit_breaker_defaults", UNSET))

        def _parse_approval_policies(data: object) -> ApprovalPolicy | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                approval_policies_type_0 = ApprovalPolicy.from_dict(data)

                return approval_policies_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(ApprovalPolicy | None | Unset, data)

        approval_policies = _parse_approval_policies(d.pop("approval_policies", UNSET))

        workspace_settings_update = cls(
            circuit_breaker_defaults=circuit_breaker_defaults,
            approval_policies=approval_policies,
        )

        workspace_settings_update.additional_properties = d
        return workspace_settings_update

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
