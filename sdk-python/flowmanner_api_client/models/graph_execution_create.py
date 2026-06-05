from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.graph_execution_create_input_data_type_0 import (
        GraphExecutionCreateInputDataType0,
    )


T = TypeVar("T", bound="GraphExecutionCreate")


@_attrs_define
class GraphExecutionCreate:
    """
    Attributes:
        input_data (GraphExecutionCreateInputDataType0 | None | Unset):
    """

    input_data: GraphExecutionCreateInputDataType0 | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.graph_execution_create_input_data_type_0 import (
            GraphExecutionCreateInputDataType0,
        )

        input_data: dict[str, Any] | None | Unset
        if isinstance(self.input_data, Unset):
            input_data = UNSET
        elif isinstance(self.input_data, GraphExecutionCreateInputDataType0):
            input_data = self.input_data.to_dict()
        else:
            input_data = self.input_data

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if input_data is not UNSET:
            field_dict["input_data"] = input_data

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.graph_execution_create_input_data_type_0 import (
            GraphExecutionCreateInputDataType0,
        )

        d = dict(src_dict)

        def _parse_input_data(
            data: object,
        ) -> GraphExecutionCreateInputDataType0 | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                input_data_type_0 = GraphExecutionCreateInputDataType0.from_dict(data)

                return input_data_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(GraphExecutionCreateInputDataType0 | None | Unset, data)

        input_data = _parse_input_data(d.pop("input_data", UNSET))

        graph_execution_create = cls(
            input_data=input_data,
        )

        graph_execution_create.additional_properties = d
        return graph_execution_create

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
