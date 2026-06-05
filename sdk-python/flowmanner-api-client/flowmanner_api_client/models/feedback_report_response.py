from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field
from dateutil.parser import isoparse

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.feedback_report_response_error_summary_type_0 import (
        FeedbackReportResponseErrorSummaryType0,
    )
    from ..models.feedback_report_response_strengths_type_0 import (
        FeedbackReportResponseStrengthsType0,
    )
    from ..models.feedback_report_response_suggestions_type_0 import (
        FeedbackReportResponseSuggestionsType0,
    )
    from ..models.feedback_report_response_task_analysis_type_0 import (
        FeedbackReportResponseTaskAnalysisType0,
    )
    from ..models.feedback_report_response_token_efficiency_type_0 import (
        FeedbackReportResponseTokenEfficiencyType0,
    )
    from ..models.feedback_report_response_weaknesses_type_0 import (
        FeedbackReportResponseWeaknessesType0,
    )


T = TypeVar("T", bound="FeedbackReportResponse")


@_attrs_define
class FeedbackReportResponse:
    """
    Attributes:
        id (str):
        mission_id (str):
        overall_score (float):
        efficiency_score (float | None | Unset):
        quality_score (float | None | Unset):
        strengths (FeedbackReportResponseStrengthsType0 | None | Unset):
        weaknesses (FeedbackReportResponseWeaknessesType0 | None | Unset):
        suggestions (FeedbackReportResponseSuggestionsType0 | None | Unset):
        task_analysis (FeedbackReportResponseTaskAnalysisType0 | None | Unset):
        error_summary (FeedbackReportResponseErrorSummaryType0 | None | Unset):
        token_efficiency (FeedbackReportResponseTokenEfficiencyType0 | None | Unset):
        synthesis_mode (str | Unset):  Default: 'auto'.
        status (str | Unset):  Default: 'completed'.
        created_at (datetime.datetime | None | Unset):
    """

    id: str
    mission_id: str
    overall_score: float
    efficiency_score: float | None | Unset = UNSET
    quality_score: float | None | Unset = UNSET
    strengths: FeedbackReportResponseStrengthsType0 | None | Unset = UNSET
    weaknesses: FeedbackReportResponseWeaknessesType0 | None | Unset = UNSET
    suggestions: FeedbackReportResponseSuggestionsType0 | None | Unset = UNSET
    task_analysis: FeedbackReportResponseTaskAnalysisType0 | None | Unset = UNSET
    error_summary: FeedbackReportResponseErrorSummaryType0 | None | Unset = UNSET
    token_efficiency: FeedbackReportResponseTokenEfficiencyType0 | None | Unset = UNSET
    synthesis_mode: str | Unset = "auto"
    status: str | Unset = "completed"
    created_at: datetime.datetime | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.feedback_report_response_error_summary_type_0 import (
            FeedbackReportResponseErrorSummaryType0,
        )
        from ..models.feedback_report_response_strengths_type_0 import (
            FeedbackReportResponseStrengthsType0,
        )
        from ..models.feedback_report_response_suggestions_type_0 import (
            FeedbackReportResponseSuggestionsType0,
        )
        from ..models.feedback_report_response_task_analysis_type_0 import (
            FeedbackReportResponseTaskAnalysisType0,
        )
        from ..models.feedback_report_response_token_efficiency_type_0 import (
            FeedbackReportResponseTokenEfficiencyType0,
        )
        from ..models.feedback_report_response_weaknesses_type_0 import (
            FeedbackReportResponseWeaknessesType0,
        )

        id = self.id

        mission_id = self.mission_id

        overall_score = self.overall_score

        efficiency_score: float | None | Unset
        if isinstance(self.efficiency_score, Unset):
            efficiency_score = UNSET
        else:
            efficiency_score = self.efficiency_score

        quality_score: float | None | Unset
        if isinstance(self.quality_score, Unset):
            quality_score = UNSET
        else:
            quality_score = self.quality_score

        strengths: dict[str, Any] | None | Unset
        if isinstance(self.strengths, Unset):
            strengths = UNSET
        elif isinstance(self.strengths, FeedbackReportResponseStrengthsType0):
            strengths = self.strengths.to_dict()
        else:
            strengths = self.strengths

        weaknesses: dict[str, Any] | None | Unset
        if isinstance(self.weaknesses, Unset):
            weaknesses = UNSET
        elif isinstance(self.weaknesses, FeedbackReportResponseWeaknessesType0):
            weaknesses = self.weaknesses.to_dict()
        else:
            weaknesses = self.weaknesses

        suggestions: dict[str, Any] | None | Unset
        if isinstance(self.suggestions, Unset):
            suggestions = UNSET
        elif isinstance(self.suggestions, FeedbackReportResponseSuggestionsType0):
            suggestions = self.suggestions.to_dict()
        else:
            suggestions = self.suggestions

        task_analysis: dict[str, Any] | None | Unset
        if isinstance(self.task_analysis, Unset):
            task_analysis = UNSET
        elif isinstance(self.task_analysis, FeedbackReportResponseTaskAnalysisType0):
            task_analysis = self.task_analysis.to_dict()
        else:
            task_analysis = self.task_analysis

        error_summary: dict[str, Any] | None | Unset
        if isinstance(self.error_summary, Unset):
            error_summary = UNSET
        elif isinstance(self.error_summary, FeedbackReportResponseErrorSummaryType0):
            error_summary = self.error_summary.to_dict()
        else:
            error_summary = self.error_summary

        token_efficiency: dict[str, Any] | None | Unset
        if isinstance(self.token_efficiency, Unset):
            token_efficiency = UNSET
        elif isinstance(
            self.token_efficiency, FeedbackReportResponseTokenEfficiencyType0
        ):
            token_efficiency = self.token_efficiency.to_dict()
        else:
            token_efficiency = self.token_efficiency

        synthesis_mode = self.synthesis_mode

        status = self.status

        created_at: None | str | Unset
        if isinstance(self.created_at, Unset):
            created_at = UNSET
        elif isinstance(self.created_at, datetime.datetime):
            created_at = self.created_at.isoformat()
        else:
            created_at = self.created_at

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "id": id,
                "mission_id": mission_id,
                "overall_score": overall_score,
            }
        )
        if efficiency_score is not UNSET:
            field_dict["efficiency_score"] = efficiency_score
        if quality_score is not UNSET:
            field_dict["quality_score"] = quality_score
        if strengths is not UNSET:
            field_dict["strengths"] = strengths
        if weaknesses is not UNSET:
            field_dict["weaknesses"] = weaknesses
        if suggestions is not UNSET:
            field_dict["suggestions"] = suggestions
        if task_analysis is not UNSET:
            field_dict["task_analysis"] = task_analysis
        if error_summary is not UNSET:
            field_dict["error_summary"] = error_summary
        if token_efficiency is not UNSET:
            field_dict["token_efficiency"] = token_efficiency
        if synthesis_mode is not UNSET:
            field_dict["synthesis_mode"] = synthesis_mode
        if status is not UNSET:
            field_dict["status"] = status
        if created_at is not UNSET:
            field_dict["created_at"] = created_at

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.feedback_report_response_error_summary_type_0 import (
            FeedbackReportResponseErrorSummaryType0,
        )
        from ..models.feedback_report_response_strengths_type_0 import (
            FeedbackReportResponseStrengthsType0,
        )
        from ..models.feedback_report_response_suggestions_type_0 import (
            FeedbackReportResponseSuggestionsType0,
        )
        from ..models.feedback_report_response_task_analysis_type_0 import (
            FeedbackReportResponseTaskAnalysisType0,
        )
        from ..models.feedback_report_response_token_efficiency_type_0 import (
            FeedbackReportResponseTokenEfficiencyType0,
        )
        from ..models.feedback_report_response_weaknesses_type_0 import (
            FeedbackReportResponseWeaknessesType0,
        )

        d = dict(src_dict)
        id = d.pop("id")

        mission_id = d.pop("mission_id")

        overall_score = d.pop("overall_score")

        def _parse_efficiency_score(data: object) -> float | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(float | None | Unset, data)

        efficiency_score = _parse_efficiency_score(d.pop("efficiency_score", UNSET))

        def _parse_quality_score(data: object) -> float | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(float | None | Unset, data)

        quality_score = _parse_quality_score(d.pop("quality_score", UNSET))

        def _parse_strengths(
            data: object,
        ) -> FeedbackReportResponseStrengthsType0 | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                strengths_type_0 = FeedbackReportResponseStrengthsType0.from_dict(data)

                return strengths_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(FeedbackReportResponseStrengthsType0 | None | Unset, data)

        strengths = _parse_strengths(d.pop("strengths", UNSET))

        def _parse_weaknesses(
            data: object,
        ) -> FeedbackReportResponseWeaknessesType0 | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                weaknesses_type_0 = FeedbackReportResponseWeaknessesType0.from_dict(
                    data
                )

                return weaknesses_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(FeedbackReportResponseWeaknessesType0 | None | Unset, data)

        weaknesses = _parse_weaknesses(d.pop("weaknesses", UNSET))

        def _parse_suggestions(
            data: object,
        ) -> FeedbackReportResponseSuggestionsType0 | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                suggestions_type_0 = FeedbackReportResponseSuggestionsType0.from_dict(
                    data
                )

                return suggestions_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(FeedbackReportResponseSuggestionsType0 | None | Unset, data)

        suggestions = _parse_suggestions(d.pop("suggestions", UNSET))

        def _parse_task_analysis(
            data: object,
        ) -> FeedbackReportResponseTaskAnalysisType0 | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                task_analysis_type_0 = (
                    FeedbackReportResponseTaskAnalysisType0.from_dict(data)
                )

                return task_analysis_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(FeedbackReportResponseTaskAnalysisType0 | None | Unset, data)

        task_analysis = _parse_task_analysis(d.pop("task_analysis", UNSET))

        def _parse_error_summary(
            data: object,
        ) -> FeedbackReportResponseErrorSummaryType0 | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                error_summary_type_0 = (
                    FeedbackReportResponseErrorSummaryType0.from_dict(data)
                )

                return error_summary_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(FeedbackReportResponseErrorSummaryType0 | None | Unset, data)

        error_summary = _parse_error_summary(d.pop("error_summary", UNSET))

        def _parse_token_efficiency(
            data: object,
        ) -> FeedbackReportResponseTokenEfficiencyType0 | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                token_efficiency_type_0 = (
                    FeedbackReportResponseTokenEfficiencyType0.from_dict(data)
                )

                return token_efficiency_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(FeedbackReportResponseTokenEfficiencyType0 | None | Unset, data)

        token_efficiency = _parse_token_efficiency(d.pop("token_efficiency", UNSET))

        synthesis_mode = d.pop("synthesis_mode", UNSET)

        status = d.pop("status", UNSET)

        def _parse_created_at(data: object) -> datetime.datetime | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                created_at_type_0 = isoparse(data)

                return created_at_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(datetime.datetime | None | Unset, data)

        created_at = _parse_created_at(d.pop("created_at", UNSET))

        feedback_report_response = cls(
            id=id,
            mission_id=mission_id,
            overall_score=overall_score,
            efficiency_score=efficiency_score,
            quality_score=quality_score,
            strengths=strengths,
            weaknesses=weaknesses,
            suggestions=suggestions,
            task_analysis=task_analysis,
            error_summary=error_summary,
            token_efficiency=token_efficiency,
            synthesis_mode=synthesis_mode,
            status=status,
            created_at=created_at,
        )

        feedback_report_response.additional_properties = d
        return feedback_report_response

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
