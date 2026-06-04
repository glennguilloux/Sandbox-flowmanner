from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..types import UNSET, Unset
from typing import cast

if TYPE_CHECKING:
  from ..models.import_payload_data import ImportPayloadData





T = TypeVar("T", bound="ImportPayload")



@_attrs_define
class ImportPayload:
    """ 
        Attributes:
            data (ImportPayloadData):
            title_override (None | str | Unset):
     """

    data: ImportPayloadData
    title_override: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        from ..models.import_payload_data import ImportPayloadData
        data = self.data.to_dict()

        title_override: None | str | Unset
        if isinstance(self.title_override, Unset):
            title_override = UNSET
        else:
            title_override = self.title_override


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "data": data,
        })
        if title_override is not UNSET:
            field_dict["title_override"] = title_override

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.import_payload_data import ImportPayloadData
        d = dict(src_dict)
        data = ImportPayloadData.from_dict(d.pop("data"))




        def _parse_title_override(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        title_override = _parse_title_override(d.pop("title_override", UNSET))


        import_payload = cls(
            data=data,
            title_override=title_override,
        )


        import_payload.additional_properties = d
        return import_payload

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
