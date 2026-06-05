from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.trigger_update_config_type_0 import TriggerUpdateConfigType0


T = TypeVar("T", bound="TriggerUpdate")


@_attrs_define
class TriggerUpdate:
    """
    Attributes:
        name (None | str | Unset):
        cron_expression (None | str | Unset):
        cron_timezone (None | str | Unset):
        config (None | TriggerUpdateConfigType0 | Unset):
        status (None | str | Unset):
    """

    name: None | str | Unset = UNSET
    cron_expression: None | str | Unset = UNSET
    cron_timezone: None | str | Unset = UNSET
    config: None | TriggerUpdateConfigType0 | Unset = UNSET
    status: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.trigger_update_config_type_0 import TriggerUpdateConfigType0

        name: None | str | Unset
        if isinstance(self.name, Unset):
            name = UNSET
        else:
            name = self.name

        cron_expression: None | str | Unset
        if isinstance(self.cron_expression, Unset):
            cron_expression = UNSET
        else:
            cron_expression = self.cron_expression

        cron_timezone: None | str | Unset
        if isinstance(self.cron_timezone, Unset):
            cron_timezone = UNSET
        else:
            cron_timezone = self.cron_timezone

        config: dict[str, Any] | None | Unset
        if isinstance(self.config, Unset):
            config = UNSET
        elif isinstance(self.config, TriggerUpdateConfigType0):
            config = self.config.to_dict()
        else:
            config = self.config

        status: None | str | Unset
        if isinstance(self.status, Unset):
            status = UNSET
        else:
            status = self.status

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if name is not UNSET:
            field_dict["name"] = name
        if cron_expression is not UNSET:
            field_dict["cron_expression"] = cron_expression
        if cron_timezone is not UNSET:
            field_dict["cron_timezone"] = cron_timezone
        if config is not UNSET:
            field_dict["config"] = config
        if status is not UNSET:
            field_dict["status"] = status

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.trigger_update_config_type_0 import TriggerUpdateConfigType0

        d = dict(src_dict)

        def _parse_name(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        name = _parse_name(d.pop("name", UNSET))

        def _parse_cron_expression(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        cron_expression = _parse_cron_expression(d.pop("cron_expression", UNSET))

        def _parse_cron_timezone(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        cron_timezone = _parse_cron_timezone(d.pop("cron_timezone", UNSET))

        def _parse_config(data: object) -> None | TriggerUpdateConfigType0 | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                config_type_0 = TriggerUpdateConfigType0.from_dict(data)

                return config_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | TriggerUpdateConfigType0 | Unset, data)

        config = _parse_config(d.pop("config", UNSET))

        def _parse_status(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        status = _parse_status(d.pop("status", UNSET))

        trigger_update = cls(
            name=name,
            cron_expression=cron_expression,
            cron_timezone=cron_timezone,
            config=config,
            status=status,
        )

        trigger_update.additional_properties = d
        return trigger_update

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
