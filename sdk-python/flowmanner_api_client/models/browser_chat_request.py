from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="BrowserChatRequest")


@_attrs_define
class BrowserChatRequest:
    """
    Attributes:
        message (str):
        model (None | str | Unset):
        temperature (float | None | Unset):
        max_tokens (int | None | Unset):
        system_prompt (None | str | Unset):
        byok_key (None | str | Unset):
        byok_base_url (None | str | Unset):
    """

    message: str
    model: None | str | Unset = UNSET
    temperature: float | None | Unset = UNSET
    max_tokens: int | None | Unset = UNSET
    system_prompt: None | str | Unset = UNSET
    byok_key: None | str | Unset = UNSET
    byok_base_url: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        message = self.message

        model: None | str | Unset
        if isinstance(self.model, Unset):
            model = UNSET
        else:
            model = self.model

        temperature: float | None | Unset
        if isinstance(self.temperature, Unset):
            temperature = UNSET
        else:
            temperature = self.temperature

        max_tokens: int | None | Unset
        if isinstance(self.max_tokens, Unset):
            max_tokens = UNSET
        else:
            max_tokens = self.max_tokens

        system_prompt: None | str | Unset
        if isinstance(self.system_prompt, Unset):
            system_prompt = UNSET
        else:
            system_prompt = self.system_prompt

        byok_key: None | str | Unset
        if isinstance(self.byok_key, Unset):
            byok_key = UNSET
        else:
            byok_key = self.byok_key

        byok_base_url: None | str | Unset
        if isinstance(self.byok_base_url, Unset):
            byok_base_url = UNSET
        else:
            byok_base_url = self.byok_base_url

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "message": message,
            }
        )
        if model is not UNSET:
            field_dict["model"] = model
        if temperature is not UNSET:
            field_dict["temperature"] = temperature
        if max_tokens is not UNSET:
            field_dict["max_tokens"] = max_tokens
        if system_prompt is not UNSET:
            field_dict["system_prompt"] = system_prompt
        if byok_key is not UNSET:
            field_dict["byok_key"] = byok_key
        if byok_base_url is not UNSET:
            field_dict["byok_base_url"] = byok_base_url

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        message = d.pop("message")

        def _parse_model(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        model = _parse_model(d.pop("model", UNSET))

        def _parse_temperature(data: object) -> float | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(float | None | Unset, data)

        temperature = _parse_temperature(d.pop("temperature", UNSET))

        def _parse_max_tokens(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        max_tokens = _parse_max_tokens(d.pop("max_tokens", UNSET))

        def _parse_system_prompt(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        system_prompt = _parse_system_prompt(d.pop("system_prompt", UNSET))

        def _parse_byok_key(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        byok_key = _parse_byok_key(d.pop("byok_key", UNSET))

        def _parse_byok_base_url(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        byok_base_url = _parse_byok_base_url(d.pop("byok_base_url", UNSET))

        browser_chat_request = cls(
            message=message,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            system_prompt=system_prompt,
            byok_key=byok_key,
            byok_base_url=byok_base_url,
        )

        browser_chat_request.additional_properties = d
        return browser_chat_request

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
