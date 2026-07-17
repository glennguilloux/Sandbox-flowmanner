from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.clarify_request_resolution_payload_type_0 import ClarifyRequestResolutionPayloadType0


T = TypeVar("T", bound="ClarifyRequest")


@_attrs_define
class ClarifyRequest:
    """
    Attributes:
        response_text (str):
        resolution_payload (ClarifyRequestResolutionPayloadType0 | None | Unset):
    """

    response_text: str
    resolution_payload: ClarifyRequestResolutionPayloadType0 | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.clarify_request_resolution_payload_type_0 import ClarifyRequestResolutionPayloadType0

        response_text = self.response_text

        resolution_payload: dict[str, Any] | None | Unset
        if isinstance(self.resolution_payload, Unset):
            resolution_payload = UNSET
        elif isinstance(self.resolution_payload, ClarifyRequestResolutionPayloadType0):
            resolution_payload = self.resolution_payload.to_dict()
        else:
            resolution_payload = self.resolution_payload

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "response_text": response_text,
            }
        )
        if resolution_payload is not UNSET:
            field_dict["resolution_payload"] = resolution_payload

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.clarify_request_resolution_payload_type_0 import ClarifyRequestResolutionPayloadType0

        d = dict(src_dict)
        response_text = d.pop("response_text")

        def _parse_resolution_payload(data: object) -> ClarifyRequestResolutionPayloadType0 | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                resolution_payload_type_0 = ClarifyRequestResolutionPayloadType0.from_dict(data)

                return resolution_payload_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(ClarifyRequestResolutionPayloadType0 | None | Unset, data)

        resolution_payload = _parse_resolution_payload(d.pop("resolution_payload", UNSET))

        clarify_request = cls(
            response_text=response_text,
            resolution_payload=resolution_payload,
        )

        clarify_request.additional_properties = d
        return clarify_request

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
