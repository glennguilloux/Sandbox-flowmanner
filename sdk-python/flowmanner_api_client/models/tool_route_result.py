from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.tool_route_result_mode import ToolRouteResultMode
from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.tool_route_result_reasons import ToolRouteResultReasons
    from ..models.tool_route_result_tools_item import ToolRouteResultToolsItem
    from ..models.tool_score import ToolScore


T = TypeVar("T", bound="ToolRouteResult")


@_attrs_define
class ToolRouteResult:
    """Result of a tool routing decision.

    Attributes:
        mode (ToolRouteResultMode): 'sparse' when confidence is above threshold, 'fallback-full-registry' otherwise
        top_score (float): Highest score among all candidates considered
        candidates_considered (int): Total number of tools scored
        candidates_returned (int): Number of tools in the final candidate set
        task_text_hash (str): SHA-256 hex digest of normalized task text (for audit privacy)
        tools (list[ToolRouteResultToolsItem] | Unset): Selected ToolDefinition dicts (to_dict() output)
        reasons (ToolRouteResultReasons | Unset): Per-tool_id reason string for why it was included
        scores (list[ToolScore] | Unset): Per-tool score details (for debugging/admin)
    """

    mode: ToolRouteResultMode
    top_score: float
    candidates_considered: int
    candidates_returned: int
    task_text_hash: str
    tools: list[ToolRouteResultToolsItem] | Unset = UNSET
    reasons: ToolRouteResultReasons | Unset = UNSET
    scores: list[ToolScore] | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        mode = self.mode.value

        top_score = self.top_score

        candidates_considered = self.candidates_considered

        candidates_returned = self.candidates_returned

        task_text_hash = self.task_text_hash

        tools: list[dict[str, Any]] | Unset = UNSET
        if not isinstance(self.tools, Unset):
            tools = []
            for tools_item_data in self.tools:
                tools_item = tools_item_data.to_dict()
                tools.append(tools_item)

        reasons: dict[str, Any] | Unset = UNSET
        if not isinstance(self.reasons, Unset):
            reasons = self.reasons.to_dict()

        scores: list[dict[str, Any]] | Unset = UNSET
        if not isinstance(self.scores, Unset):
            scores = []
            for scores_item_data in self.scores:
                scores_item = scores_item_data.to_dict()
                scores.append(scores_item)

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "mode": mode,
                "top_score": top_score,
                "candidates_considered": candidates_considered,
                "candidates_returned": candidates_returned,
                "task_text_hash": task_text_hash,
            }
        )
        if tools is not UNSET:
            field_dict["tools"] = tools
        if reasons is not UNSET:
            field_dict["reasons"] = reasons
        if scores is not UNSET:
            field_dict["scores"] = scores

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.tool_route_result_reasons import ToolRouteResultReasons
        from ..models.tool_route_result_tools_item import ToolRouteResultToolsItem
        from ..models.tool_score import ToolScore

        d = dict(src_dict)
        mode = ToolRouteResultMode(d.pop("mode"))

        top_score = d.pop("top_score")

        candidates_considered = d.pop("candidates_considered")

        candidates_returned = d.pop("candidates_returned")

        task_text_hash = d.pop("task_text_hash")

        _tools = d.pop("tools", UNSET)
        tools: list[ToolRouteResultToolsItem] | Unset = UNSET
        if _tools is not UNSET:
            tools = []
            for tools_item_data in _tools:
                tools_item = ToolRouteResultToolsItem.from_dict(tools_item_data)

                tools.append(tools_item)

        _reasons = d.pop("reasons", UNSET)
        reasons: ToolRouteResultReasons | Unset
        if isinstance(_reasons, Unset):
            reasons = UNSET
        else:
            reasons = ToolRouteResultReasons.from_dict(_reasons)

        _scores = d.pop("scores", UNSET)
        scores: list[ToolScore] | Unset = UNSET
        if _scores is not UNSET:
            scores = []
            for scores_item_data in _scores:
                scores_item = ToolScore.from_dict(scores_item_data)

                scores.append(scores_item)

        tool_route_result = cls(
            mode=mode,
            top_score=top_score,
            candidates_considered=candidates_considered,
            candidates_returned=candidates_returned,
            task_text_hash=task_text_hash,
            tools=tools,
            reasons=reasons,
            scores=scores,
        )

        tool_route_result.additional_properties = d
        return tool_route_result

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
