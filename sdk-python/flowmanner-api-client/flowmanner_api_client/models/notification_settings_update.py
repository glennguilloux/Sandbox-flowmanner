from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="NotificationSettingsUpdate")


@_attrs_define
class NotificationSettingsUpdate:
    """Update notification settings.

    Attributes:
        in_app_enabled (bool | None | Unset):
        email_enabled (bool | None | Unset):
        push_enabled (bool | None | Unset):
        event_mission_completed (bool | None | Unset):
        event_mission_failed (bool | None | Unset):
        event_mention (bool | None | Unset):
        event_system (bool | None | Unset):
        digest_mode (None | str | Unset):
        digest_time_utc (None | str | Unset):
        digest_day_of_week (int | None | Unset):
        email_address (None | str | Unset):
        push_enabled_channels (None | str | Unset):
        mission_completed (bool | None | Unset):
        mission_failed (bool | None | Unset):
        slack_enabled (bool | None | Unset):
        slack_webhook_url (None | str | Unset):
    """

    in_app_enabled: bool | None | Unset = UNSET
    email_enabled: bool | None | Unset = UNSET
    push_enabled: bool | None | Unset = UNSET
    event_mission_completed: bool | None | Unset = UNSET
    event_mission_failed: bool | None | Unset = UNSET
    event_mention: bool | None | Unset = UNSET
    event_system: bool | None | Unset = UNSET
    digest_mode: None | str | Unset = UNSET
    digest_time_utc: None | str | Unset = UNSET
    digest_day_of_week: int | None | Unset = UNSET
    email_address: None | str | Unset = UNSET
    push_enabled_channels: None | str | Unset = UNSET
    mission_completed: bool | None | Unset = UNSET
    mission_failed: bool | None | Unset = UNSET
    slack_enabled: bool | None | Unset = UNSET
    slack_webhook_url: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        in_app_enabled: bool | None | Unset
        if isinstance(self.in_app_enabled, Unset):
            in_app_enabled = UNSET
        else:
            in_app_enabled = self.in_app_enabled

        email_enabled: bool | None | Unset
        if isinstance(self.email_enabled, Unset):
            email_enabled = UNSET
        else:
            email_enabled = self.email_enabled

        push_enabled: bool | None | Unset
        if isinstance(self.push_enabled, Unset):
            push_enabled = UNSET
        else:
            push_enabled = self.push_enabled

        event_mission_completed: bool | None | Unset
        if isinstance(self.event_mission_completed, Unset):
            event_mission_completed = UNSET
        else:
            event_mission_completed = self.event_mission_completed

        event_mission_failed: bool | None | Unset
        if isinstance(self.event_mission_failed, Unset):
            event_mission_failed = UNSET
        else:
            event_mission_failed = self.event_mission_failed

        event_mention: bool | None | Unset
        if isinstance(self.event_mention, Unset):
            event_mention = UNSET
        else:
            event_mention = self.event_mention

        event_system: bool | None | Unset
        if isinstance(self.event_system, Unset):
            event_system = UNSET
        else:
            event_system = self.event_system

        digest_mode: None | str | Unset
        if isinstance(self.digest_mode, Unset):
            digest_mode = UNSET
        else:
            digest_mode = self.digest_mode

        digest_time_utc: None | str | Unset
        if isinstance(self.digest_time_utc, Unset):
            digest_time_utc = UNSET
        else:
            digest_time_utc = self.digest_time_utc

        digest_day_of_week: int | None | Unset
        if isinstance(self.digest_day_of_week, Unset):
            digest_day_of_week = UNSET
        else:
            digest_day_of_week = self.digest_day_of_week

        email_address: None | str | Unset
        if isinstance(self.email_address, Unset):
            email_address = UNSET
        else:
            email_address = self.email_address

        push_enabled_channels: None | str | Unset
        if isinstance(self.push_enabled_channels, Unset):
            push_enabled_channels = UNSET
        else:
            push_enabled_channels = self.push_enabled_channels

        mission_completed: bool | None | Unset
        if isinstance(self.mission_completed, Unset):
            mission_completed = UNSET
        else:
            mission_completed = self.mission_completed

        mission_failed: bool | None | Unset
        if isinstance(self.mission_failed, Unset):
            mission_failed = UNSET
        else:
            mission_failed = self.mission_failed

        slack_enabled: bool | None | Unset
        if isinstance(self.slack_enabled, Unset):
            slack_enabled = UNSET
        else:
            slack_enabled = self.slack_enabled

        slack_webhook_url: None | str | Unset
        if isinstance(self.slack_webhook_url, Unset):
            slack_webhook_url = UNSET
        else:
            slack_webhook_url = self.slack_webhook_url

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if in_app_enabled is not UNSET:
            field_dict["in_app_enabled"] = in_app_enabled
        if email_enabled is not UNSET:
            field_dict["email_enabled"] = email_enabled
        if push_enabled is not UNSET:
            field_dict["push_enabled"] = push_enabled
        if event_mission_completed is not UNSET:
            field_dict["event_mission_completed"] = event_mission_completed
        if event_mission_failed is not UNSET:
            field_dict["event_mission_failed"] = event_mission_failed
        if event_mention is not UNSET:
            field_dict["event_mention"] = event_mention
        if event_system is not UNSET:
            field_dict["event_system"] = event_system
        if digest_mode is not UNSET:
            field_dict["digest_mode"] = digest_mode
        if digest_time_utc is not UNSET:
            field_dict["digest_time_utc"] = digest_time_utc
        if digest_day_of_week is not UNSET:
            field_dict["digest_day_of_week"] = digest_day_of_week
        if email_address is not UNSET:
            field_dict["email_address"] = email_address
        if push_enabled_channels is not UNSET:
            field_dict["push_enabled_channels"] = push_enabled_channels
        if mission_completed is not UNSET:
            field_dict["mission_completed"] = mission_completed
        if mission_failed is not UNSET:
            field_dict["mission_failed"] = mission_failed
        if slack_enabled is not UNSET:
            field_dict["slack_enabled"] = slack_enabled
        if slack_webhook_url is not UNSET:
            field_dict["slack_webhook_url"] = slack_webhook_url

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)

        def _parse_in_app_enabled(data: object) -> bool | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(bool | None | Unset, data)

        in_app_enabled = _parse_in_app_enabled(d.pop("in_app_enabled", UNSET))

        def _parse_email_enabled(data: object) -> bool | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(bool | None | Unset, data)

        email_enabled = _parse_email_enabled(d.pop("email_enabled", UNSET))

        def _parse_push_enabled(data: object) -> bool | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(bool | None | Unset, data)

        push_enabled = _parse_push_enabled(d.pop("push_enabled", UNSET))

        def _parse_event_mission_completed(data: object) -> bool | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(bool | None | Unset, data)

        event_mission_completed = _parse_event_mission_completed(
            d.pop("event_mission_completed", UNSET)
        )

        def _parse_event_mission_failed(data: object) -> bool | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(bool | None | Unset, data)

        event_mission_failed = _parse_event_mission_failed(
            d.pop("event_mission_failed", UNSET)
        )

        def _parse_event_mention(data: object) -> bool | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(bool | None | Unset, data)

        event_mention = _parse_event_mention(d.pop("event_mention", UNSET))

        def _parse_event_system(data: object) -> bool | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(bool | None | Unset, data)

        event_system = _parse_event_system(d.pop("event_system", UNSET))

        def _parse_digest_mode(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        digest_mode = _parse_digest_mode(d.pop("digest_mode", UNSET))

        def _parse_digest_time_utc(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        digest_time_utc = _parse_digest_time_utc(d.pop("digest_time_utc", UNSET))

        def _parse_digest_day_of_week(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        digest_day_of_week = _parse_digest_day_of_week(
            d.pop("digest_day_of_week", UNSET)
        )

        def _parse_email_address(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        email_address = _parse_email_address(d.pop("email_address", UNSET))

        def _parse_push_enabled_channels(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        push_enabled_channels = _parse_push_enabled_channels(
            d.pop("push_enabled_channels", UNSET)
        )

        def _parse_mission_completed(data: object) -> bool | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(bool | None | Unset, data)

        mission_completed = _parse_mission_completed(d.pop("mission_completed", UNSET))

        def _parse_mission_failed(data: object) -> bool | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(bool | None | Unset, data)

        mission_failed = _parse_mission_failed(d.pop("mission_failed", UNSET))

        def _parse_slack_enabled(data: object) -> bool | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(bool | None | Unset, data)

        slack_enabled = _parse_slack_enabled(d.pop("slack_enabled", UNSET))

        def _parse_slack_webhook_url(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        slack_webhook_url = _parse_slack_webhook_url(d.pop("slack_webhook_url", UNSET))

        notification_settings_update = cls(
            in_app_enabled=in_app_enabled,
            email_enabled=email_enabled,
            push_enabled=push_enabled,
            event_mission_completed=event_mission_completed,
            event_mission_failed=event_mission_failed,
            event_mention=event_mention,
            event_system=event_system,
            digest_mode=digest_mode,
            digest_time_utc=digest_time_utc,
            digest_day_of_week=digest_day_of_week,
            email_address=email_address,
            push_enabled_channels=push_enabled_channels,
            mission_completed=mission_completed,
            mission_failed=mission_failed,
            slack_enabled=slack_enabled,
            slack_webhook_url=slack_webhook_url,
        )

        notification_settings_update.additional_properties = d
        return notification_settings_update

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
