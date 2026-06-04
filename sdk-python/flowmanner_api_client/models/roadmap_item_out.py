from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset







T = TypeVar("T", bound="RoadmapItemOut")



@_attrs_define
class RoadmapItemOut:
    """ 
        Attributes:
            id (str):
            title (str):
            description (str):
            status (str):
            category (str):
            sort_order (int):
            is_public (bool):
            vote_count (int):
            created_by (str):
            created_at (str):
            updated_at (str):
     """

    id: str
    title: str
    description: str
    status: str
    category: str
    sort_order: int
    is_public: bool
    vote_count: int
    created_by: str
    created_at: str
    updated_at: str
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        id = self.id

        title = self.title

        description = self.description

        status = self.status

        category = self.category

        sort_order = self.sort_order

        is_public = self.is_public

        vote_count = self.vote_count

        created_by = self.created_by

        created_at = self.created_at

        updated_at = self.updated_at


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "id": id,
            "title": title,
            "description": description,
            "status": status,
            "category": category,
            "sort_order": sort_order,
            "is_public": is_public,
            "vote_count": vote_count,
            "created_by": created_by,
            "created_at": created_at,
            "updated_at": updated_at,
        })

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        id = d.pop("id")

        title = d.pop("title")

        description = d.pop("description")

        status = d.pop("status")

        category = d.pop("category")

        sort_order = d.pop("sort_order")

        is_public = d.pop("is_public")

        vote_count = d.pop("vote_count")

        created_by = d.pop("created_by")

        created_at = d.pop("created_at")

        updated_at = d.pop("updated_at")

        roadmap_item_out = cls(
            id=id,
            title=title,
            description=description,
            status=status,
            category=category,
            sort_order=sort_order,
            is_public=is_public,
            vote_count=vote_count,
            created_by=created_by,
            created_at=created_at,
            updated_at=updated_at,
        )


        roadmap_item_out.additional_properties = d
        return roadmap_item_out

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
