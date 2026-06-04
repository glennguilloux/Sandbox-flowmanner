from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..types import UNSET, Unset
from typing import cast

if TYPE_CHECKING:
  from ..models.tool_detail_input_schema import ToolDetailInputSchema
  from ..models.tool_detail_output_schema import ToolDetailOutputSchema





T = TypeVar("T", bound="ToolDetail")



@_attrs_define
class ToolDetail:
    """ 
        Attributes:
            tool_id (str):
            name (str):
            description (str):
            category (str):
            tags (list[str]):
            input_schema (ToolDetailInputSchema):
            output_schema (ToolDetailOutputSchema):
            requires_auth (bool):
            timeout_seconds (int):
            rate_limit (int | None | Unset):
     """

    tool_id: str
    name: str
    description: str
    category: str
    tags: list[str]
    input_schema: ToolDetailInputSchema
    output_schema: ToolDetailOutputSchema
    requires_auth: bool
    timeout_seconds: int
    rate_limit: int | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        from ..models.tool_detail_input_schema import ToolDetailInputSchema
        from ..models.tool_detail_output_schema import ToolDetailOutputSchema
        tool_id = self.tool_id

        name = self.name

        description = self.description

        category = self.category

        tags = self.tags



        input_schema = self.input_schema.to_dict()

        output_schema = self.output_schema.to_dict()

        requires_auth = self.requires_auth

        timeout_seconds = self.timeout_seconds

        rate_limit: int | None | Unset
        if isinstance(self.rate_limit, Unset):
            rate_limit = UNSET
        else:
            rate_limit = self.rate_limit


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "tool_id": tool_id,
            "name": name,
            "description": description,
            "category": category,
            "tags": tags,
            "input_schema": input_schema,
            "output_schema": output_schema,
            "requires_auth": requires_auth,
            "timeout_seconds": timeout_seconds,
        })
        if rate_limit is not UNSET:
            field_dict["rate_limit"] = rate_limit

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.tool_detail_input_schema import ToolDetailInputSchema
        from ..models.tool_detail_output_schema import ToolDetailOutputSchema
        d = dict(src_dict)
        tool_id = d.pop("tool_id")

        name = d.pop("name")

        description = d.pop("description")

        category = d.pop("category")

        tags = cast(list[str], d.pop("tags"))


        input_schema = ToolDetailInputSchema.from_dict(d.pop("input_schema"))




        output_schema = ToolDetailOutputSchema.from_dict(d.pop("output_schema"))




        requires_auth = d.pop("requires_auth")

        timeout_seconds = d.pop("timeout_seconds")

        def _parse_rate_limit(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        rate_limit = _parse_rate_limit(d.pop("rate_limit", UNSET))


        tool_detail = cls(
            tool_id=tool_id,
            name=name,
            description=description,
            category=category,
            tags=tags,
            input_schema=input_schema,
            output_schema=output_schema,
            requires_auth=requires_auth,
            timeout_seconds=timeout_seconds,
            rate_limit=rate_limit,
        )


        tool_detail.additional_properties = d
        return tool_detail

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
