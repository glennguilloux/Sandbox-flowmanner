from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.bulk_resolve_request_action import BulkResolveRequestAction
from ..types import UNSET, Unset

T = TypeVar("T", bound="BulkResolveRequest")


@_attrs_define
class BulkResolveRequest:
    """Request body for bulk inbox item resolution.

    Attributes:
        item_ids (list[str]):
        action (BulkResolveRequestAction):
        resolution_note (None | str | Unset):
    """

    item_ids: list[str]
    action: BulkResolveRequestAction
    resolution_note: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        item_ids = self.item_ids

        action = self.action.value

        resolution_note: None | str | Unset
        if isinstance(self.resolution_note, Unset):
            resolution_note = UNSET
        else:
            resolution_note = self.resolution_note

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "item_ids": item_ids,
                "action": action,
            }
        )
        if resolution_note is not UNSET:
            field_dict["resolution_note"] = resolution_note

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        item_ids = cast(list[str], d.pop("item_ids"))

        action = BulkResolveRequestAction(d.pop("action"))

        def _parse_resolution_note(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        resolution_note = _parse_resolution_note(d.pop("resolution_note", UNSET))

        bulk_resolve_request = cls(
            item_ids=item_ids,
            action=action,
            resolution_note=resolution_note,
        )

        bulk_resolve_request.additional_properties = d
        return bulk_resolve_request

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
