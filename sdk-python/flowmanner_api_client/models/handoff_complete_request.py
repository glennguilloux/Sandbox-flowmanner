from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.handoff_complete_request_result_metadata_type_0 import HandoffCompleteRequestResultMetadataType0


T = TypeVar("T", bound="HandoffCompleteRequest")


@_attrs_define
class HandoffCompleteRequest:
    """
    Attributes:
        result (str):
        result_metadata (HandoffCompleteRequestResultMetadataType0 | None | Unset):
    """

    result: str
    result_metadata: HandoffCompleteRequestResultMetadataType0 | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.handoff_complete_request_result_metadata_type_0 import HandoffCompleteRequestResultMetadataType0

        result = self.result

        result_metadata: dict[str, Any] | None | Unset
        if isinstance(self.result_metadata, Unset):
            result_metadata = UNSET
        elif isinstance(self.result_metadata, HandoffCompleteRequestResultMetadataType0):
            result_metadata = self.result_metadata.to_dict()
        else:
            result_metadata = self.result_metadata

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "result": result,
            }
        )
        if result_metadata is not UNSET:
            field_dict["result_metadata"] = result_metadata

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.handoff_complete_request_result_metadata_type_0 import HandoffCompleteRequestResultMetadataType0

        d = dict(src_dict)
        result = d.pop("result")

        def _parse_result_metadata(data: object) -> HandoffCompleteRequestResultMetadataType0 | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                result_metadata_type_0 = HandoffCompleteRequestResultMetadataType0.from_dict(data)

                return result_metadata_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(HandoffCompleteRequestResultMetadataType0 | None | Unset, data)

        result_metadata = _parse_result_metadata(d.pop("result_metadata", UNSET))

        handoff_complete_request = cls(
            result=result,
            result_metadata=result_metadata,
        )

        handoff_complete_request.additional_properties = d
        return handoff_complete_request

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
