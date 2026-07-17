from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define

from ..types import UNSET, Unset

T = TypeVar("T", bound="NotesUpdate")


@_attrs_define
class NotesUpdate:
    """Request body for ``PATCH /programs/{id}/notes``.

    Column-level update: only the user-owned ``user_notes`` sub-key of the
    learning brief is touched.  Consolidation MUST NEVER overwrite this
    field (per plan §T2 — column-level UPDATE discipline in the service
    layer; this schema is the contract).

        Attributes:
            user_notes (str | Unset):  Default: ''.
    """

    user_notes: str | Unset = ""

    def to_dict(self) -> dict[str, Any]:
        user_notes = self.user_notes

        field_dict: dict[str, Any] = {}

        field_dict.update({})
        if user_notes is not UNSET:
            field_dict["user_notes"] = user_notes

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        user_notes = d.pop("user_notes", UNSET)

        notes_update = cls(
            user_notes=user_notes,
        )

        return notes_update
