from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

T = TypeVar("T", bound="CreateFromTemplateResponse")


@_attrs_define
class CreateFromTemplateResponse:
    """
    Attributes:
        mission_id (str):
        title (str):
        status (str):
        template_id (str):
    """

    mission_id: str
    title: str
    status: str
    template_id: str
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        mission_id = self.mission_id

        title = self.title

        status = self.status

        template_id = self.template_id

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "mission_id": mission_id,
                "title": title,
                "status": status,
                "template_id": template_id,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        mission_id = d.pop("mission_id")

        title = d.pop("title")

        status = d.pop("status")

        template_id = d.pop("template_id")

        create_from_template_response = cls(
            mission_id=mission_id,
            title=title,
            status=status,
            template_id=template_id,
        )

        create_from_template_response.additional_properties = d
        return create_from_template_response

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
