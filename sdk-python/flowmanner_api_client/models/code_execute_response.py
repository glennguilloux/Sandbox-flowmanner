from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="CodeExecuteResponse")


@_attrs_define
class CodeExecuteResponse:
    """Response from code execution.

    Attributes:
        success (bool):
        stdout (str | Unset):  Default: ''.
        stderr (str | Unset):  Default: ''.
        return_code (int | Unset):  Default: -1.
        execution_time_ms (float | Unset):  Default: 0.0.
        error (None | str | Unset):
    """

    success: bool
    stdout: str | Unset = ""
    stderr: str | Unset = ""
    return_code: int | Unset = -1
    execution_time_ms: float | Unset = 0.0
    error: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        success = self.success

        stdout = self.stdout

        stderr = self.stderr

        return_code = self.return_code

        execution_time_ms = self.execution_time_ms

        error: None | str | Unset
        if isinstance(self.error, Unset):
            error = UNSET
        else:
            error = self.error

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "success": success,
            }
        )
        if stdout is not UNSET:
            field_dict["stdout"] = stdout
        if stderr is not UNSET:
            field_dict["stderr"] = stderr
        if return_code is not UNSET:
            field_dict["return_code"] = return_code
        if execution_time_ms is not UNSET:
            field_dict["execution_time_ms"] = execution_time_ms
        if error is not UNSET:
            field_dict["error"] = error

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        success = d.pop("success")

        stdout = d.pop("stdout", UNSET)

        stderr = d.pop("stderr", UNSET)

        return_code = d.pop("return_code", UNSET)

        execution_time_ms = d.pop("execution_time_ms", UNSET)

        def _parse_error(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        error = _parse_error(d.pop("error", UNSET))

        code_execute_response = cls(
            success=success,
            stdout=stdout,
            stderr=stderr,
            return_code=return_code,
            execution_time_ms=execution_time_ms,
            error=error,
        )

        code_execute_response.additional_properties = d
        return code_execute_response

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
