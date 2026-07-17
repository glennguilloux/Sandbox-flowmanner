from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define

from ..types import UNSET, Unset

T = TypeVar("T", bound="ConsolidateRequest")


@_attrs_define
class ConsolidateRequest:
    """Request body for ``POST /programs/{id}/consolidate``.

    ``limit`` controls how many of the most-recent completed runs are fed to
    the consolidation LLM. Bounded 1..50 to prevent runaway consolidation
    runs.

        Attributes:
            limit (int | Unset):  Default: 10.
    """

    limit: int | Unset = 10

    def to_dict(self) -> dict[str, Any]:
        limit = self.limit

        field_dict: dict[str, Any] = {}

        field_dict.update({})
        if limit is not UNSET:
            field_dict["limit"] = limit

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        limit = d.pop("limit", UNSET)

        consolidate_request = cls(
            limit=limit,
        )

        return consolidate_request
