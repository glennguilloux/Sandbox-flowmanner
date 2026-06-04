from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..types import UNSET, Unset
from typing import cast






T = TypeVar("T", bound="RunEvaluationRequest")



@_attrs_define
class RunEvaluationRequest:
    """ 
        Attributes:
            dataset_id (str):
            model_name (None | str | Unset):
            system_prompt (None | str | Unset):
            temperature (float | Unset):  Default: 0.7.
     """

    dataset_id: str
    model_name: None | str | Unset = UNSET
    system_prompt: None | str | Unset = UNSET
    temperature: float | Unset = 0.7
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        dataset_id = self.dataset_id

        model_name: None | str | Unset
        if isinstance(self.model_name, Unset):
            model_name = UNSET
        else:
            model_name = self.model_name

        system_prompt: None | str | Unset
        if isinstance(self.system_prompt, Unset):
            system_prompt = UNSET
        else:
            system_prompt = self.system_prompt

        temperature = self.temperature


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "dataset_id": dataset_id,
        })
        if model_name is not UNSET:
            field_dict["model_name"] = model_name
        if system_prompt is not UNSET:
            field_dict["system_prompt"] = system_prompt
        if temperature is not UNSET:
            field_dict["temperature"] = temperature

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        dataset_id = d.pop("dataset_id")

        def _parse_model_name(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        model_name = _parse_model_name(d.pop("model_name", UNSET))


        def _parse_system_prompt(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        system_prompt = _parse_system_prompt(d.pop("system_prompt", UNSET))


        temperature = d.pop("temperature", UNSET)

        run_evaluation_request = cls(
            dataset_id=dataset_id,
            model_name=model_name,
            system_prompt=system_prompt,
            temperature=temperature,
        )


        run_evaluation_request.additional_properties = d
        return run_evaluation_request

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
