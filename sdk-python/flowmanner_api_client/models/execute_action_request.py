from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.execute_action_request_params import ExecuteActionRequestParams


T = TypeVar("T", bound="ExecuteActionRequest")


@_attrs_define
class ExecuteActionRequest:
    """
    Attributes:
        connection_id (str): OAuth connection ID to use
        action_name (str): Action slug, e.g. 'send_message'
        params (ExecuteActionRequestParams | Unset): Action parameters
    """

    connection_id: str
    action_name: str
    params: ExecuteActionRequestParams | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        connection_id = self.connection_id

        action_name = self.action_name

        params: dict[str, Any] | Unset = UNSET
        if not isinstance(self.params, Unset):
            params = self.params.to_dict()

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "connection_id": connection_id,
                "action_name": action_name,
            }
        )
        if params is not UNSET:
            field_dict["params"] = params

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.execute_action_request_params import ExecuteActionRequestParams

        d = dict(src_dict)
        connection_id = d.pop("connection_id")

        action_name = d.pop("action_name")

        _params = d.pop("params", UNSET)
        params: ExecuteActionRequestParams | Unset
        if isinstance(_params, Unset):
            params = UNSET
        else:
            params = ExecuteActionRequestParams.from_dict(_params)

        execute_action_request = cls(
            connection_id=connection_id,
            action_name=action_name,
            params=params,
        )

        execute_action_request.additional_properties = d
        return execute_action_request

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
