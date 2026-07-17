from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.generated_prompt_rationale import GeneratedPromptRationale
    from ..models.generated_prompt_usage import GeneratedPromptUsage


T = TypeVar("T", bound="GeneratedPrompt")


@_attrs_define
class GeneratedPrompt:
    """
    Attributes:
        system_prompt (str):
        rationale (GeneratedPromptRationale | Unset):
        recommended_model (str | Unset):  Default: 'deepseek/deepseek-v4-flash'.
        temperature (float | Unset):  Default: 0.7.
        usage (GeneratedPromptUsage | Unset):
    """

    system_prompt: str
    rationale: GeneratedPromptRationale | Unset = UNSET
    recommended_model: str | Unset = "deepseek/deepseek-v4-flash"
    temperature: float | Unset = 0.7
    usage: GeneratedPromptUsage | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        system_prompt = self.system_prompt

        rationale: dict[str, Any] | Unset = UNSET
        if not isinstance(self.rationale, Unset):
            rationale = self.rationale.to_dict()

        recommended_model = self.recommended_model

        temperature = self.temperature

        usage: dict[str, Any] | Unset = UNSET
        if not isinstance(self.usage, Unset):
            usage = self.usage.to_dict()

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "system_prompt": system_prompt,
            }
        )
        if rationale is not UNSET:
            field_dict["rationale"] = rationale
        if recommended_model is not UNSET:
            field_dict["recommended_model"] = recommended_model
        if temperature is not UNSET:
            field_dict["temperature"] = temperature
        if usage is not UNSET:
            field_dict["usage"] = usage

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.generated_prompt_rationale import GeneratedPromptRationale
        from ..models.generated_prompt_usage import GeneratedPromptUsage

        d = dict(src_dict)
        system_prompt = d.pop("system_prompt")

        _rationale = d.pop("rationale", UNSET)
        rationale: GeneratedPromptRationale | Unset
        if isinstance(_rationale, Unset):
            rationale = UNSET
        else:
            rationale = GeneratedPromptRationale.from_dict(_rationale)

        recommended_model = d.pop("recommended_model", UNSET)

        temperature = d.pop("temperature", UNSET)

        _usage = d.pop("usage", UNSET)
        usage: GeneratedPromptUsage | Unset
        if isinstance(_usage, Unset):
            usage = UNSET
        else:
            usage = GeneratedPromptUsage.from_dict(_usage)

        generated_prompt = cls(
            system_prompt=system_prompt,
            rationale=rationale,
            recommended_model=recommended_model,
            temperature=temperature,
            usage=usage,
        )

        generated_prompt.additional_properties = d
        return generated_prompt

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
