from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

T = TypeVar("T", bound="PromptVersionResponse")


@_attrs_define
class PromptVersionResponse:
    """
    Attributes:
        id (int):
        workspace_id (str):
        name (str):
        content (str):
        version (int):
        is_active (bool):
        created_by (int | None):
        created_at (None | str):
        updated_at (None | str):
    """

    id: int
    workspace_id: str
    name: str
    content: str
    version: int
    is_active: bool
    created_by: int | None
    created_at: None | str
    updated_at: None | str
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        id = self.id

        workspace_id = self.workspace_id

        name = self.name

        content = self.content

        version = self.version

        is_active = self.is_active

        created_by: int | None
        created_by = self.created_by

        created_at: None | str
        created_at = self.created_at

        updated_at: None | str
        updated_at = self.updated_at

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "id": id,
                "workspace_id": workspace_id,
                "name": name,
                "content": content,
                "version": version,
                "is_active": is_active,
                "created_by": created_by,
                "created_at": created_at,
                "updated_at": updated_at,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        id = d.pop("id")

        workspace_id = d.pop("workspace_id")

        name = d.pop("name")

        content = d.pop("content")

        version = d.pop("version")

        is_active = d.pop("is_active")

        def _parse_created_by(data: object) -> int | None:
            if data is None:
                return data
            return cast(int | None, data)

        created_by = _parse_created_by(d.pop("created_by"))

        def _parse_created_at(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        created_at = _parse_created_at(d.pop("created_at"))

        def _parse_updated_at(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        updated_at = _parse_updated_at(d.pop("updated_at"))

        prompt_version_response = cls(
            id=id,
            workspace_id=workspace_id,
            name=name,
            content=content,
            version=version,
            is_active=is_active,
            created_by=created_by,
            created_at=created_at,
            updated_at=updated_at,
        )

        prompt_version_response.additional_properties = d
        return prompt_version_response

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
