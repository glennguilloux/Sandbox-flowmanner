from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.trigger_response_config_type_0 import TriggerResponseConfigType0


T = TypeVar("T", bound="TriggerResponse")


@_attrs_define
class TriggerResponse:
    """
    Attributes:
        id (str):
        user_id (int):
        mission_id (str):
        trigger_type (str):
        name (str):
        status (str):
        cron_expression (None | str | Unset):
        cron_timezone (str | Unset):  Default: 'UTC'.
        webhook_path (None | str | Unset):
        config (None | TriggerResponseConfigType0 | Unset):
        fire_count (int | Unset):  Default: 0.
        last_fired_at (datetime.datetime | None | Unset):
        next_fire_at (datetime.datetime | None | Unset):
        created_at (datetime.datetime | None | Unset):
        updated_at (datetime.datetime | None | Unset):
    """

    id: str
    user_id: int
    mission_id: str
    trigger_type: str
    name: str
    status: str
    cron_expression: None | str | Unset = UNSET
    cron_timezone: str | Unset = "UTC"
    webhook_path: None | str | Unset = UNSET
    config: None | TriggerResponseConfigType0 | Unset = UNSET
    fire_count: int | Unset = 0
    last_fired_at: datetime.datetime | None | Unset = UNSET
    next_fire_at: datetime.datetime | None | Unset = UNSET
    created_at: datetime.datetime | None | Unset = UNSET
    updated_at: datetime.datetime | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.trigger_response_config_type_0 import TriggerResponseConfigType0

        id = self.id

        user_id = self.user_id

        mission_id = self.mission_id

        trigger_type = self.trigger_type

        name = self.name

        status = self.status

        cron_expression: None | str | Unset
        if isinstance(self.cron_expression, Unset):
            cron_expression = UNSET
        else:
            cron_expression = self.cron_expression

        cron_timezone = self.cron_timezone

        webhook_path: None | str | Unset
        if isinstance(self.webhook_path, Unset):
            webhook_path = UNSET
        else:
            webhook_path = self.webhook_path

        config: dict[str, Any] | None | Unset
        if isinstance(self.config, Unset):
            config = UNSET
        elif isinstance(self.config, TriggerResponseConfigType0):
            config = self.config.to_dict()
        else:
            config = self.config

        fire_count = self.fire_count

        last_fired_at: None | str | Unset
        if isinstance(self.last_fired_at, Unset):
            last_fired_at = UNSET
        elif isinstance(self.last_fired_at, datetime.datetime):
            last_fired_at = self.last_fired_at.isoformat()
        else:
            last_fired_at = self.last_fired_at

        next_fire_at: None | str | Unset
        if isinstance(self.next_fire_at, Unset):
            next_fire_at = UNSET
        elif isinstance(self.next_fire_at, datetime.datetime):
            next_fire_at = self.next_fire_at.isoformat()
        else:
            next_fire_at = self.next_fire_at

        created_at: None | str | Unset
        if isinstance(self.created_at, Unset):
            created_at = UNSET
        elif isinstance(self.created_at, datetime.datetime):
            created_at = self.created_at.isoformat()
        else:
            created_at = self.created_at

        updated_at: None | str | Unset
        if isinstance(self.updated_at, Unset):
            updated_at = UNSET
        elif isinstance(self.updated_at, datetime.datetime):
            updated_at = self.updated_at.isoformat()
        else:
            updated_at = self.updated_at

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "id": id,
                "user_id": user_id,
                "mission_id": mission_id,
                "trigger_type": trigger_type,
                "name": name,
                "status": status,
            }
        )
        if cron_expression is not UNSET:
            field_dict["cron_expression"] = cron_expression
        if cron_timezone is not UNSET:
            field_dict["cron_timezone"] = cron_timezone
        if webhook_path is not UNSET:
            field_dict["webhook_path"] = webhook_path
        if config is not UNSET:
            field_dict["config"] = config
        if fire_count is not UNSET:
            field_dict["fire_count"] = fire_count
        if last_fired_at is not UNSET:
            field_dict["last_fired_at"] = last_fired_at
        if next_fire_at is not UNSET:
            field_dict["next_fire_at"] = next_fire_at
        if created_at is not UNSET:
            field_dict["created_at"] = created_at
        if updated_at is not UNSET:
            field_dict["updated_at"] = updated_at

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.trigger_response_config_type_0 import TriggerResponseConfigType0

        d = dict(src_dict)
        id = d.pop("id")

        user_id = d.pop("user_id")

        mission_id = d.pop("mission_id")

        trigger_type = d.pop("trigger_type")

        name = d.pop("name")

        status = d.pop("status")

        def _parse_cron_expression(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        cron_expression = _parse_cron_expression(d.pop("cron_expression", UNSET))

        cron_timezone = d.pop("cron_timezone", UNSET)

        def _parse_webhook_path(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        webhook_path = _parse_webhook_path(d.pop("webhook_path", UNSET))

        def _parse_config(data: object) -> None | TriggerResponseConfigType0 | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                config_type_0 = TriggerResponseConfigType0.from_dict(data)

                return config_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | TriggerResponseConfigType0 | Unset, data)

        config = _parse_config(d.pop("config", UNSET))

        fire_count = d.pop("fire_count", UNSET)

        def _parse_last_fired_at(data: object) -> datetime.datetime | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                last_fired_at_type_0 = datetime.datetime.fromisoformat(data)

                return last_fired_at_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(datetime.datetime | None | Unset, data)

        last_fired_at = _parse_last_fired_at(d.pop("last_fired_at", UNSET))

        def _parse_next_fire_at(data: object) -> datetime.datetime | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                next_fire_at_type_0 = datetime.datetime.fromisoformat(data)

                return next_fire_at_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(datetime.datetime | None | Unset, data)

        next_fire_at = _parse_next_fire_at(d.pop("next_fire_at", UNSET))

        def _parse_created_at(data: object) -> datetime.datetime | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                created_at_type_0 = datetime.datetime.fromisoformat(data)

                return created_at_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(datetime.datetime | None | Unset, data)

        created_at = _parse_created_at(d.pop("created_at", UNSET))

        def _parse_updated_at(data: object) -> datetime.datetime | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                updated_at_type_0 = datetime.datetime.fromisoformat(data)

                return updated_at_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(datetime.datetime | None | Unset, data)

        updated_at = _parse_updated_at(d.pop("updated_at", UNSET))

        trigger_response = cls(
            id=id,
            user_id=user_id,
            mission_id=mission_id,
            trigger_type=trigger_type,
            name=name,
            status=status,
            cron_expression=cron_expression,
            cron_timezone=cron_timezone,
            webhook_path=webhook_path,
            config=config,
            fire_count=fire_count,
            last_fired_at=last_fired_at,
            next_fire_at=next_fire_at,
            created_at=created_at,
            updated_at=updated_at,
        )

        trigger_response.additional_properties = d
        return trigger_response

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
