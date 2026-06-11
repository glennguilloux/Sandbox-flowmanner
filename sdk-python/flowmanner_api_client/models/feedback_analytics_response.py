from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.feedback_analytics_response_score_trend_item import (
        FeedbackAnalyticsResponseScoreTrendItem,
    )
    from ..models.feedback_analytics_response_top_patterns_item import (
        FeedbackAnalyticsResponseTopPatternsItem,
    )


T = TypeVar("T", bound="FeedbackAnalyticsResponse")


@_attrs_define
class FeedbackAnalyticsResponse:
    """
    Attributes:
        total_reports (int):
        avg_overall_score (float):
        avg_efficiency_score (float | None | Unset):
        avg_quality_score (float | None | Unset):
        top_patterns (list[FeedbackAnalyticsResponseTopPatternsItem] | Unset):
        score_trend (list[FeedbackAnalyticsResponseScoreTrendItem] | Unset):
    """

    total_reports: int
    avg_overall_score: float
    avg_efficiency_score: float | None | Unset = UNSET
    avg_quality_score: float | None | Unset = UNSET
    top_patterns: list[FeedbackAnalyticsResponseTopPatternsItem] | Unset = UNSET
    score_trend: list[FeedbackAnalyticsResponseScoreTrendItem] | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        total_reports = self.total_reports

        avg_overall_score = self.avg_overall_score

        avg_efficiency_score: float | None | Unset
        if isinstance(self.avg_efficiency_score, Unset):
            avg_efficiency_score = UNSET
        else:
            avg_efficiency_score = self.avg_efficiency_score

        avg_quality_score: float | None | Unset
        if isinstance(self.avg_quality_score, Unset):
            avg_quality_score = UNSET
        else:
            avg_quality_score = self.avg_quality_score

        top_patterns: list[dict[str, Any]] | Unset = UNSET
        if not isinstance(self.top_patterns, Unset):
            top_patterns = []
            for top_patterns_item_data in self.top_patterns:
                top_patterns_item = top_patterns_item_data.to_dict()
                top_patterns.append(top_patterns_item)

        score_trend: list[dict[str, Any]] | Unset = UNSET
        if not isinstance(self.score_trend, Unset):
            score_trend = []
            for score_trend_item_data in self.score_trend:
                score_trend_item = score_trend_item_data.to_dict()
                score_trend.append(score_trend_item)

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "total_reports": total_reports,
                "avg_overall_score": avg_overall_score,
            }
        )
        if avg_efficiency_score is not UNSET:
            field_dict["avg_efficiency_score"] = avg_efficiency_score
        if avg_quality_score is not UNSET:
            field_dict["avg_quality_score"] = avg_quality_score
        if top_patterns is not UNSET:
            field_dict["top_patterns"] = top_patterns
        if score_trend is not UNSET:
            field_dict["score_trend"] = score_trend

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.feedback_analytics_response_score_trend_item import (
            FeedbackAnalyticsResponseScoreTrendItem,
        )
        from ..models.feedback_analytics_response_top_patterns_item import (
            FeedbackAnalyticsResponseTopPatternsItem,
        )

        d = dict(src_dict)
        total_reports = d.pop("total_reports")

        avg_overall_score = d.pop("avg_overall_score")

        def _parse_avg_efficiency_score(data: object) -> float | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(float | None | Unset, data)

        avg_efficiency_score = _parse_avg_efficiency_score(d.pop("avg_efficiency_score", UNSET))

        def _parse_avg_quality_score(data: object) -> float | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(float | None | Unset, data)

        avg_quality_score = _parse_avg_quality_score(d.pop("avg_quality_score", UNSET))

        _top_patterns = d.pop("top_patterns", UNSET)
        top_patterns: list[FeedbackAnalyticsResponseTopPatternsItem] | Unset = UNSET
        if _top_patterns is not UNSET:
            top_patterns = []
            for top_patterns_item_data in _top_patterns:
                top_patterns_item = FeedbackAnalyticsResponseTopPatternsItem.from_dict(top_patterns_item_data)

                top_patterns.append(top_patterns_item)

        _score_trend = d.pop("score_trend", UNSET)
        score_trend: list[FeedbackAnalyticsResponseScoreTrendItem] | Unset = UNSET
        if _score_trend is not UNSET:
            score_trend = []
            for score_trend_item_data in _score_trend:
                score_trend_item = FeedbackAnalyticsResponseScoreTrendItem.from_dict(score_trend_item_data)

                score_trend.append(score_trend_item)

        feedback_analytics_response = cls(
            total_reports=total_reports,
            avg_overall_score=avg_overall_score,
            avg_efficiency_score=avg_efficiency_score,
            avg_quality_score=avg_quality_score,
            top_patterns=top_patterns,
            score_trend=score_trend,
        )

        feedback_analytics_response.additional_properties = d
        return feedback_analytics_response

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
