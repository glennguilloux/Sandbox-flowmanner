from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.resolve_request_resolution_payload_type_0 import ResolveRequestResolutionPayloadType0


T = TypeVar("T", bound="ResolveRequest")


@_attrs_define
class ResolveRequest:
    """
    Attributes:
        resolution_note (None | str | Unset):
        resolution_payload (None | ResolveRequestResolutionPayloadType0 | Unset):
    """

    resolution_note: None | str | Unset = UNSET
    resolution_payload: None | ResolveRequestResolutionPayloadType0 | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.resolve_request_resolution_payload_type_0 import ResolveRequestResolutionPayloadType0

        resolution_note: None | str | Unset
        if isinstance(self.resolution_note, Unset):
            resolution_note = UNSET
        else:
            resolution_note = self.resolution_note

        resolution_payload: dict[str, Any] | None | Unset
        if isinstance(self.resolution_payload, Unset):
            resolution_payload = UNSET
        elif isinstance(self.resolution_payload, ResolveRequestResolutionPayloadType0):
            resolution_payload = self.resolution_payload.to_dict()
        else:
            resolution_payload = self.resolution_payload

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if resolution_note is not UNSET:
            field_dict["resolution_note"] = resolution_note
        if resolution_payload is not UNSET:
            field_dict["resolution_payload"] = resolution_payload

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.resolve_request_resolution_payload_type_0 import ResolveRequestResolutionPayloadType0

        d = dict(src_dict)

        def _parse_resolution_note(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        resolution_note = _parse_resolution_note(d.pop("resolution_note", UNSET))

        def _parse_resolution_payload(data: object) -> None | ResolveRequestResolutionPayloadType0 | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                resolution_payload_type_0 = ResolveRequestResolutionPayloadType0.from_dict(data)

                return resolution_payload_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | ResolveRequestResolutionPayloadType0 | Unset, data)

        resolution_payload = _parse_resolution_payload(d.pop("resolution_payload", UNSET))

        resolve_request = cls(
            resolution_note=resolution_note,
            resolution_payload=resolution_payload,
        )

        resolve_request.additional_properties = d
        return resolve_request

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
