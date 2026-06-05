from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.tool_execution_result_result_type_0 import (
        ToolExecutionResultResultType0,
    )


T = TypeVar("T", bound="ToolExecutionResult")


@_attrs_define
class ToolExecutionResult:
    """
    Attributes:
        tool_id (str):
        success (bool):
        result (None | ToolExecutionResultResultType0 | Unset):
        error (None | str | Unset):
        execution_time_ms (float | Unset):  Default: 0.0.
        tokens_used (int | Unset):  Default: 0.
        cost_usd (float | Unset):  Default: 0.0.
    """

    tool_id: str
    success: bool
    result: None | ToolExecutionResultResultType0 | Unset = UNSET
    error: None | str | Unset = UNSET
    execution_time_ms: float | Unset = 0.0
    tokens_used: int | Unset = 0
    cost_usd: float | Unset = 0.0
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.tool_execution_result_result_type_0 import (
            ToolExecutionResultResultType0,
        )

        tool_id = self.tool_id

        success = self.success

        result: dict[str, Any] | None | Unset
        if isinstance(self.result, Unset):
            result = UNSET
        elif isinstance(self.result, ToolExecutionResultResultType0):
            result = self.result.to_dict()
        else:
            result = self.result

        error: None | str | Unset
        if isinstance(self.error, Unset):
            error = UNSET
        else:
            error = self.error

        execution_time_ms = self.execution_time_ms

        tokens_used = self.tokens_used

        cost_usd = self.cost_usd

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "tool_id": tool_id,
                "success": success,
            }
        )
        if result is not UNSET:
            field_dict["result"] = result
        if error is not UNSET:
            field_dict["error"] = error
        if execution_time_ms is not UNSET:
            field_dict["execution_time_ms"] = execution_time_ms
        if tokens_used is not UNSET:
            field_dict["tokens_used"] = tokens_used
        if cost_usd is not UNSET:
            field_dict["cost_usd"] = cost_usd

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.tool_execution_result_result_type_0 import (
            ToolExecutionResultResultType0,
        )

        d = dict(src_dict)
        tool_id = d.pop("tool_id")

        success = d.pop("success")

        def _parse_result(
            data: object,
        ) -> None | ToolExecutionResultResultType0 | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                result_type_0 = ToolExecutionResultResultType0.from_dict(data)

                return result_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | ToolExecutionResultResultType0 | Unset, data)

        result = _parse_result(d.pop("result", UNSET))

        def _parse_error(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        error = _parse_error(d.pop("error", UNSET))

        execution_time_ms = d.pop("execution_time_ms", UNSET)

        tokens_used = d.pop("tokens_used", UNSET)

        cost_usd = d.pop("cost_usd", UNSET)

        tool_execution_result = cls(
            tool_id=tool_id,
            success=success,
            result=result,
            error=error,
            execution_time_ms=execution_time_ms,
            tokens_used=tokens_used,
            cost_usd=cost_usd,
        )

        tool_execution_result.additional_properties = d
        return tool_execution_result

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
