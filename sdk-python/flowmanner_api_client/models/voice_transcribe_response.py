from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.voice_transcribe_response_segments_item import VoiceTranscribeResponseSegmentsItem


T = TypeVar("T", bound="VoiceTranscribeResponse")


@_attrs_define
class VoiceTranscribeResponse:
    """Response from voice transcription.

    Attributes:
        text (str):
        language (None | str | Unset):
        duration_seconds (float | Unset):  Default: 0.0.
        segments (list[VoiceTranscribeResponseSegmentsItem] | Unset):
    """

    text: str
    language: None | str | Unset = UNSET
    duration_seconds: float | Unset = 0.0
    segments: list[VoiceTranscribeResponseSegmentsItem] | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        text = self.text

        language: None | str | Unset
        if isinstance(self.language, Unset):
            language = UNSET
        else:
            language = self.language

        duration_seconds = self.duration_seconds

        segments: list[dict[str, Any]] | Unset = UNSET
        if not isinstance(self.segments, Unset):
            segments = []
            for segments_item_data in self.segments:
                segments_item = segments_item_data.to_dict()
                segments.append(segments_item)

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "text": text,
            }
        )
        if language is not UNSET:
            field_dict["language"] = language
        if duration_seconds is not UNSET:
            field_dict["duration_seconds"] = duration_seconds
        if segments is not UNSET:
            field_dict["segments"] = segments

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.voice_transcribe_response_segments_item import VoiceTranscribeResponseSegmentsItem

        d = dict(src_dict)
        text = d.pop("text")

        def _parse_language(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        language = _parse_language(d.pop("language", UNSET))

        duration_seconds = d.pop("duration_seconds", UNSET)

        _segments = d.pop("segments", UNSET)
        segments: list[VoiceTranscribeResponseSegmentsItem] | Unset = UNSET
        if _segments is not UNSET:
            segments = []
            for segments_item_data in _segments:
                segments_item = VoiceTranscribeResponseSegmentsItem.from_dict(segments_item_data)

                segments.append(segments_item)

        voice_transcribe_response = cls(
            text=text,
            language=language,
            duration_seconds=duration_seconds,
            segments=segments,
        )

        voice_transcribe_response.additional_properties = d
        return voice_transcribe_response

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
