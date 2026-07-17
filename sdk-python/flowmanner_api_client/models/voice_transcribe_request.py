from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="VoiceTranscribeRequest")


@_attrs_define
class VoiceTranscribeRequest:
    """Request to transcribe audio to text.

    Attributes:
        audio_data (None | str | Unset): Base64-encoded audio
        audio_url (None | str | Unset): URL to audio file
        language (None | str | Unset):
        model (str | Unset):  Default: 'whisper-1'.
    """

    audio_data: None | str | Unset = UNSET
    audio_url: None | str | Unset = UNSET
    language: None | str | Unset = UNSET
    model: str | Unset = "whisper-1"
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        audio_data: None | str | Unset
        if isinstance(self.audio_data, Unset):
            audio_data = UNSET
        else:
            audio_data = self.audio_data

        audio_url: None | str | Unset
        if isinstance(self.audio_url, Unset):
            audio_url = UNSET
        else:
            audio_url = self.audio_url

        language: None | str | Unset
        if isinstance(self.language, Unset):
            language = UNSET
        else:
            language = self.language

        model = self.model

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if audio_data is not UNSET:
            field_dict["audio_data"] = audio_data
        if audio_url is not UNSET:
            field_dict["audio_url"] = audio_url
        if language is not UNSET:
            field_dict["language"] = language
        if model is not UNSET:
            field_dict["model"] = model

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)

        def _parse_audio_data(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        audio_data = _parse_audio_data(d.pop("audio_data", UNSET))

        def _parse_audio_url(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        audio_url = _parse_audio_url(d.pop("audio_url", UNSET))

        def _parse_language(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        language = _parse_language(d.pop("language", UNSET))

        model = d.pop("model", UNSET)

        voice_transcribe_request = cls(
            audio_data=audio_data,
            audio_url=audio_url,
            language=language,
            model=model,
        )

        voice_transcribe_request.additional_properties = d
        return voice_transcribe_request

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
