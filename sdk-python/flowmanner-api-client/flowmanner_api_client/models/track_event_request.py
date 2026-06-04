from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.track_event_request_properties_type_0 import TrackEventRequestPropertiesType0


T = TypeVar("T", bound="TrackEventRequest")


@_attrs_define
class TrackEventRequest:
    """
    Attributes:
        user_id (str):
        event_type (str):
        properties (None | TrackEventRequestPropertiesType0 | Unset):
        session_id (None | str | Unset):
    """

    user_id: str
    event_type: str
    properties: None | TrackEventRequestPropertiesType0 | Unset = UNSET
    session_id: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.track_event_request_properties_type_0 import TrackEventRequestPropertiesType0

        user_id = self.user_id

        event_type = self.event_type

        properties: dict[str, Any] | None | Unset
        if isinstance(self.properties, Unset):
            properties = UNSET
        elif isinstance(self.properties, TrackEventRequestPropertiesType0):
            properties = self.properties.to_dict()
        else:
            properties = self.properties

        session_id: None | str | Unset
        if isinstance(self.session_id, Unset):
            session_id = UNSET
        else:
            session_id = self.session_id

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "user_id": user_id,
                "event_type": event_type,
            }
        )
        if properties is not UNSET:
            field_dict["properties"] = properties
        if session_id is not UNSET:
            field_dict["session_id"] = session_id

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.track_event_request_properties_type_0 import TrackEventRequestPropertiesType0

        d = dict(src_dict)
        user_id = d.pop("user_id")

        event_type = d.pop("event_type")

        def _parse_properties(data: object) -> None | TrackEventRequestPropertiesType0 | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                properties_type_0 = TrackEventRequestPropertiesType0.from_dict(data)

                return properties_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | TrackEventRequestPropertiesType0 | Unset, data)

        properties = _parse_properties(d.pop("properties", UNSET))

        def _parse_session_id(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        session_id = _parse_session_id(d.pop("session_id", UNSET))

        track_event_request = cls(
            user_id=user_id,
            event_type=event_type,
            properties=properties,
            session_id=session_id,
        )

        track_event_request.additional_properties = d
        return track_event_request

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
