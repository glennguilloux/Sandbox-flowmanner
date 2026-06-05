from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.tool_summary_input_schema import ToolSummaryInputSchema


T = TypeVar("T", bound="ToolSummary")


@_attrs_define
class ToolSummary:
    """
    Attributes:
        tool_id (str):
        name (str):
        description (str):
        category (str):
        tags (list[str]):
        input_schema (ToolSummaryInputSchema):
        requires_auth (bool):
    """

    tool_id: str
    name: str
    description: str
    category: str
    tags: list[str]
    input_schema: ToolSummaryInputSchema
    requires_auth: bool
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        tool_id = self.tool_id

        name = self.name

        description = self.description

        category = self.category

        tags = self.tags

        input_schema = self.input_schema.to_dict()

        requires_auth = self.requires_auth

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "tool_id": tool_id,
                "name": name,
                "description": description,
                "category": category,
                "tags": tags,
                "input_schema": input_schema,
                "requires_auth": requires_auth,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.tool_summary_input_schema import ToolSummaryInputSchema

        d = dict(src_dict)
        tool_id = d.pop("tool_id")

        name = d.pop("name")

        description = d.pop("description")

        category = d.pop("category")

        tags = cast(list[str], d.pop("tags"))

        input_schema = ToolSummaryInputSchema.from_dict(d.pop("input_schema"))

        requires_auth = d.pop("requires_auth")

        tool_summary = cls(
            tool_id=tool_id,
            name=name,
            description=description,
            category=category,
            tags=tags,
            input_schema=input_schema,
            requires_auth=requires_auth,
        )

        tool_summary.additional_properties = d
        return tool_summary

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
