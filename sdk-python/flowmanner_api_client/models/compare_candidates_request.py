from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="CompareCandidatesRequest")


@_attrs_define
class CompareCandidatesRequest:
    """
    Attributes:
        dataset_id (str):
        candidate_models (list[str]):
        system_prompt (None | str | Unset):
        temperature (float | Unset):  Default: 0.7.
        judge_model (None | str | Unset):
    """

    dataset_id: str
    candidate_models: list[str]
    system_prompt: None | str | Unset = UNSET
    temperature: float | Unset = 0.7
    judge_model: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        dataset_id = self.dataset_id

        candidate_models = self.candidate_models

        system_prompt: None | str | Unset
        if isinstance(self.system_prompt, Unset):
            system_prompt = UNSET
        else:
            system_prompt = self.system_prompt

        temperature = self.temperature

        judge_model: None | str | Unset
        if isinstance(self.judge_model, Unset):
            judge_model = UNSET
        else:
            judge_model = self.judge_model

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "dataset_id": dataset_id,
                "candidate_models": candidate_models,
            }
        )
        if system_prompt is not UNSET:
            field_dict["system_prompt"] = system_prompt
        if temperature is not UNSET:
            field_dict["temperature"] = temperature
        if judge_model is not UNSET:
            field_dict["judge_model"] = judge_model

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        dataset_id = d.pop("dataset_id")

        candidate_models = cast(list[str], d.pop("candidate_models"))

        def _parse_system_prompt(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        system_prompt = _parse_system_prompt(d.pop("system_prompt", UNSET))

        temperature = d.pop("temperature", UNSET)

        def _parse_judge_model(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        judge_model = _parse_judge_model(d.pop("judge_model", UNSET))

        compare_candidates_request = cls(
            dataset_id=dataset_id,
            candidate_models=candidate_models,
            system_prompt=system_prompt,
            temperature=temperature,
            judge_model=judge_model,
        )

        compare_candidates_request.additional_properties = d
        return compare_candidates_request

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
