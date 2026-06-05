from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field
from dateutil.parser import isoparse

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.graph_state_response_state_data import GraphStateResponseStateData


T = TypeVar("T", bound="GraphStateResponse")


@_attrs_define
class GraphStateResponse:
    """
    Attributes:
        id (str):
        state_data (GraphStateResponseStateData):
        created_at (datetime.datetime):
        workflow_id (None | str | Unset):
        execution_id (None | str | Unset):
    """

    id: str
    state_data: GraphStateResponseStateData
    created_at: datetime.datetime
    workflow_id: None | str | Unset = UNSET
    execution_id: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        id = self.id

        state_data = self.state_data.to_dict()

        created_at = self.created_at.isoformat()

        workflow_id: None | str | Unset
        if isinstance(self.workflow_id, Unset):
            workflow_id = UNSET
        else:
            workflow_id = self.workflow_id

        execution_id: None | str | Unset
        if isinstance(self.execution_id, Unset):
            execution_id = UNSET
        else:
            execution_id = self.execution_id

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "id": id,
                "state_data": state_data,
                "created_at": created_at,
            }
        )
        if workflow_id is not UNSET:
            field_dict["workflow_id"] = workflow_id
        if execution_id is not UNSET:
            field_dict["execution_id"] = execution_id

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.graph_state_response_state_data import GraphStateResponseStateData

        d = dict(src_dict)
        id = d.pop("id")

        state_data = GraphStateResponseStateData.from_dict(d.pop("state_data"))

        created_at = isoparse(d.pop("created_at"))

        def _parse_workflow_id(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        workflow_id = _parse_workflow_id(d.pop("workflow_id", UNSET))

        def _parse_execution_id(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        execution_id = _parse_execution_id(d.pop("execution_id", UNSET))

        graph_state_response = cls(
            id=id,
            state_data=state_data,
            created_at=created_at,
            workflow_id=workflow_id,
            execution_id=execution_id,
        )

        graph_state_response.additional_properties = d
        return graph_state_response

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
