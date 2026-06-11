from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast
from uuid import UUID

from attrs import define as _attrs_define
from attrs import field as _attrs_field
from dateutil.parser import isoparse

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.template_response_default_constraints_type_0 import (
        TemplateResponseDefaultConstraintsType0,
    )
    from ..models.template_response_default_plan_type_0 import (
        TemplateResponseDefaultPlanType0,
    )
    from ..models.template_response_default_tasks_type_0 import (
        TemplateResponseDefaultTasksType0,
    )


T = TypeVar("T", bound="TemplateResponse")


@_attrs_define
class TemplateResponse:
    """
    Attributes:
        id (UUID):
        name (str):
        description (None | str):
        category (None | str):
        is_public (bool):
        user_id (int):
        default_plan (list[Any] | None | TemplateResponseDefaultPlanType0 | Unset):
        default_tasks (list[Any] | None | TemplateResponseDefaultTasksType0 | Unset):
        default_constraints (list[Any] | None | TemplateResponseDefaultConstraintsType0 | Unset):
        created_at (datetime.datetime | None | Unset):
        updated_at (datetime.datetime | None | Unset):
    """

    id: UUID
    name: str
    description: None | str
    category: None | str
    is_public: bool
    user_id: int
    default_plan: list[Any] | None | TemplateResponseDefaultPlanType0 | Unset = UNSET
    default_tasks: list[Any] | None | TemplateResponseDefaultTasksType0 | Unset = UNSET
    default_constraints: list[Any] | None | TemplateResponseDefaultConstraintsType0 | Unset = UNSET
    created_at: datetime.datetime | None | Unset = UNSET
    updated_at: datetime.datetime | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.template_response_default_constraints_type_0 import (
            TemplateResponseDefaultConstraintsType0,
        )
        from ..models.template_response_default_plan_type_0 import (
            TemplateResponseDefaultPlanType0,
        )
        from ..models.template_response_default_tasks_type_0 import (
            TemplateResponseDefaultTasksType0,
        )

        id = str(self.id)

        name = self.name

        description: None | str
        description = self.description

        category: None | str
        category = self.category

        is_public = self.is_public

        user_id = self.user_id

        default_plan: dict[str, Any] | list[Any] | None | Unset
        if isinstance(self.default_plan, Unset):
            default_plan = UNSET
        elif isinstance(self.default_plan, TemplateResponseDefaultPlanType0):
            default_plan = self.default_plan.to_dict()
        elif isinstance(self.default_plan, list):
            default_plan = self.default_plan

        else:
            default_plan = self.default_plan

        default_tasks: dict[str, Any] | list[Any] | None | Unset
        if isinstance(self.default_tasks, Unset):
            default_tasks = UNSET
        elif isinstance(self.default_tasks, TemplateResponseDefaultTasksType0):
            default_tasks = self.default_tasks.to_dict()
        elif isinstance(self.default_tasks, list):
            default_tasks = self.default_tasks

        else:
            default_tasks = self.default_tasks

        default_constraints: dict[str, Any] | list[Any] | None | Unset
        if isinstance(self.default_constraints, Unset):
            default_constraints = UNSET
        elif isinstance(self.default_constraints, TemplateResponseDefaultConstraintsType0):
            default_constraints = self.default_constraints.to_dict()
        elif isinstance(self.default_constraints, list):
            default_constraints = self.default_constraints

        else:
            default_constraints = self.default_constraints

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
                "category": category,
                "is_public": is_public,
                "user_id": user_id,
            }
        )
        if default_plan is not UNSET:
            field_dict["default_plan"] = default_plan
        if default_tasks is not UNSET:
            field_dict["default_tasks"] = default_tasks
        if default_constraints is not UNSET:
            field_dict["default_constraints"] = default_constraints
        if created_at is not UNSET:
            field_dict["created_at"] = created_at
        if updated_at is not UNSET:
            field_dict["updated_at"] = updated_at

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.template_response_default_constraints_type_0 import (
            TemplateResponseDefaultConstraintsType0,
        )
        from ..models.template_response_default_plan_type_0 import (
            TemplateResponseDefaultPlanType0,
        )
        from ..models.template_response_default_tasks_type_0 import (
            TemplateResponseDefaultTasksType0,
        )

        d = dict(src_dict)
        id = UUID(d.pop("id"))

        name = d.pop("name")

        def _parse_description(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        description = _parse_description(d.pop("description"))

        def _parse_category(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        category = _parse_category(d.pop("category"))

        is_public = d.pop("is_public")

        user_id = d.pop("user_id")

        def _parse_default_plan(
            data: object,
        ) -> list[Any] | None | TemplateResponseDefaultPlanType0 | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                default_plan_type_0 = TemplateResponseDefaultPlanType0.from_dict(data)

                return default_plan_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            try:
                if not isinstance(data, list):
                    raise TypeError()
                default_plan_type_1 = cast(list[Any], data)

                return default_plan_type_1
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(list[Any] | None | TemplateResponseDefaultPlanType0 | Unset, data)

        default_plan = _parse_default_plan(d.pop("default_plan", UNSET))

        def _parse_default_tasks(
            data: object,
        ) -> list[Any] | None | TemplateResponseDefaultTasksType0 | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                default_tasks_type_0 = TemplateResponseDefaultTasksType0.from_dict(data)

                return default_tasks_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            try:
                if not isinstance(data, list):
                    raise TypeError()
                default_tasks_type_1 = cast(list[Any], data)

                return default_tasks_type_1
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(list[Any] | None | TemplateResponseDefaultTasksType0 | Unset, data)

        default_tasks = _parse_default_tasks(d.pop("default_tasks", UNSET))

        def _parse_default_constraints(
            data: object,
        ) -> list[Any] | None | TemplateResponseDefaultConstraintsType0 | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                default_constraints_type_0 = TemplateResponseDefaultConstraintsType0.from_dict(data)

                return default_constraints_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            try:
                if not isinstance(data, list):
                    raise TypeError()
                default_constraints_type_1 = cast(list[Any], data)

                return default_constraints_type_1
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(list[Any] | None | TemplateResponseDefaultConstraintsType0 | Unset, data)

        default_constraints = _parse_default_constraints(d.pop("default_constraints", UNSET))

        def _parse_created_at(data: object) -> datetime.datetime | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                created_at_type_0 = isoparse(data)

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
                updated_at_type_0 = isoparse(data)

                return updated_at_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(datetime.datetime | None | Unset, data)

        updated_at = _parse_updated_at(d.pop("updated_at", UNSET))

        template_response = cls(
            id=id,
            name=name,
            description=description,
            category=category,
            is_public=is_public,
            user_id=user_id,
            default_plan=default_plan,
            default_tasks=default_tasks,
            default_constraints=default_constraints,
            created_at=created_at,
            updated_at=updated_at,
        )

        template_response.additional_properties = d
        return template_response

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
