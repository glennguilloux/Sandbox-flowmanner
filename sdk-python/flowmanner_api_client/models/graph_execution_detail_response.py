from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast
from uuid import UUID

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.graph_execution_detail_response_input_data_type_0 import GraphExecutionDetailResponseInputDataType0
    from ..models.graph_execution_detail_response_node_states_item import GraphExecutionDetailResponseNodeStatesItem
    from ..models.graph_execution_detail_response_output_data_type_0 import GraphExecutionDetailResponseOutputDataType0


T = TypeVar("T", bound="GraphExecutionDetailResponse")


@_attrs_define
class GraphExecutionDetailResponse:
    """
    Attributes:
        id (str | UUID):
        workflow_id (str | UUID):
        status (str):
        created_at (datetime.datetime):
        input_data (GraphExecutionDetailResponseInputDataType0 | None | Unset):
        output_data (GraphExecutionDetailResponseOutputDataType0 | None | Unset):
        error_message (None | str | Unset):
        started_at (datetime.datetime | None | Unset):
        completed_at (datetime.datetime | None | Unset):
        node_states (list[GraphExecutionDetailResponseNodeStatesItem] | Unset):
    """

    id: str | UUID
    workflow_id: str | UUID
    status: str
    created_at: datetime.datetime
    input_data: GraphExecutionDetailResponseInputDataType0 | None | Unset = UNSET
    output_data: GraphExecutionDetailResponseOutputDataType0 | None | Unset = UNSET
    error_message: None | str | Unset = UNSET
    started_at: datetime.datetime | None | Unset = UNSET
    completed_at: datetime.datetime | None | Unset = UNSET
    node_states: list[GraphExecutionDetailResponseNodeStatesItem] | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.graph_execution_detail_response_input_data_type_0 import (
            GraphExecutionDetailResponseInputDataType0,
        )
        from ..models.graph_execution_detail_response_output_data_type_0 import (
            GraphExecutionDetailResponseOutputDataType0,
        )

        id: str
        if isinstance(self.id, UUID):
            id = str(self.id)
        else:
            id = self.id

        workflow_id: str
        if isinstance(self.workflow_id, UUID):
            workflow_id = str(self.workflow_id)
        else:
            workflow_id = self.workflow_id

        status = self.status

        created_at = self.created_at.isoformat()

        input_data: dict[str, Any] | None | Unset
        if isinstance(self.input_data, Unset):
            input_data = UNSET
        elif isinstance(self.input_data, GraphExecutionDetailResponseInputDataType0):
            input_data = self.input_data.to_dict()
        else:
            input_data = self.input_data

        output_data: dict[str, Any] | None | Unset
        if isinstance(self.output_data, Unset):
            output_data = UNSET
        elif isinstance(self.output_data, GraphExecutionDetailResponseOutputDataType0):
            output_data = self.output_data.to_dict()
        else:
            output_data = self.output_data

        error_message: None | str | Unset
        if isinstance(self.error_message, Unset):
            error_message = UNSET
        else:
            error_message = self.error_message

        started_at: None | str | Unset
        if isinstance(self.started_at, Unset):
            started_at = UNSET
        elif isinstance(self.started_at, datetime.datetime):
            started_at = self.started_at.isoformat()
        else:
            started_at = self.started_at

        completed_at: None | str | Unset
        if isinstance(self.completed_at, Unset):
            completed_at = UNSET
        elif isinstance(self.completed_at, datetime.datetime):
            completed_at = self.completed_at.isoformat()
        else:
            completed_at = self.completed_at

        node_states: list[dict[str, Any]] | Unset = UNSET
        if not isinstance(self.node_states, Unset):
            node_states = []
            for node_states_item_data in self.node_states:
                node_states_item = node_states_item_data.to_dict()
                node_states.append(node_states_item)

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "id": id,
                "workflow_id": workflow_id,
                "status": status,
                "created_at": created_at,
            }
        )
        if input_data is not UNSET:
            field_dict["input_data"] = input_data
        if output_data is not UNSET:
            field_dict["output_data"] = output_data
        if error_message is not UNSET:
            field_dict["error_message"] = error_message
        if started_at is not UNSET:
            field_dict["started_at"] = started_at
        if completed_at is not UNSET:
            field_dict["completed_at"] = completed_at
        if node_states is not UNSET:
            field_dict["node_states"] = node_states

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.graph_execution_detail_response_input_data_type_0 import (
            GraphExecutionDetailResponseInputDataType0,
        )
        from ..models.graph_execution_detail_response_node_states_item import GraphExecutionDetailResponseNodeStatesItem
        from ..models.graph_execution_detail_response_output_data_type_0 import (
            GraphExecutionDetailResponseOutputDataType0,
        )

        d = dict(src_dict)

        def _parse_id(data: object) -> str | UUID:
            try:
                if not isinstance(data, str):
                    raise TypeError()
                id_type_1 = UUID(data)

                return id_type_1
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(str | UUID, data)

        id = _parse_id(d.pop("id"))

        def _parse_workflow_id(data: object) -> str | UUID:
            try:
                if not isinstance(data, str):
                    raise TypeError()
                workflow_id_type_1 = UUID(data)

                return workflow_id_type_1
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(str | UUID, data)

        workflow_id = _parse_workflow_id(d.pop("workflow_id"))

        status = d.pop("status")

        created_at = datetime.datetime.fromisoformat(d.pop("created_at"))

        def _parse_input_data(data: object) -> GraphExecutionDetailResponseInputDataType0 | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                input_data_type_0 = GraphExecutionDetailResponseInputDataType0.from_dict(data)

                return input_data_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(GraphExecutionDetailResponseInputDataType0 | None | Unset, data)

        input_data = _parse_input_data(d.pop("input_data", UNSET))

        def _parse_output_data(data: object) -> GraphExecutionDetailResponseOutputDataType0 | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                output_data_type_0 = GraphExecutionDetailResponseOutputDataType0.from_dict(data)

                return output_data_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(GraphExecutionDetailResponseOutputDataType0 | None | Unset, data)

        output_data = _parse_output_data(d.pop("output_data", UNSET))

        def _parse_error_message(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        error_message = _parse_error_message(d.pop("error_message", UNSET))

        def _parse_started_at(data: object) -> datetime.datetime | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                started_at_type_0 = datetime.datetime.fromisoformat(data)

                return started_at_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(datetime.datetime | None | Unset, data)

        started_at = _parse_started_at(d.pop("started_at", UNSET))

        def _parse_completed_at(data: object) -> datetime.datetime | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                completed_at_type_0 = datetime.datetime.fromisoformat(data)

                return completed_at_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(datetime.datetime | None | Unset, data)

        completed_at = _parse_completed_at(d.pop("completed_at", UNSET))

        _node_states = d.pop("node_states", UNSET)
        node_states: list[GraphExecutionDetailResponseNodeStatesItem] | Unset = UNSET
        if _node_states is not UNSET:
            node_states = []
            for node_states_item_data in _node_states:
                node_states_item = GraphExecutionDetailResponseNodeStatesItem.from_dict(node_states_item_data)

                node_states.append(node_states_item)

        graph_execution_detail_response = cls(
            id=id,
            workflow_id=workflow_id,
            status=status,
            created_at=created_at,
            input_data=input_data,
            output_data=output_data,
            error_message=error_message,
            started_at=started_at,
            completed_at=completed_at,
            node_states=node_states,
        )

        graph_execution_detail_response.additional_properties = d
        return graph_execution_detail_response

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
