from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.plugin_response_node_types_item import PluginResponseNodeTypesItem


T = TypeVar("T", bound="PluginResponse")


@_attrs_define
class PluginResponse:
    """
    Attributes:
        id (str):
        name (str):
        version (str):
        description (None | str | Unset):
        author (None | str | Unset):
        source (str | Unset):  Default: 'upload'.
        status (str | Unset):  Default: 'installed'.
        execution_count (int | Unset):  Default: 0.
        error_count (int | Unset):  Default: 0.
        last_executed_at (None | str | Unset):
        last_error (None | str | Unset):
        p99_latency_ms (float | None | Unset):
        permissions (list[str] | Unset):
        node_types (list[PluginResponseNodeTypesItem] | Unset):
        default_prompts (list[str] | Unset):
        created_at (str | Unset):  Default: ''.
        updated_at (str | Unset):  Default: ''.
    """

    id: str
    name: str
    version: str
    description: None | str | Unset = UNSET
    author: None | str | Unset = UNSET
    source: str | Unset = "upload"
    status: str | Unset = "installed"
    execution_count: int | Unset = 0
    error_count: int | Unset = 0
    last_executed_at: None | str | Unset = UNSET
    last_error: None | str | Unset = UNSET
    p99_latency_ms: float | None | Unset = UNSET
    permissions: list[str] | Unset = UNSET
    node_types: list[PluginResponseNodeTypesItem] | Unset = UNSET
    default_prompts: list[str] | Unset = UNSET
    created_at: str | Unset = ""
    updated_at: str | Unset = ""
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        id = self.id

        name = self.name

        version = self.version

        description: None | str | Unset
        if isinstance(self.description, Unset):
            description = UNSET
        else:
            description = self.description

        author: None | str | Unset
        if isinstance(self.author, Unset):
            author = UNSET
        else:
            author = self.author

        source = self.source

        status = self.status

        execution_count = self.execution_count

        error_count = self.error_count

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

        p99_latency_ms: float | None | Unset
        if isinstance(self.p99_latency_ms, Unset):
            p99_latency_ms = UNSET
        else:
            p99_latency_ms = self.p99_latency_ms

        permissions: list[str] | Unset = UNSET
        if not isinstance(self.permissions, Unset):
            permissions = self.permissions

        node_types: list[dict[str, Any]] | Unset = UNSET
        if not isinstance(self.node_types, Unset):
            node_types = []
            for node_types_item_data in self.node_types:
                node_types_item = node_types_item_data.to_dict()
                node_types.append(node_types_item)

        default_prompts: list[str] | Unset = UNSET
        if not isinstance(self.default_prompts, Unset):
            default_prompts = self.default_prompts

        created_at = self.created_at

        updated_at = self.updated_at

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "id": id,
                "name": name,
                "version": version,
            }
        )
        if description is not UNSET:
            field_dict["description"] = description
        if author is not UNSET:
            field_dict["author"] = author
        if source is not UNSET:
            field_dict["source"] = source
        if status is not UNSET:
            field_dict["status"] = status
        if execution_count is not UNSET:
            field_dict["execution_count"] = execution_count
        if error_count is not UNSET:
            field_dict["error_count"] = error_count
        if last_executed_at is not UNSET:
            field_dict["last_executed_at"] = last_executed_at
        if last_error is not UNSET:
            field_dict["last_error"] = last_error
        if p99_latency_ms is not UNSET:
            field_dict["p99_latency_ms"] = p99_latency_ms
        if permissions is not UNSET:
            field_dict["permissions"] = permissions
        if node_types is not UNSET:
            field_dict["node_types"] = node_types
        if default_prompts is not UNSET:
            field_dict["default_prompts"] = default_prompts
        if created_at is not UNSET:
            field_dict["created_at"] = created_at
        if updated_at is not UNSET:
            field_dict["updated_at"] = updated_at

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.plugin_response_node_types_item import PluginResponseNodeTypesItem

        d = dict(src_dict)
        id = d.pop("id")

        name = d.pop("name")

        version = d.pop("version")

        def _parse_description(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        description = _parse_description(d.pop("description", UNSET))

        def _parse_author(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        author = _parse_author(d.pop("author", UNSET))

        source = d.pop("source", UNSET)

        status = d.pop("status", UNSET)

        execution_count = d.pop("execution_count", UNSET)

        error_count = d.pop("error_count", UNSET)

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

        def _parse_p99_latency_ms(data: object) -> float | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(float | None | Unset, data)

        p99_latency_ms = _parse_p99_latency_ms(d.pop("p99_latency_ms", UNSET))

        permissions = cast(list[str], d.pop("permissions", UNSET))

        _node_types = d.pop("node_types", UNSET)
        node_types: list[PluginResponseNodeTypesItem] | Unset = UNSET
        if _node_types is not UNSET:
            node_types = []
            for node_types_item_data in _node_types:
                node_types_item = PluginResponseNodeTypesItem.from_dict(node_types_item_data)

                node_types.append(node_types_item)

        default_prompts = cast(list[str], d.pop("default_prompts", UNSET))

        created_at = d.pop("created_at", UNSET)

        updated_at = d.pop("updated_at", UNSET)

        plugin_response = cls(
            id=id,
            name=name,
            version=version,
            description=description,
            author=author,
            source=source,
            status=status,
            execution_count=execution_count,
            error_count=error_count,
            last_executed_at=last_executed_at,
            last_error=last_error,
            p99_latency_ms=p99_latency_ms,
            permissions=permissions,
            node_types=node_types,
            default_prompts=default_prompts,
            created_at=created_at,
            updated_at=updated_at,
        )

        plugin_response.additional_properties = d
        return plugin_response

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
