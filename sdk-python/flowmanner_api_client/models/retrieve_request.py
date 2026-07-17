from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="RetrieveRequest")


@_attrs_define
class RetrieveRequest:
    """Request body for POST /episodes/retrieve.

    Attributes:
        query (str): Search query text
        workspace_id (str): Workspace UUID to scope results
        k (int | Unset): Max results (hard cap: 5) Default: 5.
    """

    query: str
    workspace_id: str
    k: int | Unset = 5
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        query = self.query

        workspace_id = self.workspace_id

        k = self.k

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "query": query,
                "workspace_id": workspace_id,
            }
        )
        if k is not UNSET:
            field_dict["k"] = k

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        query = d.pop("query")

        workspace_id = d.pop("workspace_id")

        k = d.pop("k", UNSET)

        retrieve_request = cls(
            query=query,
            workspace_id=workspace_id,
            k=k,
        )

        retrieve_request.additional_properties = d
        return retrieve_request

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
