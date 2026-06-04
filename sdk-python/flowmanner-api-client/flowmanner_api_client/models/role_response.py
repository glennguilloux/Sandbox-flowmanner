from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field
from dateutil.parser import isoparse

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.role_permission_response import RolePermissionResponse


T = TypeVar("T", bound="RoleResponse")


@_attrs_define
class RoleResponse:
    """
    Attributes:
        id (str):
        tenant_id (None | str):
        name (str):
        description (None | str):
        is_system (bool):
        created_by (int | None):
        created_at (datetime.datetime):
        updated_at (datetime.datetime):
        permissions (list[RolePermissionResponse] | Unset):
    """

    id: str
    tenant_id: None | str
    name: str
    description: None | str
    is_system: bool
    created_by: int | None
    created_at: datetime.datetime
    updated_at: datetime.datetime
    permissions: list[RolePermissionResponse] | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        id = self.id

        tenant_id: None | str
        tenant_id = self.tenant_id

        name = self.name

        description: None | str
        description = self.description

        is_system = self.is_system

        created_by: int | None
        created_by = self.created_by

        created_at = self.created_at.isoformat()

        updated_at = self.updated_at.isoformat()

        permissions: list[dict[str, Any]] | Unset = UNSET
        if not isinstance(self.permissions, Unset):
            permissions = []
            for permissions_item_data in self.permissions:
                permissions_item = permissions_item_data.to_dict()
                permissions.append(permissions_item)

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "id": id,
                "tenant_id": tenant_id,
                "name": name,
                "description": description,
                "is_system": is_system,
                "created_by": created_by,
                "created_at": created_at,
                "updated_at": updated_at,
            }
        )
        if permissions is not UNSET:
            field_dict["permissions"] = permissions

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.role_permission_response import RolePermissionResponse

        d = dict(src_dict)
        id = d.pop("id")

        def _parse_tenant_id(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        tenant_id = _parse_tenant_id(d.pop("tenant_id"))

        name = d.pop("name")

        def _parse_description(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        description = _parse_description(d.pop("description"))

        is_system = d.pop("is_system")

        def _parse_created_by(data: object) -> int | None:
            if data is None:
                return data
            return cast(int | None, data)

        created_by = _parse_created_by(d.pop("created_by"))

        created_at = isoparse(d.pop("created_at"))

        updated_at = isoparse(d.pop("updated_at"))

        _permissions = d.pop("permissions", UNSET)
        permissions: list[RolePermissionResponse] | Unset = UNSET
        if _permissions is not UNSET:
            permissions = []
            for permissions_item_data in _permissions:
                permissions_item = RolePermissionResponse.from_dict(permissions_item_data)

                permissions.append(permissions_item)

        role_response = cls(
            id=id,
            tenant_id=tenant_id,
            name=name,
            description=description,
            is_system=is_system,
            created_by=created_by,
            created_at=created_at,
            updated_at=updated_at,
            permissions=permissions,
        )

        role_response.additional_properties = d
        return role_response

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
