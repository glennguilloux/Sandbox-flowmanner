from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="EpisodeResponse")


@_attrs_define
class EpisodeResponse:
    """Single episode in a response.

    Attributes:
        id (str):
        mission_id (None | str | Unset):
        step_type (None | str | Unset):
        outcome (None | str | Unset):
        cost_bucket (None | str | Unset):
        hitl_outcome (None | str | Unset):
        retrieval_text (None | str | Unset):
        combined_score (float | None | Unset):
        created_at (None | str | Unset):
    """

    id: str
    mission_id: None | str | Unset = UNSET
    step_type: None | str | Unset = UNSET
    outcome: None | str | Unset = UNSET
    cost_bucket: None | str | Unset = UNSET
    hitl_outcome: None | str | Unset = UNSET
    retrieval_text: None | str | Unset = UNSET
    combined_score: float | None | Unset = UNSET
    created_at: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        id = self.id

        mission_id: None | str | Unset
        if isinstance(self.mission_id, Unset):
            mission_id = UNSET
        else:
            mission_id = self.mission_id

        step_type: None | str | Unset
        if isinstance(self.step_type, Unset):
            step_type = UNSET
        else:
            step_type = self.step_type

        outcome: None | str | Unset
        if isinstance(self.outcome, Unset):
            outcome = UNSET
        else:
            outcome = self.outcome

        cost_bucket: None | str | Unset
        if isinstance(self.cost_bucket, Unset):
            cost_bucket = UNSET
        else:
            cost_bucket = self.cost_bucket

        hitl_outcome: None | str | Unset
        if isinstance(self.hitl_outcome, Unset):
            hitl_outcome = UNSET
        else:
            hitl_outcome = self.hitl_outcome

        retrieval_text: None | str | Unset
        if isinstance(self.retrieval_text, Unset):
            retrieval_text = UNSET
        else:
            retrieval_text = self.retrieval_text

        combined_score: float | None | Unset
        if isinstance(self.combined_score, Unset):
            combined_score = UNSET
        else:
            combined_score = self.combined_score

        created_at: None | str | Unset
        if isinstance(self.created_at, Unset):
            created_at = UNSET
        else:
            created_at = self.created_at

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "id": id,
            }
        )
        if mission_id is not UNSET:
            field_dict["mission_id"] = mission_id
        if step_type is not UNSET:
            field_dict["step_type"] = step_type
        if outcome is not UNSET:
            field_dict["outcome"] = outcome
        if cost_bucket is not UNSET:
            field_dict["cost_bucket"] = cost_bucket
        if hitl_outcome is not UNSET:
            field_dict["hitl_outcome"] = hitl_outcome
        if retrieval_text is not UNSET:
            field_dict["retrieval_text"] = retrieval_text
        if combined_score is not UNSET:
            field_dict["combined_score"] = combined_score
        if created_at is not UNSET:
            field_dict["created_at"] = created_at

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        id = d.pop("id")

        def _parse_mission_id(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        mission_id = _parse_mission_id(d.pop("mission_id", UNSET))

        def _parse_step_type(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        step_type = _parse_step_type(d.pop("step_type", UNSET))

        def _parse_outcome(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        outcome = _parse_outcome(d.pop("outcome", UNSET))

        def _parse_cost_bucket(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        cost_bucket = _parse_cost_bucket(d.pop("cost_bucket", UNSET))

        def _parse_hitl_outcome(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        hitl_outcome = _parse_hitl_outcome(d.pop("hitl_outcome", UNSET))

        def _parse_retrieval_text(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        retrieval_text = _parse_retrieval_text(d.pop("retrieval_text", UNSET))

        def _parse_combined_score(data: object) -> float | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(float | None | Unset, data)

        combined_score = _parse_combined_score(d.pop("combined_score", UNSET))

        def _parse_created_at(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        created_at = _parse_created_at(d.pop("created_at", UNSET))

        episode_response = cls(
            id=id,
            mission_id=mission_id,
            step_type=step_type,
            outcome=outcome,
            cost_bucket=cost_bucket,
            hitl_outcome=hitl_outcome,
            retrieval_text=retrieval_text,
            combined_score=combined_score,
            created_at=created_at,
        )

        episode_response.additional_properties = d
        return episode_response

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
