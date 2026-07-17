from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.fire_request_trigger_payload_type_0 import FireRequestTriggerPayloadType0


T = TypeVar("T", bound="FireRequest")


@_attrs_define
class FireRequest:
    """Request body for ``POST /programs/{id}/fire``.

    ``trigger_payload`` is optional — manual fires need no payload, but
    webhook replays and cron re-fires do.

        Attributes:
            trigger_payload (FireRequestTriggerPayloadType0 | None | Unset):
    """

    trigger_payload: FireRequestTriggerPayloadType0 | None | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        from ..models.fire_request_trigger_payload_type_0 import FireRequestTriggerPayloadType0

        trigger_payload: dict[str, Any] | None | Unset
        if isinstance(self.trigger_payload, Unset):
            trigger_payload = UNSET
        elif isinstance(self.trigger_payload, FireRequestTriggerPayloadType0):
            trigger_payload = self.trigger_payload.to_dict()
        else:
            trigger_payload = self.trigger_payload

        field_dict: dict[str, Any] = {}

        field_dict.update({})
        if trigger_payload is not UNSET:
            field_dict["trigger_payload"] = trigger_payload

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.fire_request_trigger_payload_type_0 import FireRequestTriggerPayloadType0

        d = dict(src_dict)

        def _parse_trigger_payload(data: object) -> FireRequestTriggerPayloadType0 | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                trigger_payload_type_0 = FireRequestTriggerPayloadType0.from_dict(data)

                return trigger_payload_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(FireRequestTriggerPayloadType0 | None | Unset, data)

        trigger_payload = _parse_trigger_payload(d.pop("trigger_payload", UNSET))

        fire_request = cls(
            trigger_payload=trigger_payload,
        )

        return fire_request
