from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.episode_response import EpisodeResponse


T = TypeVar("T", bound="RetrieveResponse")


@_attrs_define
class RetrieveResponse:
    """Response for POST /episodes/retrieve.

    Attributes:
        episodes (list[EpisodeResponse]):
        count (int):
        capped (bool): True if results were capped at k=5
    """

    episodes: list[EpisodeResponse]
    count: int
    capped: bool
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        episodes = []
        for episodes_item_data in self.episodes:
            episodes_item = episodes_item_data.to_dict()
            episodes.append(episodes_item)

        count = self.count

        capped = self.capped

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "episodes": episodes,
                "count": count,
                "capped": capped,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.episode_response import EpisodeResponse

        d = dict(src_dict)
        episodes = []
        _episodes = d.pop("episodes")
        for episodes_item_data in _episodes:
            episodes_item = EpisodeResponse.from_dict(episodes_item_data)

            episodes.append(episodes_item)

        count = d.pop("count")

        capped = d.pop("capped")

        retrieve_response = cls(
            episodes=episodes,
            count=count,
            capped=capped,
        )

        retrieve_response.additional_properties = d
        return retrieve_response

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
