from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.console_log_entry import ConsoleLogEntry


T = TypeVar("T", bound="ConsoleLogsResponse")


@_attrs_define
class ConsoleLogsResponse:
    """
    Attributes:
        success (bool):
        logs (list[ConsoleLogEntry] | Unset):
        error (None | str | Unset):
    """

    success: bool
    logs: list[ConsoleLogEntry] | Unset = UNSET
    error: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        success = self.success

        logs: list[dict[str, Any]] | Unset = UNSET
        if not isinstance(self.logs, Unset):
            logs = []
            for logs_item_data in self.logs:
                logs_item = logs_item_data.to_dict()
                logs.append(logs_item)

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
        if logs is not UNSET:
            field_dict["logs"] = logs
        if error is not UNSET:
            field_dict["error"] = error

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.console_log_entry import ConsoleLogEntry

        d = dict(src_dict)
        success = d.pop("success")

        _logs = d.pop("logs", UNSET)
        logs: list[ConsoleLogEntry] | Unset = UNSET
        if _logs is not UNSET:
            logs = []
            for logs_item_data in _logs:
                logs_item = ConsoleLogEntry.from_dict(logs_item_data)

                logs.append(logs_item)

        def _parse_error(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        error = _parse_error(d.pop("error", UNSET))

        console_logs_response = cls(
            success=success,
            logs=logs,
            error=error,
        )

        console_logs_response.additional_properties = d
        return console_logs_response

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
