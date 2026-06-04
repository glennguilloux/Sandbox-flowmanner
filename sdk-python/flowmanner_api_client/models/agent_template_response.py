from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..types import UNSET, Unset
from dateutil.parser import isoparse
from typing import cast
import datetime

if TYPE_CHECKING:
  from ..models.agent_template_response_config_data_type_0 import AgentTemplateResponseConfigDataType0





T = TypeVar("T", bound="AgentTemplateResponse")



@_attrs_define
class AgentTemplateResponse:
    """ 
        Attributes:
            id (str):
            template_id (str):
            name (str):
            description (None | str):
            agent_type (str):
            system_prompt (None | str):
            is_active (bool | None):
            created_at (datetime.datetime | None):
            updated_at (datetime.datetime | None):
            config_data (AgentTemplateResponseConfigDataType0 | None | Unset):
     """

    id: str
    template_id: str
    name: str
    description: None | str
    agent_type: str
    system_prompt: None | str
    is_active: bool | None
    created_at: datetime.datetime | None
    updated_at: datetime.datetime | None
    config_data: AgentTemplateResponseConfigDataType0 | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        from ..models.agent_template_response_config_data_type_0 import AgentTemplateResponseConfigDataType0
        id = self.id

        template_id = self.template_id

        name = self.name

        description: None | str
        description = self.description

        agent_type = self.agent_type

        system_prompt: None | str
        system_prompt = self.system_prompt

        is_active: bool | None
        is_active = self.is_active

        created_at: None | str
        if isinstance(self.created_at, datetime.datetime):
            created_at = self.created_at.isoformat()
        else:
            created_at = self.created_at

        updated_at: None | str
        if isinstance(self.updated_at, datetime.datetime):
            updated_at = self.updated_at.isoformat()
        else:
            updated_at = self.updated_at

        config_data: dict[str, Any] | None | Unset
        if isinstance(self.config_data, Unset):
            config_data = UNSET
        elif isinstance(self.config_data, AgentTemplateResponseConfigDataType0):
            config_data = self.config_data.to_dict()
        else:
            config_data = self.config_data


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "id": id,
            "template_id": template_id,
            "name": name,
            "description": description,
            "agent_type": agent_type,
            "system_prompt": system_prompt,
            "is_active": is_active,
            "created_at": created_at,
            "updated_at": updated_at,
        })
        if config_data is not UNSET:
            field_dict["config_data"] = config_data

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.agent_template_response_config_data_type_0 import AgentTemplateResponseConfigDataType0
        d = dict(src_dict)
        id = d.pop("id")

        template_id = d.pop("template_id")

        name = d.pop("name")

        def _parse_description(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        description = _parse_description(d.pop("description"))


        agent_type = d.pop("agent_type")

        def _parse_system_prompt(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        system_prompt = _parse_system_prompt(d.pop("system_prompt"))


        def _parse_is_active(data: object) -> bool | None:
            if data is None:
                return data
            return cast(bool | None, data)

        is_active = _parse_is_active(d.pop("is_active"))


        def _parse_created_at(data: object) -> datetime.datetime | None:
            if data is None:
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                created_at_type_0 = isoparse(data)



                return created_at_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(datetime.datetime | None, data)

        created_at = _parse_created_at(d.pop("created_at"))


        def _parse_updated_at(data: object) -> datetime.datetime | None:
            if data is None:
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                updated_at_type_0 = isoparse(data)



                return updated_at_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(datetime.datetime | None, data)

        updated_at = _parse_updated_at(d.pop("updated_at"))


        def _parse_config_data(data: object) -> AgentTemplateResponseConfigDataType0 | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                config_data_type_0 = AgentTemplateResponseConfigDataType0.from_dict(data)



                return config_data_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(AgentTemplateResponseConfigDataType0 | None | Unset, data)

        config_data = _parse_config_data(d.pop("config_data", UNSET))


        agent_template_response = cls(
            id=id,
            template_id=template_id,
            name=name,
            description=description,
            agent_type=agent_type,
            system_prompt=system_prompt,
            is_active=is_active,
            created_at=created_at,
            updated_at=updated_at,
            config_data=config_data,
        )


        agent_template_response.additional_properties = d
        return agent_template_response

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
