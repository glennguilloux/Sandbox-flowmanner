from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="PluginStatusResponse")


@_attrs_define
class PluginStatusResponse:
    """
    Attributes:
        id (str):
        name (str):
        version (str):
        status (str):
        health (str):
        execution_count (int | Unset):  Default: 0.
        error_count (int | Unset):  Default: 0.
        error_rate (float | Unset):  Default: 0.0.
        last_executed_at (None | str | Unset):
        last_error (None | str | Unset):
        registered_node_types (list[str] | Unset):
    """

    id: str
    name: str
    version: str
    status: str
    health: str
    execution_count: int | Unset = 0
    error_count: int | Unset = 0
    error_rate: float | Unset = 0.0
    last_executed_at: None | str | Unset = UNSET
    last_error: None | str | Unset = UNSET
    registered_node_types: list[str] | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        id = self.id

        name = self.name

        version = self.version

        status = self.status

        health = self.health

        execution_count = self.execution_count

        error_count = self.error_count

        error_rate = self.error_rate

        last_executed_at: None | str | Unset
        if isinstance(self.last_executed_at, Unset):
            last_executed_at = UNSET
        else:
            last_executed_at = self.last_executed_at

        last_error: None | str | Unset
        if isinstance(self.last_error, Unset):
            last_error = UNSET
        else:
            last_error = self.last_error

        registered_node_types: list[str] | Unset = UNSET
        if not isinstance(self.registered_node_types, Unset):
            registered_node_types = self.registered_node_types

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "id": id,
                "name": name,
                "version": version,
                "status": status,
                "health": health,
            }
        )
        if execution_count is not UNSET:
            field_dict["execution_count"] = execution_count
        if error_count is not UNSET:
            field_dict["error_count"] = error_count
        if error_rate is not UNSET:
            field_dict["error_rate"] = error_rate
        if last_executed_at is not UNSET:
            field_dict["last_executed_at"] = last_executed_at
        if last_error is not UNSET:
            field_dict["last_error"] = last_error
        if registered_node_types is not UNSET:
            field_dict["registered_node_types"] = registered_node_types

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        id = d.pop("id")

        name = d.pop("name")

        version = d.pop("version")

        status = d.pop("status")

        health = d.pop("health")

        execution_count = d.pop("execution_count", UNSET)

        error_count = d.pop("error_count", UNSET)

        error_rate = d.pop("error_rate", UNSET)

        def _parse_last_executed_at(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        last_executed_at = _parse_last_executed_at(d.pop("last_executed_at", UNSET))

        def _parse_last_error(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        last_error = _parse_last_error(d.pop("last_error", UNSET))

        registered_node_types = cast(list[str], d.pop("registered_node_types", UNSET))

        plugin_status_response = cls(
            id=id,
            name=name,
            version=version,
            status=status,
            health=health,
            execution_count=execution_count,
            error_count=error_count,
            error_rate=error_rate,
            last_executed_at=last_executed_at,
            last_error=last_error,
            registered_node_types=registered_node_types,
        )

        plugin_status_response.additional_properties = d
        return plugin_status_response

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
