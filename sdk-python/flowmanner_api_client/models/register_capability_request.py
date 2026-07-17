from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.register_capability_request_metadata_type_0 import RegisterCapabilityRequestMetadataType0


T = TypeVar("T", bound="RegisterCapabilityRequest")


@_attrs_define
class RegisterCapabilityRequest:
    """
    Attributes:
        agent_id (str):
        name (str):
        description (str | Unset):  Default: ''.
        task_types (list[str] | Unset):
        tools (list[str] | Unset):
        confidence_score (float | Unset):  Default: 0.5.
        metadata (None | RegisterCapabilityRequestMetadataType0 | Unset):
    """

    agent_id: str
    name: str
    description: str | Unset = ""
    task_types: list[str] | Unset = UNSET
    tools: list[str] | Unset = UNSET
    confidence_score: float | Unset = 0.5
    metadata: None | RegisterCapabilityRequestMetadataType0 | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.register_capability_request_metadata_type_0 import RegisterCapabilityRequestMetadataType0

        agent_id = self.agent_id

        name = self.name

        description = self.description

        task_types: list[str] | Unset = UNSET
        if not isinstance(self.task_types, Unset):
            task_types = self.task_types

        tools: list[str] | Unset = UNSET
        if not isinstance(self.tools, Unset):
            tools = self.tools

        confidence_score = self.confidence_score

        metadata: dict[str, Any] | None | Unset
        if isinstance(self.metadata, Unset):
            metadata = UNSET
        elif isinstance(self.metadata, RegisterCapabilityRequestMetadataType0):
            metadata = self.metadata.to_dict()
        else:
            metadata = self.metadata

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "agent_id": agent_id,
                "name": name,
            }
        )
        if description is not UNSET:
            field_dict["description"] = description
        if task_types is not UNSET:
            field_dict["task_types"] = task_types
        if tools is not UNSET:
            field_dict["tools"] = tools
        if confidence_score is not UNSET:
            field_dict["confidence_score"] = confidence_score
        if metadata is not UNSET:
            field_dict["metadata"] = metadata

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.register_capability_request_metadata_type_0 import RegisterCapabilityRequestMetadataType0

        d = dict(src_dict)
        agent_id = d.pop("agent_id")

        name = d.pop("name")

        description = d.pop("description", UNSET)

        task_types = cast(list[str], d.pop("task_types", UNSET))

        tools = cast(list[str], d.pop("tools", UNSET))

        confidence_score = d.pop("confidence_score", UNSET)

        def _parse_metadata(data: object) -> None | RegisterCapabilityRequestMetadataType0 | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                metadata_type_0 = RegisterCapabilityRequestMetadataType0.from_dict(data)

                return metadata_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | RegisterCapabilityRequestMetadataType0 | Unset, data)

        metadata = _parse_metadata(d.pop("metadata", UNSET))

        register_capability_request = cls(
            agent_id=agent_id,
            name=name,
            description=description,
            task_types=task_types,
            tools=tools,
            confidence_score=confidence_score,
            metadata=metadata,
        )

        register_capability_request.additional_properties = d
        return register_capability_request

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
