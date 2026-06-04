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
  from ..models.graph_workflow_response_graph_definition_type_0 import GraphWorkflowResponseGraphDefinitionType0





T = TypeVar("T", bound="GraphWorkflowResponse")



@_attrs_define
class GraphWorkflowResponse:
    """ 
        Attributes:
            id (str):
            name (str):
            created_at (datetime.datetime):
            updated_at (datetime.datetime):
            description (None | str | Unset):
            graph_definition (GraphWorkflowResponseGraphDefinitionType0 | None | Unset):
            status (str | Unset):  Default: 'draft'.
            user_id (int | None | Unset):
     """

    id: str
    name: str
    created_at: datetime.datetime
    updated_at: datetime.datetime
    description: None | str | Unset = UNSET
    graph_definition: GraphWorkflowResponseGraphDefinitionType0 | None | Unset = UNSET
    status: str | Unset = 'draft'
    user_id: int | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        from ..models.graph_workflow_response_graph_definition_type_0 import GraphWorkflowResponseGraphDefinitionType0
        id = self.id

        name = self.name

        created_at = self.created_at.isoformat()

        updated_at = self.updated_at.isoformat()

        description: None | str | Unset
        if isinstance(self.description, Unset):
            description = UNSET
        else:
            description = self.description

        graph_definition: dict[str, Any] | None | Unset
        if isinstance(self.graph_definition, Unset):
            graph_definition = UNSET
        elif isinstance(self.graph_definition, GraphWorkflowResponseGraphDefinitionType0):
            graph_definition = self.graph_definition.to_dict()
        else:
            graph_definition = self.graph_definition

        status = self.status

        user_id: int | None | Unset
        if isinstance(self.user_id, Unset):
            user_id = UNSET
        else:
            user_id = self.user_id


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "id": id,
            "name": name,
            "created_at": created_at,
            "updated_at": updated_at,
        })
        if description is not UNSET:
            field_dict["description"] = description
        if graph_definition is not UNSET:
            field_dict["graph_definition"] = graph_definition
        if status is not UNSET:
            field_dict["status"] = status
        if user_id is not UNSET:
            field_dict["user_id"] = user_id

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.graph_workflow_response_graph_definition_type_0 import GraphWorkflowResponseGraphDefinitionType0
        d = dict(src_dict)
        id = d.pop("id")

        name = d.pop("name")

        created_at = isoparse(d.pop("created_at"))




        updated_at = isoparse(d.pop("updated_at"))




        def _parse_description(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        description = _parse_description(d.pop("description", UNSET))


        def _parse_graph_definition(data: object) -> GraphWorkflowResponseGraphDefinitionType0 | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                graph_definition_type_0 = GraphWorkflowResponseGraphDefinitionType0.from_dict(data)



                return graph_definition_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(GraphWorkflowResponseGraphDefinitionType0 | None | Unset, data)

        graph_definition = _parse_graph_definition(d.pop("graph_definition", UNSET))


        status = d.pop("status", UNSET)

        def _parse_user_id(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        user_id = _parse_user_id(d.pop("user_id", UNSET))


        graph_workflow_response = cls(
            id=id,
            name=name,
            created_at=created_at,
            updated_at=updated_at,
            description=description,
            graph_definition=graph_definition,
            status=status,
            user_id=user_id,
        )


        graph_workflow_response.additional_properties = d
        return graph_workflow_response

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
