from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.tool_stats_category_counts import ToolStatsCategoryCounts


T = TypeVar("T", bound="ToolStats")


@_attrs_define
class ToolStats:
    """Public tool statistics — no auth required.

    Attributes:
        total_tools (int):
        categories (list[str]):
        category_counts (ToolStatsCategoryCounts):
    """

    total_tools: int
    categories: list[str]
    category_counts: ToolStatsCategoryCounts
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        total_tools = self.total_tools

        categories = self.categories

        category_counts = self.category_counts.to_dict()

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "total_tools": total_tools,
                "categories": categories,
                "category_counts": category_counts,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.tool_stats_category_counts import ToolStatsCategoryCounts

        d = dict(src_dict)
        total_tools = d.pop("total_tools")

        categories = cast(list[str], d.pop("categories"))

        category_counts = ToolStatsCategoryCounts.from_dict(d.pop("category_counts"))

        tool_stats = cls(
            total_tools=total_tools,
            categories=categories,
            category_counts=category_counts,
        )

        tool_stats.additional_properties = d
        return tool_stats

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
