from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..types import UNSET, Unset
from typing import cast

if TYPE_CHECKING:
  from ..models.template_create_default_constraints_type_0 import TemplateCreateDefaultConstraintsType0
  from ..models.template_create_default_plan_type_0 import TemplateCreateDefaultPlanType0
  from ..models.template_create_default_tasks_type_0 import TemplateCreateDefaultTasksType0





T = TypeVar("T", bound="TemplateCreate")



@_attrs_define
class TemplateCreate:
    """ 
        Attributes:
            name (str):
            description (None | str | Unset):
            category (None | str | Unset):
            is_public (bool | Unset):  Default: False.
            default_plan (None | TemplateCreateDefaultPlanType0 | Unset):
            default_tasks (None | TemplateCreateDefaultTasksType0 | Unset):
            default_constraints (None | TemplateCreateDefaultConstraintsType0 | Unset):
     """

    name: str
    description: None | str | Unset = UNSET
    category: None | str | Unset = UNSET
    is_public: bool | Unset = False
    default_plan: None | TemplateCreateDefaultPlanType0 | Unset = UNSET
    default_tasks: None | TemplateCreateDefaultTasksType0 | Unset = UNSET
    default_constraints: None | TemplateCreateDefaultConstraintsType0 | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        from ..models.template_create_default_constraints_type_0 import TemplateCreateDefaultConstraintsType0
        from ..models.template_create_default_plan_type_0 import TemplateCreateDefaultPlanType0
        from ..models.template_create_default_tasks_type_0 import TemplateCreateDefaultTasksType0
        name = self.name

        description: None | str | Unset
        if isinstance(self.description, Unset):
            description = UNSET
        else:
            description = self.description

        category: None | str | Unset
        if isinstance(self.category, Unset):
            category = UNSET
        else:
            category = self.category

        is_public = self.is_public

        default_plan: dict[str, Any] | None | Unset
        if isinstance(self.default_plan, Unset):
            default_plan = UNSET
        elif isinstance(self.default_plan, TemplateCreateDefaultPlanType0):
            default_plan = self.default_plan.to_dict()
        else:
            default_plan = self.default_plan

        default_tasks: dict[str, Any] | None | Unset
        if isinstance(self.default_tasks, Unset):
            default_tasks = UNSET
        elif isinstance(self.default_tasks, TemplateCreateDefaultTasksType0):
            default_tasks = self.default_tasks.to_dict()
        else:
            default_tasks = self.default_tasks

        default_constraints: dict[str, Any] | None | Unset
        if isinstance(self.default_constraints, Unset):
            default_constraints = UNSET
        elif isinstance(self.default_constraints, TemplateCreateDefaultConstraintsType0):
            default_constraints = self.default_constraints.to_dict()
        else:
            default_constraints = self.default_constraints


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "name": name,
        })
        if description is not UNSET:
            field_dict["description"] = description
        if category is not UNSET:
            field_dict["category"] = category
        if is_public is not UNSET:
            field_dict["is_public"] = is_public
        if default_plan is not UNSET:
            field_dict["default_plan"] = default_plan
        if default_tasks is not UNSET:
            field_dict["default_tasks"] = default_tasks
        if default_constraints is not UNSET:
            field_dict["default_constraints"] = default_constraints

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.template_create_default_constraints_type_0 import TemplateCreateDefaultConstraintsType0
        from ..models.template_create_default_plan_type_0 import TemplateCreateDefaultPlanType0
        from ..models.template_create_default_tasks_type_0 import TemplateCreateDefaultTasksType0
        d = dict(src_dict)
        name = d.pop("name")

        def _parse_description(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        description = _parse_description(d.pop("description", UNSET))


        def _parse_category(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        category = _parse_category(d.pop("category", UNSET))


        is_public = d.pop("is_public", UNSET)

        def _parse_default_plan(data: object) -> None | TemplateCreateDefaultPlanType0 | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                default_plan_type_0 = TemplateCreateDefaultPlanType0.from_dict(data)



                return default_plan_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | TemplateCreateDefaultPlanType0 | Unset, data)

        default_plan = _parse_default_plan(d.pop("default_plan", UNSET))


        def _parse_default_tasks(data: object) -> None | TemplateCreateDefaultTasksType0 | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                default_tasks_type_0 = TemplateCreateDefaultTasksType0.from_dict(data)



                return default_tasks_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | TemplateCreateDefaultTasksType0 | Unset, data)

        default_tasks = _parse_default_tasks(d.pop("default_tasks", UNSET))


        def _parse_default_constraints(data: object) -> None | TemplateCreateDefaultConstraintsType0 | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                default_constraints_type_0 = TemplateCreateDefaultConstraintsType0.from_dict(data)



                return default_constraints_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | TemplateCreateDefaultConstraintsType0 | Unset, data)

        default_constraints = _parse_default_constraints(d.pop("default_constraints", UNSET))


        template_create = cls(
            name=name,
            description=description,
            category=category,
            is_public=is_public,
            default_plan=default_plan,
            default_tasks=default_tasks,
            default_constraints=default_constraints,
        )


        template_create.additional_properties = d
        return template_create

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
