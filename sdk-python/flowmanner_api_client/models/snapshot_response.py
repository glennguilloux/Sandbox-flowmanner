from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..types import UNSET, Unset
from typing import cast

if TYPE_CHECKING:
  from ..models.element_response import ElementResponse





T = TypeVar("T", bound="SnapshotResponse")



@_attrs_define
class SnapshotResponse:
    """ 
        Attributes:
            success (bool):
            elements (list[ElementResponse] | Unset):
            fingerprint (str | Unset):  Default: ''.
            url (None | str | Unset):
            title (None | str | Unset):
            error (None | str | Unset):
     """

    success: bool
    elements: list[ElementResponse] | Unset = UNSET
    fingerprint: str | Unset = ''
    url: None | str | Unset = UNSET
    title: None | str | Unset = UNSET
    error: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        from ..models.element_response import ElementResponse
        success = self.success

        elements: list[dict[str, Any]] | Unset = UNSET
        if not isinstance(self.elements, Unset):
            elements = []
            for elements_item_data in self.elements:
                elements_item = elements_item_data.to_dict()
                elements.append(elements_item)



        fingerprint = self.fingerprint

        url: None | str | Unset
        if isinstance(self.url, Unset):
            url = UNSET
        else:
            url = self.url

        title: None | str | Unset
        if isinstance(self.title, Unset):
            title = UNSET
        else:
            title = self.title

        error: None | str | Unset
        if isinstance(self.error, Unset):
            error = UNSET
        else:
            error = self.error


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "success": success,
        })
        if elements is not UNSET:
            field_dict["elements"] = elements
        if fingerprint is not UNSET:
            field_dict["fingerprint"] = fingerprint
        if url is not UNSET:
            field_dict["url"] = url
        if title is not UNSET:
            field_dict["title"] = title
        if error is not UNSET:
            field_dict["error"] = error

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.element_response import ElementResponse
        d = dict(src_dict)
        success = d.pop("success")

        _elements = d.pop("elements", UNSET)
        elements: list[ElementResponse] | Unset = UNSET
        if _elements is not UNSET:
            elements = []
            for elements_item_data in _elements:
                elements_item = ElementResponse.from_dict(elements_item_data)



                elements.append(elements_item)


        fingerprint = d.pop("fingerprint", UNSET)

        def _parse_url(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        url = _parse_url(d.pop("url", UNSET))


        def _parse_title(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        title = _parse_title(d.pop("title", UNSET))


        def _parse_error(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        error = _parse_error(d.pop("error", UNSET))


        snapshot_response = cls(
            success=success,
            elements=elements,
            fingerprint=fingerprint,
            url=url,
            title=title,
            error=error,
        )


        snapshot_response.additional_properties = d
        return snapshot_response

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
