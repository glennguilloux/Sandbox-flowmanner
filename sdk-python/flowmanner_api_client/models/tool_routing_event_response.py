from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.tool_routing_event_response_payload_type_0 import ToolRoutingEventResponsePayloadType0


T = TypeVar("T", bound="ToolRoutingEventResponse")


@_attrs_define
class ToolRoutingEventResponse:
    """Single routing audit event.

    Attributes:
        id (None | str | Unset):
        sequence (int | None | Unset):
        type_ (None | str | Unset):
        payload (None | ToolRoutingEventResponsePayloadType0 | Unset):
        actor (None | str | Unset):
        timestamp (None | str | Unset):
    """

    id: None | str | Unset = UNSET
    sequence: int | None | Unset = UNSET
    type_: None | str | Unset = UNSET
    payload: None | ToolRoutingEventResponsePayloadType0 | Unset = UNSET
    actor: None | str | Unset = UNSET
    timestamp: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.tool_routing_event_response_payload_type_0 import ToolRoutingEventResponsePayloadType0

        id: None | str | Unset
        if isinstance(self.id, Unset):
            id = UNSET
        else:
            id = self.id

        sequence: int | None | Unset
        if isinstance(self.sequence, Unset):
            sequence = UNSET
        else:
            sequence = self.sequence

        type_: None | str | Unset
        if isinstance(self.type_, Unset):
            type_ = UNSET
        else:
            type_ = self.type_

        payload: dict[str, Any] | None | Unset
        if isinstance(self.payload, Unset):
            payload = UNSET
        elif isinstance(self.payload, ToolRoutingEventResponsePayloadType0):
            payload = self.payload.to_dict()
        else:
            payload = self.payload

        actor: None | str | Unset
        if isinstance(self.actor, Unset):
            actor = UNSET
        else:
            actor = self.actor

        timestamp: None | str | Unset
        if isinstance(self.timestamp, Unset):
            timestamp = UNSET
        else:
            timestamp = self.timestamp

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if id is not UNSET:
            field_dict["id"] = id
        if sequence is not UNSET:
            field_dict["sequence"] = sequence
        if type_ is not UNSET:
            field_dict["type"] = type_
        if payload is not UNSET:
            field_dict["payload"] = payload
        if actor is not UNSET:
            field_dict["actor"] = actor
        if timestamp is not UNSET:
            field_dict["timestamp"] = timestamp

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.tool_routing_event_response_payload_type_0 import ToolRoutingEventResponsePayloadType0

        d = dict(src_dict)

        def _parse_id(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        id = _parse_id(d.pop("id", UNSET))

        def _parse_sequence(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        sequence = _parse_sequence(d.pop("sequence", UNSET))

        def _parse_type_(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        type_ = _parse_type_(d.pop("type", UNSET))

        def _parse_payload(data: object) -> None | ToolRoutingEventResponsePayloadType0 | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                payload_type_0 = ToolRoutingEventResponsePayloadType0.from_dict(data)

                return payload_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | ToolRoutingEventResponsePayloadType0 | Unset, data)

        payload = _parse_payload(d.pop("payload", UNSET))

        def _parse_actor(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        actor = _parse_actor(d.pop("actor", UNSET))

        def _parse_timestamp(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        timestamp = _parse_timestamp(d.pop("timestamp", UNSET))

        tool_routing_event_response = cls(
            id=id,
            sequence=sequence,
            type_=type_,
            payload=payload,
            actor=actor,
            timestamp=timestamp,
        )

        tool_routing_event_response.additional_properties = d
        return tool_routing_event_response

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
