from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define

from ..models.mission_status import MissionStatus
from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.mission_update_results_type_0 import MissionUpdateResultsType0


T = TypeVar("T", bound="MissionUpdate")


@_attrs_define
class MissionUpdate:
    """
    Attributes:
        title (None | str | Unset):
        description (None | str | Unset):
        status (MissionStatus | None | Unset):
        priority (None | str | Unset):
        mission_type (None | str | Unset):
        error_message (None | str | Unset):
        results (MissionUpdateResultsType0 | None | Unset):
        tokens_used (int | None | Unset):
        actual_cost (float | None | Unset):
    """

    title: None | str | Unset = UNSET
    description: None | str | Unset = UNSET
    status: MissionStatus | None | Unset = UNSET
    priority: None | str | Unset = UNSET
    mission_type: None | str | Unset = UNSET
    error_message: None | str | Unset = UNSET
    results: MissionUpdateResultsType0 | None | Unset = UNSET
    tokens_used: int | None | Unset = UNSET
    actual_cost: float | None | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        from ..models.mission_update_results_type_0 import MissionUpdateResultsType0

        title: None | str | Unset
        if isinstance(self.title, Unset):
            title = UNSET
        else:
            title = self.title

        description: None | str | Unset
        if isinstance(self.description, Unset):
            description = UNSET
        else:
            description = self.description

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

        mission_type: None | str | Unset
        if isinstance(self.mission_type, Unset):
            mission_type = UNSET
        else:
            mission_type = self.mission_type

        error_message: None | str | Unset
        if isinstance(self.error_message, Unset):
            error_message = UNSET
        else:
            error_message = self.error_message

        results: dict[str, Any] | None | Unset
        if isinstance(self.results, Unset):
            results = UNSET
        elif isinstance(self.results, MissionUpdateResultsType0):
            results = self.results.to_dict()
        else:
            results = self.results

        tokens_used: int | None | Unset
        if isinstance(self.tokens_used, Unset):
            tokens_used = UNSET
        else:
            tokens_used = self.tokens_used

        actual_cost: float | None | Unset
        if isinstance(self.actual_cost, Unset):
            actual_cost = UNSET
        else:
            actual_cost = self.actual_cost

        field_dict: dict[str, Any] = {}

        field_dict.update({})
        if title is not UNSET:
            field_dict["title"] = title
        if description is not UNSET:
            field_dict["description"] = description
        if status is not UNSET:
            field_dict["status"] = status
        if priority is not UNSET:
            field_dict["priority"] = priority
        if mission_type is not UNSET:
            field_dict["mission_type"] = mission_type
        if error_message is not UNSET:
            field_dict["error_message"] = error_message
        if results is not UNSET:
            field_dict["results"] = results
        if tokens_used is not UNSET:
            field_dict["tokens_used"] = tokens_used
        if actual_cost is not UNSET:
            field_dict["actual_cost"] = actual_cost

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.mission_update_results_type_0 import MissionUpdateResultsType0

        d = dict(src_dict)

        def _parse_title(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        title = _parse_title(d.pop("title", UNSET))

        def _parse_description(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        description = _parse_description(d.pop("description", UNSET))

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

        def _parse_mission_type(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        mission_type = _parse_mission_type(d.pop("mission_type", UNSET))

        def _parse_error_message(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        error_message = _parse_error_message(d.pop("error_message", UNSET))

        def _parse_results(data: object) -> MissionUpdateResultsType0 | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                results_type_0 = MissionUpdateResultsType0.from_dict(data)

                return results_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(MissionUpdateResultsType0 | None | Unset, data)

        results = _parse_results(d.pop("results", UNSET))

        def _parse_tokens_used(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        tokens_used = _parse_tokens_used(d.pop("tokens_used", UNSET))

        def _parse_actual_cost(data: object) -> float | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(float | None | Unset, data)

        actual_cost = _parse_actual_cost(d.pop("actual_cost", UNSET))

        mission_update = cls(
            title=title,
            description=description,
            status=status,
            priority=priority,
            mission_type=mission_type,
            error_message=error_message,
            results=results,
            tokens_used=tokens_used,
            actual_cost=actual_cost,
        )

        return mission_update
