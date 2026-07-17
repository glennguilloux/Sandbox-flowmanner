from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.template_workflow_step import TemplateWorkflowStep


T = TypeVar("T", bound="TemplateWorkflow")


@_attrs_define
class TemplateWorkflow:
    """
    Attributes:
        id (str):
        name (str):
        description (str):
        icon (str):
        required_integrations (list[str]):
        category (str):
        difficulty (str):
        estimated_time (str):
        steps (list[TemplateWorkflowStep]):
    """

    id: str
    name: str
    description: str
    icon: str
    required_integrations: list[str]
    category: str
    difficulty: str
    estimated_time: str
    steps: list[TemplateWorkflowStep]
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        id = self.id

        name = self.name

        description = self.description

        icon = self.icon

        required_integrations = self.required_integrations

        category = self.category

        difficulty = self.difficulty

        estimated_time = self.estimated_time

        steps = []
        for steps_item_data in self.steps:
            steps_item = steps_item_data.to_dict()
            steps.append(steps_item)

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "id": id,
                "name": name,
                "description": description,
                "icon": icon,
                "required_integrations": required_integrations,
                "category": category,
                "difficulty": difficulty,
                "estimated_time": estimated_time,
                "steps": steps,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.template_workflow_step import TemplateWorkflowStep

        d = dict(src_dict)
        id = d.pop("id")

        name = d.pop("name")

        description = d.pop("description")

        icon = d.pop("icon")

        required_integrations = cast(list[str], d.pop("required_integrations"))

        category = d.pop("category")

        difficulty = d.pop("difficulty")

        estimated_time = d.pop("estimated_time")

        steps = []
        _steps = d.pop("steps")
        for steps_item_data in _steps:
            steps_item = TemplateWorkflowStep.from_dict(steps_item_data)

            steps.append(steps_item)

        template_workflow = cls(
            id=id,
            name=name,
            description=description,
            icon=icon,
            required_integrations=required_integrations,
            category=category,
            difficulty=difficulty,
            estimated_time=estimated_time,
            steps=steps,
        )

        template_workflow.additional_properties = d
        return template_workflow

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
