from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="VoiceSynthesizeRequest")


@_attrs_define
class VoiceSynthesizeRequest:
    """Request to synthesize text to speech.

    Attributes:
        text (str):
        voice_id (str | Unset):  Default: '21m00Tcm4TlvDq8ikWAM'.
    """

    text: str
    voice_id: str | Unset = "21m00Tcm4TlvDq8ikWAM"
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        text = self.text

        voice_id = self.voice_id

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "text": text,
            }
        )
        if voice_id is not UNSET:
            field_dict["voice_id"] = voice_id

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        text = d.pop("text")

        voice_id = d.pop("voice_id", UNSET)

        voice_synthesize_request = cls(
            text=text,
            voice_id=voice_id,
        )

        voice_synthesize_request.additional_properties = d
        return voice_synthesize_request

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
