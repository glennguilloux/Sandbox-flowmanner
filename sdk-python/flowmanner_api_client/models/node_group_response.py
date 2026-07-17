from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast
from uuid import UUID

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.node_group_response_config_type_0 import NodeGroupResponseConfigType0


T = TypeVar("T", bound="NodeGroupResponse")


@_attrs_define
class NodeGroupResponse:
    """
    Attributes:
        id (UUID):
        name (str):
        description (None | str):
        group_type (None | str):
        config (NodeGroupResponseConfigType0 | None):
        owner_id (int | None):
        created_at (datetime.datetime | None | Unset):
        updated_at (datetime.datetime | None | Unset):
    """

    id: UUID
    name: str
    description: None | str
    group_type: None | str
    config: NodeGroupResponseConfigType0 | None
    owner_id: int | None
    created_at: datetime.datetime | None | Unset = UNSET
    updated_at: datetime.datetime | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.node_group_response_config_type_0 import NodeGroupResponseConfigType0

        id = str(self.id)

        name = self.name

        description: None | str
        description = self.description

        group_type: None | str
        group_type = self.group_type

        config: dict[str, Any] | None
        if isinstance(self.config, NodeGroupResponseConfigType0):
            config = self.config.to_dict()
        else:
            config = self.config

        owner_id: int | None
        owner_id = self.owner_id

        created_at: None | str | Unset
        if isinstance(self.created_at, Unset):
            created_at = UNSET
        elif isinstance(self.created_at, datetime.datetime):
            created_at = self.created_at.isoformat()
        else:
            created_at = self.created_at

        updated_at: None | str | Unset
        if isinstance(self.updated_at, Unset):
            updated_at = UNSET
        elif isinstance(self.updated_at, datetime.datetime):
            updated_at = self.updated_at.isoformat()
        else:
            updated_at = self.updated_at

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "id": id,
                "name": name,
                "description": description,
                "group_type": group_type,
                "config": config,
                "owner_id": owner_id,
            }
        )
        if created_at is not UNSET:
            field_dict["created_at"] = created_at
        if updated_at is not UNSET:
            field_dict["updated_at"] = updated_at

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.node_group_response_config_type_0 import NodeGroupResponseConfigType0

        d = dict(src_dict)
        id = UUID(d.pop("id"))

        name = d.pop("name")

        def _parse_description(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        description = _parse_description(d.pop("description"))

        def _parse_group_type(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        group_type = _parse_group_type(d.pop("group_type"))

        def _parse_config(data: object) -> NodeGroupResponseConfigType0 | None:
            if data is None:
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                config_type_0 = NodeGroupResponseConfigType0.from_dict(data)

                return config_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(NodeGroupResponseConfigType0 | None, data)

        config = _parse_config(d.pop("config"))

        def _parse_owner_id(data: object) -> int | None:
            if data is None:
                return data
            return cast(int | None, data)

        owner_id = _parse_owner_id(d.pop("owner_id"))

        def _parse_created_at(data: object) -> datetime.datetime | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                created_at_type_0 = datetime.datetime.fromisoformat(data)

                return created_at_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(datetime.datetime | None | Unset, data)

        created_at = _parse_created_at(d.pop("created_at", UNSET))

        def _parse_updated_at(data: object) -> datetime.datetime | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                updated_at_type_0 = datetime.datetime.fromisoformat(data)

                return updated_at_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(datetime.datetime | None | Unset, data)

        updated_at = _parse_updated_at(d.pop("updated_at", UNSET))

        node_group_response = cls(
            id=id,
            name=name,
            description=description,
            group_type=group_type,
            config=config,
            owner_id=owner_id,
            created_at=created_at,
            updated_at=updated_at,
        )

        node_group_response.additional_properties = d
        return node_group_response

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
