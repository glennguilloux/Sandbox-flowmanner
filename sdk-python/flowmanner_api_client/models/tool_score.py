from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.tool_score_components import ToolScoreComponents


T = TypeVar("T", bound="ToolScore")


@_attrs_define
class ToolScore:
    """Score breakdown for a single tool against a task.

    Attributes:
        tool_id (str): Tool identifier
        score (float): Final weighted score
        components (ToolScoreComponents | Unset): Score components: text_similarity, category_match, memory_hint,
            permission_ok
        reasons (list[str] | Unset): Human-readable reasons for the score
    """

    tool_id: str
    score: float
    components: ToolScoreComponents | Unset = UNSET
    reasons: list[str] | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        tool_id = self.tool_id

        score = self.score

        components: dict[str, Any] | Unset = UNSET
        if not isinstance(self.components, Unset):
            components = self.components.to_dict()

        reasons: list[str] | Unset = UNSET
        if not isinstance(self.reasons, Unset):
            reasons = self.reasons

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "tool_id": tool_id,
                "score": score,
            }
        )
        if components is not UNSET:
            field_dict["components"] = components
        if reasons is not UNSET:
            field_dict["reasons"] = reasons

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.tool_score_components import ToolScoreComponents

        d = dict(src_dict)
        tool_id = d.pop("tool_id")

        score = d.pop("score")

        _components = d.pop("components", UNSET)
        components: ToolScoreComponents | Unset
        if isinstance(_components, Unset):
            components = UNSET
        else:
            components = ToolScoreComponents.from_dict(_components)

        reasons = cast(list[str], d.pop("reasons", UNSET))

        tool_score = cls(
            tool_id=tool_id,
            score=score,
            components=components,
            reasons=reasons,
        )

        tool_score.additional_properties = d
        return tool_score

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
