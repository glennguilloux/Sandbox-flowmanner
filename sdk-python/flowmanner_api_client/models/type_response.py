from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..types import UNSET, Unset
from typing import cast






T = TypeVar("T", bound="TypeResponse")



@_attrs_define
class TypeResponse:
    """ 
        Attributes:
            success (bool):
            stale_ref (bool | Unset):  Default: False.
            method (None | str | Unset):
            healed (bool | None | Unset):
            suggest_resnapshot (bool | None | Unset):
            error (None | str | Unset):
     """

    success: bool
    stale_ref: bool | Unset = False
    method: None | str | Unset = UNSET
    healed: bool | None | Unset = UNSET
    suggest_resnapshot: bool | None | Unset = UNSET
    error: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        success = self.success

        stale_ref = self.stale_ref

        method: None | str | Unset
        if isinstance(self.method, Unset):
            method = UNSET
        else:
            method = self.method

        healed: bool | None | Unset
        if isinstance(self.healed, Unset):
            healed = UNSET
        else:
            healed = self.healed

        suggest_resnapshot: bool | None | Unset
        if isinstance(self.suggest_resnapshot, Unset):
            suggest_resnapshot = UNSET
        else:
            suggest_resnapshot = self.suggest_resnapshot

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
        if stale_ref is not UNSET:
            field_dict["stale_ref"] = stale_ref
        if method is not UNSET:
            field_dict["method"] = method
        if healed is not UNSET:
            field_dict["healed"] = healed
        if suggest_resnapshot is not UNSET:
            field_dict["suggest_resnapshot"] = suggest_resnapshot
        if error is not UNSET:
            field_dict["error"] = error

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        success = d.pop("success")

        stale_ref = d.pop("stale_ref", UNSET)

        def _parse_method(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        method = _parse_method(d.pop("method", UNSET))


        def _parse_healed(data: object) -> bool | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(bool | None | Unset, data)

        healed = _parse_healed(d.pop("healed", UNSET))


        def _parse_suggest_resnapshot(data: object) -> bool | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(bool | None | Unset, data)

        suggest_resnapshot = _parse_suggest_resnapshot(d.pop("suggest_resnapshot", UNSET))


        def _parse_error(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        error = _parse_error(d.pop("error", UNSET))


        type_response = cls(
            success=success,
            stale_ref=stale_ref,
            method=method,
            healed=healed,
            suggest_resnapshot=suggest_resnapshot,
            error=error,
        )


        type_response.additional_properties = d
        return type_response

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
