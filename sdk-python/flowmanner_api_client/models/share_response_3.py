from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

T = TypeVar("T", bound="ShareResponse3")


@_attrs_define
class ShareResponse3:
    """
    Attributes:
        id (str):
        source_workspace_id (str):
        target_workspace_id (str):
        entity_type (str):
        entity_id (str):
        permission (str):
        granted_by (int | None):
        is_active (bool):
    """

    id: str
    source_workspace_id: str
    target_workspace_id: str
    entity_type: str
    entity_id: str
    permission: str
    granted_by: int | None
    is_active: bool
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        id = self.id

        source_workspace_id = self.source_workspace_id

        target_workspace_id = self.target_workspace_id

        entity_type = self.entity_type

        entity_id = self.entity_id

        permission = self.permission

        granted_by: int | None
        granted_by = self.granted_by

        is_active = self.is_active

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "id": id,
                "source_workspace_id": source_workspace_id,
                "target_workspace_id": target_workspace_id,
                "entity_type": entity_type,
                "entity_id": entity_id,
                "permission": permission,
                "granted_by": granted_by,
                "is_active": is_active,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        id = d.pop("id")

        source_workspace_id = d.pop("source_workspace_id")

        target_workspace_id = d.pop("target_workspace_id")

        entity_type = d.pop("entity_type")

        entity_id = d.pop("entity_id")

        permission = d.pop("permission")

        def _parse_granted_by(data: object) -> int | None:
            if data is None:
                return data
            return cast(int | None, data)

        granted_by = _parse_granted_by(d.pop("granted_by"))

        is_active = d.pop("is_active")

        share_response_3 = cls(
            id=id,
            source_workspace_id=source_workspace_id,
            target_workspace_id=target_workspace_id,
            entity_type=entity_type,
            entity_id=entity_id,
            permission=permission,
            granted_by=granted_by,
            is_active=is_active,
        )

        share_response_3.additional_properties = d
        return share_response_3

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
