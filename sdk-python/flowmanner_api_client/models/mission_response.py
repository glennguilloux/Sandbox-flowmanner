from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast
from uuid import UUID

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.mission_status import MissionStatus
from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.mission_response_plan_type_0 import MissionResponsePlanType0
    from ..models.mission_response_results_type_0 import MissionResponseResultsType0


T = TypeVar("T", bound="MissionResponse")


@_attrs_define
class MissionResponse:
    """
    Attributes:
        id (UUID):
        user_id (int):
        title (str):
        description (str):
        mission_type (None | str | Unset):
        status (MissionStatus | None | Unset):
        priority (None | str | Unset):
        plan (MissionResponsePlanType0 | None | Unset):
        results (MissionResponseResultsType0 | None | Unset):
        error_message (None | str | Unset):
        tokens_used (int | None | Unset):
        estimated_cost (float | None | Unset):
        actual_cost (float | None | Unset):
        started_at (datetime.datetime | None | Unset):
        completed_at (datetime.datetime | None | Unset):
        created_at (datetime.datetime | None | Unset):
        updated_at (datetime.datetime | None | Unset):
        progress (int | None | Unset):
        eta (datetime.datetime | None | Unset):
    """

    id: UUID
    user_id: int
    title: str
    description: str
    mission_type: None | str | Unset = UNSET
    status: MissionStatus | None | Unset = UNSET
    priority: None | str | Unset = UNSET
    plan: MissionResponsePlanType0 | None | Unset = UNSET
    results: MissionResponseResultsType0 | None | Unset = UNSET
    error_message: None | str | Unset = UNSET
    tokens_used: int | None | Unset = UNSET
    estimated_cost: float | None | Unset = UNSET
    actual_cost: float | None | Unset = UNSET
    started_at: datetime.datetime | None | Unset = UNSET
    completed_at: datetime.datetime | None | Unset = UNSET
    created_at: datetime.datetime | None | Unset = UNSET
    updated_at: datetime.datetime | None | Unset = UNSET
    progress: int | None | Unset = UNSET
    eta: datetime.datetime | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.mission_response_plan_type_0 import MissionResponsePlanType0
        from ..models.mission_response_results_type_0 import MissionResponseResultsType0

        id = str(self.id)

        user_id = self.user_id

        title = self.title

        description = self.description

        mission_type: None | str | Unset
        if isinstance(self.mission_type, Unset):
            mission_type = UNSET
        else:
            mission_type = self.mission_type

        status: None | str | Unset
        if isinstance(self.status, Unset):
            status = UNSET
        elif isinstance(self.status, MissionStatus):
            status = self.status.value
        else:
            status = self.status

        priority: None | str | Unset
        if isinstance(self.priority, Unset):
            priority = UNSET
        else:
            priority = self.priority

        plan: dict[str, Any] | None | Unset
        if isinstance(self.plan, Unset):
            plan = UNSET
        elif isinstance(self.plan, MissionResponsePlanType0):
            plan = self.plan.to_dict()
        else:
            plan = self.plan

        results: dict[str, Any] | None | Unset
        if isinstance(self.results, Unset):
            results = UNSET
        elif isinstance(self.results, MissionResponseResultsType0):
            results = self.results.to_dict()
        else:
            results = self.results

        error_message: None | str | Unset
        if isinstance(self.error_message, Unset):
            error_message = UNSET
        else:
            error_message = self.error_message

        tokens_used: int | None | Unset
        if isinstance(self.tokens_used, Unset):
            tokens_used = UNSET
        else:
            tokens_used = self.tokens_used

        estimated_cost: float | None | Unset
        if isinstance(self.estimated_cost, Unset):
            estimated_cost = UNSET
        else:
            estimated_cost = self.estimated_cost

        actual_cost: float | None | Unset
        if isinstance(self.actual_cost, Unset):
            actual_cost = UNSET
        else:
            actual_cost = self.actual_cost

        started_at: None | str | Unset
        if isinstance(self.started_at, Unset):
            started_at = UNSET
        elif isinstance(self.started_at, datetime.datetime):
            started_at = self.started_at.isoformat()
        else:
            started_at = self.started_at

        completed_at: None | str | Unset
        if isinstance(self.completed_at, Unset):
            completed_at = UNSET
        elif isinstance(self.completed_at, datetime.datetime):
            completed_at = self.completed_at.isoformat()
        else:
            completed_at = self.completed_at

        created_at: None | str | Unset
        if isinstance(self.created_at, Unset):
            created_at = UNSET
        elif isinstance(self.created_at, datetime.datetime):
            created_at = self.created_at.isoformat()
        else:
            created_at = self.created_at

        updated_at: None | str | Unset
        if isinstance(self.updated_at, Unset):
            updated_at = UNSET
        elif isinstance(self.updated_at, datetime.datetime):
            updated_at = self.updated_at.isoformat()
        else:
            updated_at = self.updated_at

        progress: int | None | Unset
        if isinstance(self.progress, Unset):
            progress = UNSET
        else:
            progress = self.progress

        eta: None | str | Unset
        if isinstance(self.eta, Unset):
            eta = UNSET
        elif isinstance(self.eta, datetime.datetime):
            eta = self.eta.isoformat()
        else:
            eta = self.eta

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "id": id,
                "user_id": user_id,
                "title": title,
                "description": description,
            }
        )
        if mission_type is not UNSET:
            field_dict["mission_type"] = mission_type
        if status is not UNSET:
            field_dict["status"] = status
        if priority is not UNSET:
            field_dict["priority"] = priority
        if plan is not UNSET:
            field_dict["plan"] = plan
        if results is not UNSET:
            field_dict["results"] = results
        if error_message is not UNSET:
            field_dict["error_message"] = error_message
        if tokens_used is not UNSET:
            field_dict["tokens_used"] = tokens_used
        if estimated_cost is not UNSET:
            field_dict["estimated_cost"] = estimated_cost
        if actual_cost is not UNSET:
            field_dict["actual_cost"] = actual_cost
        if started_at is not UNSET:
            field_dict["started_at"] = started_at
        if completed_at is not UNSET:
            field_dict["completed_at"] = completed_at
        if created_at is not UNSET:
            field_dict["created_at"] = created_at
        if updated_at is not UNSET:
            field_dict["updated_at"] = updated_at
        if progress is not UNSET:
            field_dict["progress"] = progress
        if eta is not UNSET:
            field_dict["eta"] = eta

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.mission_response_plan_type_0 import MissionResponsePlanType0
        from ..models.mission_response_results_type_0 import MissionResponseResultsType0

        d = dict(src_dict)
        id = UUID(d.pop("id"))

        user_id = d.pop("user_id")

        title = d.pop("title")

        description = d.pop("description")

        def _parse_mission_type(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        mission_type = _parse_mission_type(d.pop("mission_type", UNSET))

        def _parse_status(data: object) -> MissionStatus | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                status_type_0 = MissionStatus(data)

                return status_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(MissionStatus | None | Unset, data)

        status = _parse_status(d.pop("status", UNSET))

        def _parse_priority(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        priority = _parse_priority(d.pop("priority", UNSET))

        def _parse_plan(data: object) -> MissionResponsePlanType0 | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                plan_type_0 = MissionResponsePlanType0.from_dict(data)

                return plan_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(MissionResponsePlanType0 | None | Unset, data)

        plan = _parse_plan(d.pop("plan", UNSET))

        def _parse_results(data: object) -> MissionResponseResultsType0 | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                results_type_0 = MissionResponseResultsType0.from_dict(data)

                return results_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(MissionResponseResultsType0 | None | Unset, data)

        results = _parse_results(d.pop("results", UNSET))

        def _parse_error_message(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        error_message = _parse_error_message(d.pop("error_message", UNSET))

        def _parse_tokens_used(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        tokens_used = _parse_tokens_used(d.pop("tokens_used", UNSET))

        def _parse_estimated_cost(data: object) -> float | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(float | None | Unset, data)

        estimated_cost = _parse_estimated_cost(d.pop("estimated_cost", UNSET))

        def _parse_actual_cost(data: object) -> float | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(float | None | Unset, data)

        actual_cost = _parse_actual_cost(d.pop("actual_cost", UNSET))

        def _parse_started_at(data: object) -> datetime.datetime | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                started_at_type_0 = datetime.datetime.fromisoformat(data)

                return started_at_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(datetime.datetime | None | Unset, data)

        started_at = _parse_started_at(d.pop("started_at", UNSET))

        def _parse_completed_at(data: object) -> datetime.datetime | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                completed_at_type_0 = datetime.datetime.fromisoformat(data)

                return completed_at_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(datetime.datetime | None | Unset, data)

        completed_at = _parse_completed_at(d.pop("completed_at", UNSET))

        def _parse_created_at(data: object) -> datetime.datetime | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                created_at_type_0 = datetime.datetime.fromisoformat(data)

                return created_at_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(datetime.datetime | None | Unset, data)

        created_at = _parse_created_at(d.pop("created_at", UNSET))

        def _parse_updated_at(data: object) -> datetime.datetime | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                updated_at_type_0 = datetime.datetime.fromisoformat(data)

                return updated_at_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(datetime.datetime | None | Unset, data)

        updated_at = _parse_updated_at(d.pop("updated_at", UNSET))

        def _parse_progress(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        progress = _parse_progress(d.pop("progress", UNSET))

        def _parse_eta(data: object) -> datetime.datetime | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                eta_type_0 = datetime.datetime.fromisoformat(data)

                return eta_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(datetime.datetime | None | Unset, data)

        eta = _parse_eta(d.pop("eta", UNSET))

        mission_response = cls(
            id=id,
            user_id=user_id,
            title=title,
            description=description,
            mission_type=mission_type,
            status=status,
            priority=priority,
            plan=plan,
            results=results,
            error_message=error_message,
            tokens_used=tokens_used,
            estimated_cost=estimated_cost,
            actual_cost=actual_cost,
            started_at=started_at,
            completed_at=completed_at,
            created_at=created_at,
            updated_at=updated_at,
            progress=progress,
            eta=eta,
        )

        mission_response.additional_properties = d
        return mission_response

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
