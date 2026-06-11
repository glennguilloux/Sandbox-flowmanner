from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field
from dateutil.parser import isoparse

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.graph_execution_response_input_data_type_0 import (
        GraphExecutionResponseInputDataType0,
    )
    from ..models.graph_execution_response_output_data_type_0 import (
        GraphExecutionResponseOutputDataType0,
    )


T = TypeVar("T", bound="GraphExecutionResponse")


@_attrs_define
class GraphExecutionResponse:
    """
    Attributes:
        id (str):
        workflow_id (str):
        status (str):
        created_at (datetime.datetime):
        input_data (GraphExecutionResponseInputDataType0 | None | Unset):
        output_data (GraphExecutionResponseOutputDataType0 | None | Unset):
        error_message (None | str | Unset):
        started_at (datetime.datetime | None | Unset):
        completed_at (datetime.datetime | None | Unset):
    """

    id: str
    workflow_id: str
    status: str
    created_at: datetime.datetime
    input_data: GraphExecutionResponseInputDataType0 | None | Unset = UNSET
    output_data: GraphExecutionResponseOutputDataType0 | None | Unset = UNSET
    error_message: None | str | Unset = UNSET
    started_at: datetime.datetime | None | Unset = UNSET
    completed_at: datetime.datetime | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.graph_execution_response_input_data_type_0 import (
            GraphExecutionResponseInputDataType0,
        )
        from ..models.graph_execution_response_output_data_type_0 import (
            GraphExecutionResponseOutputDataType0,
        )

        id = self.id

        workflow_id = self.workflow_id

        status = self.status

        created_at = self.created_at.isoformat()

        input_data: dict[str, Any] | None | Unset
        if isinstance(self.input_data, Unset):
            input_data = UNSET
        elif isinstance(self.input_data, GraphExecutionResponseInputDataType0):
            input_data = self.input_data.to_dict()
        else:
            input_data = self.input_data

        output_data: dict[str, Any] | None | Unset
        if isinstance(self.output_data, Unset):
            output_data = UNSET
        elif isinstance(self.output_data, GraphExecutionResponseOutputDataType0):
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

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.graph_execution_response_input_data_type_0 import (
            GraphExecutionResponseInputDataType0,
        )
        from ..models.graph_execution_response_output_data_type_0 import (
            GraphExecutionResponseOutputDataType0,
        )

        d = dict(src_dict)
        id = d.pop("id")

        workflow_id = d.pop("workflow_id")

        status = d.pop("status")

        created_at = isoparse(d.pop("created_at"))

        def _parse_input_data(
            data: object,
        ) -> GraphExecutionResponseInputDataType0 | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                input_data_type_0 = GraphExecutionResponseInputDataType0.from_dict(data)

                return input_data_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(GraphExecutionResponseInputDataType0 | None | Unset, data)

        input_data = _parse_input_data(d.pop("input_data", UNSET))

        def _parse_output_data(
            data: object,
        ) -> GraphExecutionResponseOutputDataType0 | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                output_data_type_0 = GraphExecutionResponseOutputDataType0.from_dict(data)

                return output_data_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(GraphExecutionResponseOutputDataType0 | None | Unset, data)

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
                started_at_type_0 = isoparse(data)

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
                completed_at_type_0 = isoparse(data)

                return completed_at_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(datetime.datetime | None | Unset, data)

        completed_at = _parse_completed_at(d.pop("completed_at", UNSET))

        graph_execution_response = cls(
            id=id,
            workflow_id=workflow_id,
            status=status,
            created_at=created_at,
            input_data=input_data,
            output_data=output_data,
            error_message=error_message,
            started_at=started_at,
            completed_at=completed_at,
        )

        graph_execution_response.additional_properties = d
        return graph_execution_response

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
