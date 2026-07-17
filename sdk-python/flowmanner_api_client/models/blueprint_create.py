from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.blueprint_create_input_schema_type_0 import BlueprintCreateInputSchemaType0
    from ..models.blueprint_create_output_schema_type_0 import BlueprintCreateOutputSchemaType0
    from ..models.blueprint_definition import BlueprintDefinition


T = TypeVar("T", bound="BlueprintCreate")


@_attrs_define
class BlueprintCreate:
    """Create a new blueprint.

    Attributes:
        title (str):
        description (str | Unset):  Default: ''.
        blueprint_type (str | Unset):  Default: 'solo'.
        definition (BlueprintDefinition | None | Unset):
        input_schema (BlueprintCreateInputSchemaType0 | None | Unset):
        output_schema (BlueprintCreateOutputSchemaType0 | None | Unset):
        tags (list[str] | None | Unset):
        category (None | str | Unset):
        icon (None | str | Unset):
    """

    title: str
    description: str | Unset = ""
    blueprint_type: str | Unset = "solo"
    definition: BlueprintDefinition | None | Unset = UNSET
    input_schema: BlueprintCreateInputSchemaType0 | None | Unset = UNSET
    output_schema: BlueprintCreateOutputSchemaType0 | None | Unset = UNSET
    tags: list[str] | None | Unset = UNSET
    category: None | str | Unset = UNSET
    icon: None | str | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        from ..models.blueprint_create_input_schema_type_0 import BlueprintCreateInputSchemaType0
        from ..models.blueprint_create_output_schema_type_0 import BlueprintCreateOutputSchemaType0
        from ..models.blueprint_definition import BlueprintDefinition

        title = self.title

        description = self.description

        blueprint_type = self.blueprint_type

        definition: dict[str, Any] | None | Unset
        if isinstance(self.definition, Unset):
            definition = UNSET
        elif isinstance(self.definition, BlueprintDefinition):
            definition = self.definition.to_dict()
        else:
            definition = self.definition

        input_schema: dict[str, Any] | None | Unset
        if isinstance(self.input_schema, Unset):
            input_schema = UNSET
        elif isinstance(self.input_schema, BlueprintCreateInputSchemaType0):
            input_schema = self.input_schema.to_dict()
        else:
            input_schema = self.input_schema

        output_schema: dict[str, Any] | None | Unset
        if isinstance(self.output_schema, Unset):
            output_schema = UNSET
        elif isinstance(self.output_schema, BlueprintCreateOutputSchemaType0):
            output_schema = self.output_schema.to_dict()
        else:
            output_schema = self.output_schema

        tags: list[str] | None | Unset
        if isinstance(self.tags, Unset):
            tags = UNSET
        elif isinstance(self.tags, list):
            tags = self.tags

        else:
            tags = self.tags

        category: None | str | Unset
        if isinstance(self.category, Unset):
            category = UNSET
        else:
            category = self.category

        icon: None | str | Unset
        if isinstance(self.icon, Unset):
            icon = UNSET
        else:
            icon = self.icon

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "title": title,
            }
        )
        if description is not UNSET:
            field_dict["description"] = description
        if blueprint_type is not UNSET:
            field_dict["blueprint_type"] = blueprint_type
        if definition is not UNSET:
            field_dict["definition"] = definition
        if input_schema is not UNSET:
            field_dict["input_schema"] = input_schema
        if output_schema is not UNSET:
            field_dict["output_schema"] = output_schema
        if tags is not UNSET:
            field_dict["tags"] = tags
        if category is not UNSET:
            field_dict["category"] = category
        if icon is not UNSET:
            field_dict["icon"] = icon

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.blueprint_create_input_schema_type_0 import BlueprintCreateInputSchemaType0
        from ..models.blueprint_create_output_schema_type_0 import BlueprintCreateOutputSchemaType0
        from ..models.blueprint_definition import BlueprintDefinition

        d = dict(src_dict)
        title = d.pop("title")

        description = d.pop("description", UNSET)

        blueprint_type = d.pop("blueprint_type", UNSET)

        def _parse_definition(data: object) -> BlueprintDefinition | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                definition_type_0 = BlueprintDefinition.from_dict(data)

                return definition_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(BlueprintDefinition | None | Unset, data)

        definition = _parse_definition(d.pop("definition", UNSET))

        def _parse_input_schema(data: object) -> BlueprintCreateInputSchemaType0 | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                input_schema_type_0 = BlueprintCreateInputSchemaType0.from_dict(data)

                return input_schema_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(BlueprintCreateInputSchemaType0 | None | Unset, data)

        input_schema = _parse_input_schema(d.pop("input_schema", UNSET))

        def _parse_output_schema(data: object) -> BlueprintCreateOutputSchemaType0 | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                output_schema_type_0 = BlueprintCreateOutputSchemaType0.from_dict(data)

                return output_schema_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(BlueprintCreateOutputSchemaType0 | None | Unset, data)

        output_schema = _parse_output_schema(d.pop("output_schema", UNSET))

        def _parse_tags(data: object) -> list[str] | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, list):
                    raise TypeError()
                tags_type_0 = cast(list[str], data)

                return tags_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(list[str] | None | Unset, data)

        tags = _parse_tags(d.pop("tags", UNSET))

        def _parse_category(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        category = _parse_category(d.pop("category", UNSET))

        def _parse_icon(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        icon = _parse_icon(d.pop("icon", UNSET))

        blueprint_create = cls(
            title=title,
            description=description,
            blueprint_type=blueprint_type,
            definition=definition,
            input_schema=input_schema,
            output_schema=output_schema,
            tags=tags,
            category=category,
            icon=icon,
        )

        return blueprint_create
