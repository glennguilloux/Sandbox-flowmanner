from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define

from ..types import UNSET, Unset

T = TypeVar("T", bound="PersonalMemoryForgetRequest")


@_attrs_define
class PersonalMemoryForgetRequest:
    """Request body for the explicit ``POST /forget`` endpoint.

    ``claim_id`` is the UUID of the claim to forget. ``hard=False`` (the
    default) is a soft-delete (sets ``deleted_at``); ``hard=True`` removes
    the row from the table.

        Attributes:
            claim_id (str):
            hard (bool | Unset):  Default: False.
    """

    claim_id: str
    hard: bool | Unset = False

    def to_dict(self) -> dict[str, Any]:
        claim_id = self.claim_id

        hard = self.hard

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "claim_id": claim_id,
            }
        )
        if hard is not UNSET:
            field_dict["hard"] = hard

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        claim_id = d.pop("claim_id")

        hard = d.pop("hard", UNSET)

        personal_memory_forget_request = cls(
            claim_id=claim_id,
            hard=hard,
        )

        return personal_memory_forget_request
