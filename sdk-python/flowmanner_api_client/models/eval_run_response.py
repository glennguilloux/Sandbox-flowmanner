from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.eval_run_response_scores_by_category_type_0 import EvalRunResponseScoresByCategoryType0


T = TypeVar("T", bound="EvalRunResponse")


@_attrs_define
class EvalRunResponse:
    """
    Attributes:
        id (str):
        dataset_id (str):
        model_name (str):
        status (str):
        aggregate_score (float | None):
        scores_by_category (EvalRunResponseScoresByCategoryType0 | None):
        per_case_count (int):
        error_message (None | str):
        started_at (None | str):
        completed_at (None | str):
        total_cost_usd (float | None | Unset):
        total_latency_ms (int | None | Unset):
        routed_provider (None | str | Unset):
        judge_model (None | str | Unset):
        pass_rate (float | None | Unset):
        correct_count (int | None | Unset):
    """

    id: str
    dataset_id: str
    model_name: str
    status: str
    aggregate_score: float | None
    scores_by_category: EvalRunResponseScoresByCategoryType0 | None
    per_case_count: int
    error_message: None | str
    started_at: None | str
    completed_at: None | str
    total_cost_usd: float | None | Unset = UNSET
    total_latency_ms: int | None | Unset = UNSET
    routed_provider: None | str | Unset = UNSET
    judge_model: None | str | Unset = UNSET
    pass_rate: float | None | Unset = UNSET
    correct_count: int | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.eval_run_response_scores_by_category_type_0 import EvalRunResponseScoresByCategoryType0

        id = self.id

        dataset_id = self.dataset_id

        model_name = self.model_name

        status = self.status

        aggregate_score: float | None
        aggregate_score = self.aggregate_score

        scores_by_category: dict[str, Any] | None
        if isinstance(self.scores_by_category, EvalRunResponseScoresByCategoryType0):
            scores_by_category = self.scores_by_category.to_dict()
        else:
            scores_by_category = self.scores_by_category

        per_case_count = self.per_case_count

        error_message: None | str
        error_message = self.error_message

        started_at: None | str
        started_at = self.started_at

        completed_at: None | str
        completed_at = self.completed_at

        total_cost_usd: float | None | Unset
        if isinstance(self.total_cost_usd, Unset):
            total_cost_usd = UNSET
        else:
            total_cost_usd = self.total_cost_usd

        total_latency_ms: int | None | Unset
        if isinstance(self.total_latency_ms, Unset):
            total_latency_ms = UNSET
        else:
            total_latency_ms = self.total_latency_ms

        routed_provider: None | str | Unset
        if isinstance(self.routed_provider, Unset):
            routed_provider = UNSET
        else:
            routed_provider = self.routed_provider

        judge_model: None | str | Unset
        if isinstance(self.judge_model, Unset):
            judge_model = UNSET
        else:
            judge_model = self.judge_model

        pass_rate: float | None | Unset
        if isinstance(self.pass_rate, Unset):
            pass_rate = UNSET
        else:
            pass_rate = self.pass_rate

        correct_count: int | None | Unset
        if isinstance(self.correct_count, Unset):
            correct_count = UNSET
        else:
            correct_count = self.correct_count

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "id": id,
                "dataset_id": dataset_id,
                "model_name": model_name,
                "status": status,
                "aggregate_score": aggregate_score,
                "scores_by_category": scores_by_category,
                "per_case_count": per_case_count,
                "error_message": error_message,
                "started_at": started_at,
                "completed_at": completed_at,
            }
        )
        if total_cost_usd is not UNSET:
            field_dict["total_cost_usd"] = total_cost_usd
        if total_latency_ms is not UNSET:
            field_dict["total_latency_ms"] = total_latency_ms
        if routed_provider is not UNSET:
            field_dict["routed_provider"] = routed_provider
        if judge_model is not UNSET:
            field_dict["judge_model"] = judge_model
        if pass_rate is not UNSET:
            field_dict["pass_rate"] = pass_rate
        if correct_count is not UNSET:
            field_dict["correct_count"] = correct_count

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.eval_run_response_scores_by_category_type_0 import EvalRunResponseScoresByCategoryType0

        d = dict(src_dict)
        id = d.pop("id")

        dataset_id = d.pop("dataset_id")

        model_name = d.pop("model_name")

        status = d.pop("status")

        def _parse_aggregate_score(data: object) -> float | None:
            if data is None:
                return data
            return cast(float | None, data)

        aggregate_score = _parse_aggregate_score(d.pop("aggregate_score"))

        def _parse_scores_by_category(data: object) -> EvalRunResponseScoresByCategoryType0 | None:
            if data is None:
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                scores_by_category_type_0 = EvalRunResponseScoresByCategoryType0.from_dict(data)

                return scores_by_category_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(EvalRunResponseScoresByCategoryType0 | None, data)

        scores_by_category = _parse_scores_by_category(d.pop("scores_by_category"))

        per_case_count = d.pop("per_case_count")

        def _parse_error_message(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        error_message = _parse_error_message(d.pop("error_message"))

        def _parse_started_at(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        started_at = _parse_started_at(d.pop("started_at"))

        def _parse_completed_at(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        completed_at = _parse_completed_at(d.pop("completed_at"))

        def _parse_total_cost_usd(data: object) -> float | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(float | None | Unset, data)

        total_cost_usd = _parse_total_cost_usd(d.pop("total_cost_usd", UNSET))

        def _parse_total_latency_ms(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        total_latency_ms = _parse_total_latency_ms(d.pop("total_latency_ms", UNSET))

        def _parse_routed_provider(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        routed_provider = _parse_routed_provider(d.pop("routed_provider", UNSET))

        def _parse_judge_model(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        judge_model = _parse_judge_model(d.pop("judge_model", UNSET))

        def _parse_pass_rate(data: object) -> float | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(float | None | Unset, data)

        pass_rate = _parse_pass_rate(d.pop("pass_rate", UNSET))

        def _parse_correct_count(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        correct_count = _parse_correct_count(d.pop("correct_count", UNSET))

        eval_run_response = cls(
            id=id,
            dataset_id=dataset_id,
            model_name=model_name,
            status=status,
            aggregate_score=aggregate_score,
            scores_by_category=scores_by_category,
            per_case_count=per_case_count,
            error_message=error_message,
            started_at=started_at,
            completed_at=completed_at,
            total_cost_usd=total_cost_usd,
            total_latency_ms=total_latency_ms,
            routed_provider=routed_provider,
            judge_model=judge_model,
            pass_rate=pass_rate,
            correct_count=correct_count,
        )

        eval_run_response.additional_properties = d
        return eval_run_response

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
