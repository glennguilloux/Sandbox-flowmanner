from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.http_integration_config_create_auth_config_type_0 import HttpIntegrationConfigCreateAuthConfigType0
    from ..models.http_integration_config_create_default_headers_type_0 import (
        HttpIntegrationConfigCreateDefaultHeadersType0,
    )


T = TypeVar("T", bound="HttpIntegrationConfigCreate")


@_attrs_define
class HttpIntegrationConfigCreate:
    """Request body for creating an HTTP integration config.

    Attributes:
        name (str):
        base_url (str):
        default_headers (HttpIntegrationConfigCreateDefaultHeadersType0 | None | Unset):
        auth_type (None | str | Unset):
        auth_config (HttpIntegrationConfigCreateAuthConfigType0 | None | Unset):
        timeout_seconds (int | Unset):  Default: 30.
        max_retries (int | Unset):  Default: 3.
    """

    name: str
    base_url: str
    default_headers: HttpIntegrationConfigCreateDefaultHeadersType0 | None | Unset = UNSET
    auth_type: None | str | Unset = UNSET
    auth_config: HttpIntegrationConfigCreateAuthConfigType0 | None | Unset = UNSET
    timeout_seconds: int | Unset = 30
    max_retries: int | Unset = 3
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.http_integration_config_create_auth_config_type_0 import (
            HttpIntegrationConfigCreateAuthConfigType0,
        )
        from ..models.http_integration_config_create_default_headers_type_0 import (
            HttpIntegrationConfigCreateDefaultHeadersType0,
        )

        name = self.name

        base_url = self.base_url

        default_headers: dict[str, Any] | None | Unset
        if isinstance(self.default_headers, Unset):
            default_headers = UNSET
        elif isinstance(self.default_headers, HttpIntegrationConfigCreateDefaultHeadersType0):
            default_headers = self.default_headers.to_dict()
        else:
            default_headers = self.default_headers

        auth_type: None | str | Unset
        if isinstance(self.auth_type, Unset):
            auth_type = UNSET
        else:
            auth_type = self.auth_type

        auth_config: dict[str, Any] | None | Unset
        if isinstance(self.auth_config, Unset):
            auth_config = UNSET
        elif isinstance(self.auth_config, HttpIntegrationConfigCreateAuthConfigType0):
            auth_config = self.auth_config.to_dict()
        else:
            auth_config = self.auth_config

        timeout_seconds = self.timeout_seconds

        max_retries = self.max_retries

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "name": name,
                "base_url": base_url,
            }
        )
        if default_headers is not UNSET:
            field_dict["default_headers"] = default_headers
        if auth_type is not UNSET:
            field_dict["auth_type"] = auth_type
        if auth_config is not UNSET:
            field_dict["auth_config"] = auth_config
        if timeout_seconds is not UNSET:
            field_dict["timeout_seconds"] = timeout_seconds
        if max_retries is not UNSET:
            field_dict["max_retries"] = max_retries

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.http_integration_config_create_auth_config_type_0 import (
            HttpIntegrationConfigCreateAuthConfigType0,
        )
        from ..models.http_integration_config_create_default_headers_type_0 import (
            HttpIntegrationConfigCreateDefaultHeadersType0,
        )

        d = dict(src_dict)
        name = d.pop("name")

        base_url = d.pop("base_url")

        def _parse_default_headers(data: object) -> HttpIntegrationConfigCreateDefaultHeadersType0 | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                default_headers_type_0 = HttpIntegrationConfigCreateDefaultHeadersType0.from_dict(data)

                return default_headers_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(HttpIntegrationConfigCreateDefaultHeadersType0 | None | Unset, data)

        default_headers = _parse_default_headers(d.pop("default_headers", UNSET))

        def _parse_auth_type(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        auth_type = _parse_auth_type(d.pop("auth_type", UNSET))

        def _parse_auth_config(data: object) -> HttpIntegrationConfigCreateAuthConfigType0 | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                auth_config_type_0 = HttpIntegrationConfigCreateAuthConfigType0.from_dict(data)

                return auth_config_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(HttpIntegrationConfigCreateAuthConfigType0 | None | Unset, data)

        auth_config = _parse_auth_config(d.pop("auth_config", UNSET))

        timeout_seconds = d.pop("timeout_seconds", UNSET)

        max_retries = d.pop("max_retries", UNSET)

        http_integration_config_create = cls(
            name=name,
            base_url=base_url,
            default_headers=default_headers,
            auth_type=auth_type,
            auth_config=auth_config,
            timeout_seconds=timeout_seconds,
            max_retries=max_retries,
        )

        http_integration_config_create.additional_properties = d
        return http_integration_config_create

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
