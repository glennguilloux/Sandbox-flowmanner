from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.plugin_execute_response_output_type_0 import PluginExecuteResponseOutputType0


T = TypeVar("T", bound="PluginExecuteResponse")


@_attrs_define
class PluginExecuteResponse:
    """
    Attributes:
        success (bool):
        output (None | PluginExecuteResponseOutputType0 | Unset):
        error (None | str | Unset):
        elapsed_ms (float | Unset):  Default: 0.0.
        plugin (None | str | Unset):
    """

    success: bool
    output: None | PluginExecuteResponseOutputType0 | Unset = UNSET
    error: None | str | Unset = UNSET
    elapsed_ms: float | Unset = 0.0
    plugin: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.plugin_execute_response_output_type_0 import PluginExecuteResponseOutputType0

        success = self.success

        output: dict[str, Any] | None | Unset
        if isinstance(self.output, Unset):
            output = UNSET
        elif isinstance(self.output, PluginExecuteResponseOutputType0):
            output = self.output.to_dict()
        else:
            output = self.output

        error: None | str | Unset
        if isinstance(self.error, Unset):
            error = UNSET
        else:
            error = self.error

        elapsed_ms = self.elapsed_ms

        plugin: None | str | Unset
        if isinstance(self.plugin, Unset):
            plugin = UNSET
        else:
            plugin = self.plugin

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "success": success,
            }
        )
        if output is not UNSET:
            field_dict["output"] = output
        if error is not UNSET:
            field_dict["error"] = error
        if elapsed_ms is not UNSET:
            field_dict["elapsed_ms"] = elapsed_ms
        if plugin is not UNSET:
            field_dict["plugin"] = plugin

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.plugin_execute_response_output_type_0 import PluginExecuteResponseOutputType0

        d = dict(src_dict)
        success = d.pop("success")

        def _parse_output(data: object) -> None | PluginExecuteResponseOutputType0 | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                output_type_0 = PluginExecuteResponseOutputType0.from_dict(data)

                return output_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | PluginExecuteResponseOutputType0 | Unset, data)

        output = _parse_output(d.pop("output", UNSET))

        def _parse_error(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        error = _parse_error(d.pop("error", UNSET))

        elapsed_ms = d.pop("elapsed_ms", UNSET)

        def _parse_plugin(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        plugin = _parse_plugin(d.pop("plugin", UNSET))

        plugin_execute_response = cls(
            success=success,
            output=output,
            error=error,
            elapsed_ms=elapsed_ms,
            plugin=plugin,
        )

        plugin_execute_response.additional_properties = d
        return plugin_execute_response

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
