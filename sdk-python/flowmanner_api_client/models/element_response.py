from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..types import UNSET, Unset
from typing import cast

if TYPE_CHECKING:
  from ..models.element_response_bbox_type_0 import ElementResponseBboxType0





T = TypeVar("T", bound="ElementResponse")



@_attrs_define
class ElementResponse:
    """ 
        Attributes:
            ref (str):
            tag (str):
            text (str):
            role (str):
            bbox (ElementResponseBboxType0 | None | Unset):
     """

    ref: str
    tag: str
    text: str
    role: str
    bbox: ElementResponseBboxType0 | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        from ..models.element_response_bbox_type_0 import ElementResponseBboxType0
        ref = self.ref

        tag = self.tag

        text = self.text

        role = self.role

        bbox: dict[str, Any] | None | Unset
        if isinstance(self.bbox, Unset):
            bbox = UNSET
        elif isinstance(self.bbox, ElementResponseBboxType0):
            bbox = self.bbox.to_dict()
        else:
            bbox = self.bbox


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "ref": ref,
            "tag": tag,
            "text": text,
            "role": role,
        })
        if bbox is not UNSET:
            field_dict["bbox"] = bbox

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.element_response_bbox_type_0 import ElementResponseBboxType0
        d = dict(src_dict)
        ref = d.pop("ref")

        tag = d.pop("tag")

        text = d.pop("text")

        role = d.pop("role")

        def _parse_bbox(data: object) -> ElementResponseBboxType0 | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                bbox_type_0 = ElementResponseBboxType0.from_dict(data)



                return bbox_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(ElementResponseBboxType0 | None | Unset, data)

        bbox = _parse_bbox(d.pop("bbox", UNSET))


        element_response = cls(
            ref=ref,
            tag=tag,
            text=text,
            role=role,
            bbox=bbox,
        )


        element_response.additional_properties = d
        return element_response

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
