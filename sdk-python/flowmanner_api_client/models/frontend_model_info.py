from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..types import UNSET, Unset
from typing import cast






T = TypeVar("T", bound="FrontendModelInfo")



@_attrs_define
class FrontendModelInfo:
    """ 
        Attributes:
            model_id (str):
            display_name (str):
            status (str | Unset):  Default: 'available'.
            context_length (int | Unset):  Default: 0.
            vram_usage_gb (float | None | Unset):
            quantization (None | str | Unset):
            provider (None | str | Unset):
            description (None | str | Unset):
     """

    model_id: str
    display_name: str
    status: str | Unset = 'available'
    context_length: int | Unset = 0
    vram_usage_gb: float | None | Unset = UNSET
    quantization: None | str | Unset = UNSET
    provider: None | str | Unset = UNSET
    description: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        model_id = self.model_id

        display_name = self.display_name

        status = self.status

        context_length = self.context_length

        vram_usage_gb: float | None | Unset
        if isinstance(self.vram_usage_gb, Unset):
            vram_usage_gb = UNSET
        else:
            vram_usage_gb = self.vram_usage_gb

        quantization: None | str | Unset
        if isinstance(self.quantization, Unset):
            quantization = UNSET
        else:
            quantization = self.quantization

        provider: None | str | Unset
        if isinstance(self.provider, Unset):
            provider = UNSET
        else:
            provider = self.provider

        description: None | str | Unset
        if isinstance(self.description, Unset):
            description = UNSET
        else:
            description = self.description


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "model_id": model_id,
            "display_name": display_name,
        })
        if status is not UNSET:
            field_dict["status"] = status
        if context_length is not UNSET:
            field_dict["context_length"] = context_length
        if vram_usage_gb is not UNSET:
            field_dict["vram_usage_gb"] = vram_usage_gb
        if quantization is not UNSET:
            field_dict["quantization"] = quantization
        if provider is not UNSET:
            field_dict["provider"] = provider
        if description is not UNSET:
            field_dict["description"] = description

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        model_id = d.pop("model_id")

        display_name = d.pop("display_name")

        status = d.pop("status", UNSET)

        context_length = d.pop("context_length", UNSET)

        def _parse_vram_usage_gb(data: object) -> float | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(float | None | Unset, data)

        vram_usage_gb = _parse_vram_usage_gb(d.pop("vram_usage_gb", UNSET))


        def _parse_quantization(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        quantization = _parse_quantization(d.pop("quantization", UNSET))


        def _parse_provider(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        provider = _parse_provider(d.pop("provider", UNSET))


        def _parse_description(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        description = _parse_description(d.pop("description", UNSET))


        frontend_model_info = cls(
            model_id=model_id,
            display_name=display_name,
            status=status,
            context_length=context_length,
            vram_usage_gb=vram_usage_gb,
            quantization=quantization,
            provider=provider,
            description=description,
        )


        frontend_model_info.additional_properties = d
        return frontend_model_info

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
