from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.trigger_create_config_type_0 import TriggerCreateConfigType0


T = TypeVar("T", bound="TriggerCreate")


@_attrs_define
class TriggerCreate:
    """
    Attributes:
        trigger_type (str):
        name (str):
        mission_id (str):
        cron_expression (None | str | Unset):
        cron_timezone (str | Unset):  Default: 'UTC'.
        webhook_secret (None | str | Unset):
        config (None | TriggerCreateConfigType0 | Unset):
    """

    trigger_type: str
    name: str
    mission_id: str
    cron_expression: None | str | Unset = UNSET
    cron_timezone: str | Unset = "UTC"
    webhook_secret: None | str | Unset = UNSET
    config: None | TriggerCreateConfigType0 | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.trigger_create_config_type_0 import TriggerCreateConfigType0

        trigger_type = self.trigger_type

        name = self.name

        mission_id = self.mission_id

        cron_expression: None | str | Unset
        if isinstance(self.cron_expression, Unset):
            cron_expression = UNSET
        else:
            cron_expression = self.cron_expression

        cron_timezone = self.cron_timezone

        webhook_secret: None | str | Unset
        if isinstance(self.webhook_secret, Unset):
            webhook_secret = UNSET
        else:
            webhook_secret = self.webhook_secret

        config: dict[str, Any] | None | Unset
        if isinstance(self.config, Unset):
            config = UNSET
        elif isinstance(self.config, TriggerCreateConfigType0):
            config = self.config.to_dict()
        else:
            config = self.config

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "trigger_type": trigger_type,
                "name": name,
                "mission_id": mission_id,
            }
        )
        if cron_expression is not UNSET:
            field_dict["cron_expression"] = cron_expression
        if cron_timezone is not UNSET:
            field_dict["cron_timezone"] = cron_timezone
        if webhook_secret is not UNSET:
            field_dict["webhook_secret"] = webhook_secret
        if config is not UNSET:
            field_dict["config"] = config

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.trigger_create_config_type_0 import TriggerCreateConfigType0

        d = dict(src_dict)
        trigger_type = d.pop("trigger_type")

        name = d.pop("name")

        mission_id = d.pop("mission_id")

        def _parse_cron_expression(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        cron_expression = _parse_cron_expression(d.pop("cron_expression", UNSET))

        cron_timezone = d.pop("cron_timezone", UNSET)

        def _parse_webhook_secret(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        webhook_secret = _parse_webhook_secret(d.pop("webhook_secret", UNSET))

        def _parse_config(data: object) -> None | TriggerCreateConfigType0 | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                config_type_0 = TriggerCreateConfigType0.from_dict(data)

                return config_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | TriggerCreateConfigType0 | Unset, data)

        config = _parse_config(d.pop("config", UNSET))

        trigger_create = cls(
            trigger_type=trigger_type,
            name=name,
            mission_id=mission_id,
            cron_expression=cron_expression,
            cron_timezone=cron_timezone,
            webhook_secret=webhook_secret,
            config=config,
        )

        trigger_create.additional_properties = d
        return trigger_create

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
