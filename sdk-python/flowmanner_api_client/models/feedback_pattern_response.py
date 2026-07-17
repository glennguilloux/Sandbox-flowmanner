from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.feedback_pattern_response_example_mission_ids_type_0 import (
        FeedbackPatternResponseExampleMissionIdsType0,
    )


T = TypeVar("T", bound="FeedbackPatternResponse")


@_attrs_define
class FeedbackPatternResponse:
    """
    Attributes:
        id (str):
        pattern_type (str):
        description (str):
        frequency (int):
        severity (str):
        example_mission_ids (FeedbackPatternResponseExampleMissionIdsType0 | None | Unset):
        suggested_fix (None | str | Unset):
        status (str | Unset):  Default: 'active'.
        created_at (datetime.datetime | None | Unset):
    """

    id: str
    pattern_type: str
    description: str
    frequency: int
    severity: str
    example_mission_ids: FeedbackPatternResponseExampleMissionIdsType0 | None | Unset = UNSET
    suggested_fix: None | str | Unset = UNSET
    status: str | Unset = "active"
    created_at: datetime.datetime | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.feedback_pattern_response_example_mission_ids_type_0 import (
            FeedbackPatternResponseExampleMissionIdsType0,
        )

        id = self.id

        pattern_type = self.pattern_type

        description = self.description

        frequency = self.frequency

        severity = self.severity

        example_mission_ids: dict[str, Any] | None | Unset
        if isinstance(self.example_mission_ids, Unset):
            example_mission_ids = UNSET
        elif isinstance(self.example_mission_ids, FeedbackPatternResponseExampleMissionIdsType0):
            example_mission_ids = self.example_mission_ids.to_dict()
        else:
            example_mission_ids = self.example_mission_ids

        suggested_fix: None | str | Unset
        if isinstance(self.suggested_fix, Unset):
            suggested_fix = UNSET
        else:
            suggested_fix = self.suggested_fix

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
                "pattern_type": pattern_type,
                "description": description,
                "frequency": frequency,
                "severity": severity,
            }
        )
        if example_mission_ids is not UNSET:
            field_dict["example_mission_ids"] = example_mission_ids
        if suggested_fix is not UNSET:
            field_dict["suggested_fix"] = suggested_fix
        if status is not UNSET:
            field_dict["status"] = status
        if created_at is not UNSET:
            field_dict["created_at"] = created_at

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.feedback_pattern_response_example_mission_ids_type_0 import (
            FeedbackPatternResponseExampleMissionIdsType0,
        )

        d = dict(src_dict)
        id = d.pop("id")

        pattern_type = d.pop("pattern_type")

        description = d.pop("description")

        frequency = d.pop("frequency")

        severity = d.pop("severity")

        def _parse_example_mission_ids(data: object) -> FeedbackPatternResponseExampleMissionIdsType0 | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                example_mission_ids_type_0 = FeedbackPatternResponseExampleMissionIdsType0.from_dict(data)

                return example_mission_ids_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(FeedbackPatternResponseExampleMissionIdsType0 | None | Unset, data)

        example_mission_ids = _parse_example_mission_ids(d.pop("example_mission_ids", UNSET))

        def _parse_suggested_fix(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        suggested_fix = _parse_suggested_fix(d.pop("suggested_fix", UNSET))

        status = d.pop("status", UNSET)

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

        feedback_pattern_response = cls(
            id=id,
            pattern_type=pattern_type,
            description=description,
            frequency=frequency,
            severity=severity,
            example_mission_ids=example_mission_ids,
            suggested_fix=suggested_fix,
            status=status,
            created_at=created_at,
        )

        feedback_pattern_response.additional_properties = d
        return feedback_pattern_response

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
