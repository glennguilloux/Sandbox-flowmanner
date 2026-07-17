from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="RouteRequest")


@_attrs_define
class RouteRequest:
    """Request body for POST /tool-routing/route.

    Attributes:
        task_text (str): Natural language task description
        workspace_id (str): Workspace UUID to scope results
        user_id (int): User ID for scoping
        k (int | None | Unset): Override top-k (default: 8)
    """

    task_text: str
    workspace_id: str
    user_id: int
    k: int | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        task_text = self.task_text

        workspace_id = self.workspace_id

        user_id = self.user_id

        k: int | None | Unset
        if isinstance(self.k, Unset):
            k = UNSET
        else:
            k = self.k

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "task_text": task_text,
                "workspace_id": workspace_id,
                "user_id": user_id,
            }
        )
        if k is not UNSET:
            field_dict["k"] = k

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        task_text = d.pop("task_text")

        workspace_id = d.pop("workspace_id")

        user_id = d.pop("user_id")

        def _parse_k(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        k = _parse_k(d.pop("k", UNSET))

        route_request = cls(
            task_text=task_text,
            workspace_id=workspace_id,
            user_id=user_id,
            k=k,
        )

        route_request.additional_properties = d
        return route_request

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
