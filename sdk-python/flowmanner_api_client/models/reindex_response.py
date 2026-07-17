from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

T = TypeVar("T", bound="ReindexResponse")


@_attrs_define
class ReindexResponse:
    """
    Attributes:
        tools_indexed (int):
        capabilities_indexed (int):
        total (int):
        source (str):
    """

    tools_indexed: int
    capabilities_indexed: int
    total: int
    source: str
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        tools_indexed = self.tools_indexed

        capabilities_indexed = self.capabilities_indexed

        total = self.total

        source = self.source

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "tools_indexed": tools_indexed,
                "capabilities_indexed": capabilities_indexed,
                "total": total,
                "source": source,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        tools_indexed = d.pop("tools_indexed")

        capabilities_indexed = d.pop("capabilities_indexed")

        total = d.pop("total")

        source = d.pop("source")

        reindex_response = cls(
            tools_indexed=tools_indexed,
            capabilities_indexed=capabilities_indexed,
            total=total,
            source=source,
        )

        reindex_response.additional_properties = d
        return reindex_response

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
