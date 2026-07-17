from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="VoiceSynthesizeResponse")


@_attrs_define
class VoiceSynthesizeResponse:
    """Response from TTS synthesis.

    Attributes:
        audio_url (None | str | Unset):
        audio_base64 (None | str | Unset):
        format_ (str | Unset):  Default: 'mp3'.
        duration_seconds (float | Unset):  Default: 0.0.
        voice_id (str | Unset):  Default: ''.
    """

    audio_url: None | str | Unset = UNSET
    audio_base64: None | str | Unset = UNSET
    format_: str | Unset = "mp3"
    duration_seconds: float | Unset = 0.0
    voice_id: str | Unset = ""
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        audio_url: None | str | Unset
        if isinstance(self.audio_url, Unset):
            audio_url = UNSET
        else:
            audio_url = self.audio_url

        audio_base64: None | str | Unset
        if isinstance(self.audio_base64, Unset):
            audio_base64 = UNSET
        else:
            audio_base64 = self.audio_base64

        format_ = self.format_

        duration_seconds = self.duration_seconds

        voice_id = self.voice_id

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if audio_url is not UNSET:
            field_dict["audio_url"] = audio_url
        if audio_base64 is not UNSET:
            field_dict["audio_base64"] = audio_base64
        if format_ is not UNSET:
            field_dict["format"] = format_
        if duration_seconds is not UNSET:
            field_dict["duration_seconds"] = duration_seconds
        if voice_id is not UNSET:
            field_dict["voice_id"] = voice_id

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)

        def _parse_audio_url(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        audio_url = _parse_audio_url(d.pop("audio_url", UNSET))

        def _parse_audio_base64(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        audio_base64 = _parse_audio_base64(d.pop("audio_base64", UNSET))

        format_ = d.pop("format", UNSET)

        duration_seconds = d.pop("duration_seconds", UNSET)

        voice_id = d.pop("voice_id", UNSET)

        voice_synthesize_response = cls(
            audio_url=audio_url,
            audio_base64=audio_base64,
            format_=format_,
            duration_seconds=duration_seconds,
            voice_id=voice_id,
        )

        voice_synthesize_response.additional_properties = d
        return voice_synthesize_response

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
