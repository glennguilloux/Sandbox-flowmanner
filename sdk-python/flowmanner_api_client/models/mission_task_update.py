from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define

from ..models.mission_task_status import MissionTaskStatus
from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.mission_task_update_output_data_type_0 import MissionTaskUpdateOutputDataType0


T = TypeVar("T", bound="MissionTaskUpdate")


@_attrs_define
class MissionTaskUpdate:
    """
    Attributes:
        title (None | str | Unset):
        description (None | str | Unset):
        status (MissionTaskStatus | None | Unset):
        output_data (MissionTaskUpdateOutputDataType0 | None | Unset):
        error_message (None | str | Unset):
        tokens_used (int | None | Unset):
        cost (float | None | Unset):
    """

    title: None | str | Unset = UNSET
    description: None | str | Unset = UNSET
    status: MissionTaskStatus | None | Unset = UNSET
    output_data: MissionTaskUpdateOutputDataType0 | None | Unset = UNSET
    error_message: None | str | Unset = UNSET
    tokens_used: int | None | Unset = UNSET
    cost: float | None | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        from ..models.mission_task_update_output_data_type_0 import MissionTaskUpdateOutputDataType0

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
        elif isinstance(self.status, MissionTaskStatus):
            status = self.status.value
        else:
            status = self.status

        output_data: dict[str, Any] | None | Unset
        if isinstance(self.output_data, Unset):
            output_data = UNSET
        elif isinstance(self.output_data, MissionTaskUpdateOutputDataType0):
            output_data = self.output_data.to_dict()
        else:
            output_data = self.output_data

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

        cost: float | None | Unset
        if isinstance(self.cost, Unset):
            cost = UNSET
        else:
            cost = self.cost

        field_dict: dict[str, Any] = {}

        field_dict.update({})
        if title is not UNSET:
            field_dict["title"] = title
        if description is not UNSET:
            field_dict["description"] = description
        if status is not UNSET:
            field_dict["status"] = status
        if output_data is not UNSET:
            field_dict["output_data"] = output_data
        if error_message is not UNSET:
            field_dict["error_message"] = error_message
        if tokens_used is not UNSET:
            field_dict["tokens_used"] = tokens_used
        if cost is not UNSET:
            field_dict["cost"] = cost

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.mission_task_update_output_data_type_0 import MissionTaskUpdateOutputDataType0

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

        def _parse_status(data: object) -> MissionTaskStatus | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                status_type_0 = MissionTaskStatus(data)

                return status_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(MissionTaskStatus | None | Unset, data)

        status = _parse_status(d.pop("status", UNSET))

        def _parse_output_data(data: object) -> MissionTaskUpdateOutputDataType0 | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                output_data_type_0 = MissionTaskUpdateOutputDataType0.from_dict(data)

                return output_data_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(MissionTaskUpdateOutputDataType0 | None | Unset, data)

        output_data = _parse_output_data(d.pop("output_data", UNSET))

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

        def _parse_cost(data: object) -> float | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(float | None | Unset, data)

        cost = _parse_cost(d.pop("cost", UNSET))

        mission_task_update = cls(
            title=title,
            description=description,
            status=status,
            output_data=output_data,
            error_message=error_message,
            tokens_used=tokens_used,
            cost=cost,
        )

        return mission_task_update
