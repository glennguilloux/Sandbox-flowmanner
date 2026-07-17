from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="ShareCreateRequest")


@_attrs_define
class ShareCreateRequest:
    """
    Attributes:
        target_workspace_id (str): Workspace to grant access to
        entity_type (str): Entity type: mission, workflow, chat_thread
        entity_id (str): Entity ID to share
        permission (str | Unset): Permission level: read or write Default: 'read'.
    """

    target_workspace_id: str
    entity_type: str
    entity_id: str
    permission: str | Unset = "read"
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        target_workspace_id = self.target_workspace_id

        entity_type = self.entity_type

        entity_id = self.entity_id

        permission = self.permission

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "target_workspace_id": target_workspace_id,
                "entity_type": entity_type,
                "entity_id": entity_id,
            }
        )
        if permission is not UNSET:
            field_dict["permission"] = permission

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        target_workspace_id = d.pop("target_workspace_id")

        entity_type = d.pop("entity_type")

        entity_id = d.pop("entity_id")

        permission = d.pop("permission", UNSET)

        share_create_request = cls(
            target_workspace_id=target_workspace_id,
            entity_type=entity_type,
            entity_id=entity_id,
            permission=permission,
        )

        share_create_request.additional_properties = d
        return share_create_request

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
