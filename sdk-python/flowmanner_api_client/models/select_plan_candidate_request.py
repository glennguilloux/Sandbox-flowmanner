from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define

T = TypeVar("T", bound="SelectPlanCandidateRequest")


@_attrs_define
class SelectPlanCandidateRequest:
    """Body for POST /api/v2/missions/{id}/select-plan.

    Lets a user pre-select a non-default candidate before execution.
    The chosen plan_id must match a row in mission_plan_candidates
    for the mission; otherwise 404.

        Attributes:
            plan_id (str):
    """

    plan_id: str

    def to_dict(self) -> dict[str, Any]:
        plan_id = self.plan_id

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "plan_id": plan_id,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        plan_id = d.pop("plan_id")

        select_plan_candidate_request = cls(
            plan_id=plan_id,
        )

        return select_plan_candidate_request
