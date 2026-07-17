from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.blueprint_definition import BlueprintDefinition
    from ..models.blueprint_update_input_schema_type_0 import BlueprintUpdateInputSchemaType0
    from ..models.blueprint_update_output_schema_type_0 import BlueprintUpdateOutputSchemaType0


T = TypeVar("T", bound="BlueprintUpdate")


@_attrs_define
class BlueprintUpdate:
    """Update an existing blueprint.

    Attributes:
        title (None | str | Unset):
        description (None | str | Unset):
        definition (BlueprintDefinition | None | Unset):
        status (None | str | Unset):
        input_schema (BlueprintUpdateInputSchemaType0 | None | Unset):
        output_schema (BlueprintUpdateOutputSchemaType0 | None | Unset):
        tags (list[str] | None | Unset):
        category (None | str | Unset):
        icon (None | str | Unset):
    """

    title: None | str | Unset = UNSET
    description: None | str | Unset = UNSET
    definition: BlueprintDefinition | None | Unset = UNSET
    status: None | str | Unset = UNSET
    input_schema: BlueprintUpdateInputSchemaType0 | None | Unset = UNSET
    output_schema: BlueprintUpdateOutputSchemaType0 | None | Unset = UNSET
    tags: list[str] | None | Unset = UNSET
    category: None | str | Unset = UNSET
    icon: None | str | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        from ..models.blueprint_definition import BlueprintDefinition
        from ..models.blueprint_update_input_schema_type_0 import BlueprintUpdateInputSchemaType0
        from ..models.blueprint_update_output_schema_type_0 import BlueprintUpdateOutputSchemaType0

        title: None | str | Unset
        if isinstance(self.title, Unset):
            title = UNSET
        else:
            title = self.title

        description: None | str | Unset
        if isinstance(self.description, Unset):
            description = UNSET
        else:
            description = self.description

        definition: dict[str, Any] | None | Unset
        if isinstance(self.definition, Unset):
            definition = UNSET
        elif isinstance(self.definition, BlueprintDefinition):
            definition = self.definition.to_dict()
        else:
            definition = self.definition

        status: None | str | Unset
        if isinstance(self.status, Unset):
            status = UNSET
        else:
            status = self.status

        input_schema: dict[str, Any] | None | Unset
        if isinstance(self.input_schema, Unset):
            input_schema = UNSET
        elif isinstance(self.input_schema, BlueprintUpdateInputSchemaType0):
            input_schema = self.input_schema.to_dict()
        else:
            input_schema = self.input_schema

        output_schema: dict[str, Any] | None | Unset
        if isinstance(self.output_schema, Unset):
            output_schema = UNSET
        elif isinstance(self.output_schema, BlueprintUpdateOutputSchemaType0):
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

        field_dict.update({})
        if title is not UNSET:
            field_dict["title"] = title
        if description is not UNSET:
            field_dict["description"] = description
        if definition is not UNSET:
            field_dict["definition"] = definition
        if status is not UNSET:
            field_dict["status"] = status
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
        from ..models.blueprint_definition import BlueprintDefinition
        from ..models.blueprint_update_input_schema_type_0 import BlueprintUpdateInputSchemaType0
        from ..models.blueprint_update_output_schema_type_0 import BlueprintUpdateOutputSchemaType0

        d = dict(src_dict)

        def _parse_title(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        title = _parse_title(d.pop("title", UNSET))

        def _parse_description(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        description = _parse_description(d.pop("description", UNSET))

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

        def _parse_status(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        status = _parse_status(d.pop("status", UNSET))

        def _parse_input_schema(data: object) -> BlueprintUpdateInputSchemaType0 | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                input_schema_type_0 = BlueprintUpdateInputSchemaType0.from_dict(data)

                return input_schema_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(BlueprintUpdateInputSchemaType0 | None | Unset, data)

        input_schema = _parse_input_schema(d.pop("input_schema", UNSET))

        def _parse_output_schema(data: object) -> BlueprintUpdateOutputSchemaType0 | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                output_schema_type_0 = BlueprintUpdateOutputSchemaType0.from_dict(data)

                return output_schema_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(BlueprintUpdateOutputSchemaType0 | None | Unset, data)

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

        blueprint_update = cls(
            title=title,
            description=description,
            definition=definition,
            status=status,
            input_schema=input_schema,
            output_schema=output_schema,
            tags=tags,
            category=category,
            icon=icon,
        )

        return blueprint_update
