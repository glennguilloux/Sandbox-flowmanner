from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field
from dateutil.parser import isoparse

from ..types import UNSET, Unset

T = TypeVar("T", bound="TriggerLogResponse")


@_attrs_define
class TriggerLogResponse:
    """
    Attributes:
        id (str):
        trigger_id (str):
        status (str):
        trigger_type (str):
        mission_run_id (None | str | Unset):
        error_message (None | str | Unset):
        duration_ms (int | None | Unset):
        webhook_signature_valid (bool | None | Unset):
        fired_at (datetime.datetime | None | Unset):
    """

    id: str
    trigger_id: str
    status: str
    trigger_type: str
    mission_run_id: None | str | Unset = UNSET
    error_message: None | str | Unset = UNSET
    duration_ms: int | None | Unset = UNSET
    webhook_signature_valid: bool | None | Unset = UNSET
    fired_at: datetime.datetime | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        id = self.id

        trigger_id = self.trigger_id

        status = self.status

        trigger_type = self.trigger_type

        mission_run_id: None | str | Unset
        if isinstance(self.mission_run_id, Unset):
            mission_run_id = UNSET
        else:
            mission_run_id = self.mission_run_id

        error_message: None | str | Unset
        if isinstance(self.error_message, Unset):
            error_message = UNSET
        else:
            error_message = self.error_message

        duration_ms: int | None | Unset
        if isinstance(self.duration_ms, Unset):
            duration_ms = UNSET
        else:
            duration_ms = self.duration_ms

        webhook_signature_valid: bool | None | Unset
        if isinstance(self.webhook_signature_valid, Unset):
            webhook_signature_valid = UNSET
        else:
            webhook_signature_valid = self.webhook_signature_valid

        fired_at: None | str | Unset
        if isinstance(self.fired_at, Unset):
            fired_at = UNSET
        elif isinstance(self.fired_at, datetime.datetime):
            fired_at = self.fired_at.isoformat()
        else:
            fired_at = self.fired_at

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "id": id,
                "trigger_id": trigger_id,
                "status": status,
                "trigger_type": trigger_type,
            }
        )
        if mission_run_id is not UNSET:
            field_dict["mission_run_id"] = mission_run_id
        if error_message is not UNSET:
            field_dict["error_message"] = error_message
        if duration_ms is not UNSET:
            field_dict["duration_ms"] = duration_ms
        if webhook_signature_valid is not UNSET:
            field_dict["webhook_signature_valid"] = webhook_signature_valid
        if fired_at is not UNSET:
            field_dict["fired_at"] = fired_at

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        id = d.pop("id")

        trigger_id = d.pop("trigger_id")

        status = d.pop("status")

        trigger_type = d.pop("trigger_type")

        def _parse_mission_run_id(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        mission_run_id = _parse_mission_run_id(d.pop("mission_run_id", UNSET))

        def _parse_error_message(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        error_message = _parse_error_message(d.pop("error_message", UNSET))

        def _parse_duration_ms(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        duration_ms = _parse_duration_ms(d.pop("duration_ms", UNSET))

        def _parse_webhook_signature_valid(data: object) -> bool | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(bool | None | Unset, data)

        webhook_signature_valid = _parse_webhook_signature_valid(d.pop("webhook_signature_valid", UNSET))

        def _parse_fired_at(data: object) -> datetime.datetime | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                fired_at_type_0 = isoparse(data)

                return fired_at_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(datetime.datetime | None | Unset, data)

        fired_at = _parse_fired_at(d.pop("fired_at", UNSET))

        trigger_log_response = cls(
            id=id,
            trigger_id=trigger_id,
            status=status,
            trigger_type=trigger_type,
            mission_run_id=mission_run_id,
            error_message=error_message,
            duration_ms=duration_ms,
            webhook_signature_valid=webhook_signature_valid,
            fired_at=fired_at,
        )

        trigger_log_response.additional_properties = d
        return trigger_log_response

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
