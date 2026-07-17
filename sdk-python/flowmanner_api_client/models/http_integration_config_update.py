from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.http_integration_config_update_auth_config_type_0 import HttpIntegrationConfigUpdateAuthConfigType0
    from ..models.http_integration_config_update_default_headers_type_0 import (
        HttpIntegrationConfigUpdateDefaultHeadersType0,
    )


T = TypeVar("T", bound="HttpIntegrationConfigUpdate")


@_attrs_define
class HttpIntegrationConfigUpdate:
    """Request body for updating an HTTP integration config.

    Attributes:
        name (None | str | Unset):
        base_url (None | str | Unset):
        default_headers (HttpIntegrationConfigUpdateDefaultHeadersType0 | None | Unset):
        auth_type (None | str | Unset):
        auth_config (HttpIntegrationConfigUpdateAuthConfigType0 | None | Unset):
        timeout_seconds (int | None | Unset):
        max_retries (int | None | Unset):
        is_active (bool | None | Unset):
    """

    name: None | str | Unset = UNSET
    base_url: None | str | Unset = UNSET
    default_headers: HttpIntegrationConfigUpdateDefaultHeadersType0 | None | Unset = UNSET
    auth_type: None | str | Unset = UNSET
    auth_config: HttpIntegrationConfigUpdateAuthConfigType0 | None | Unset = UNSET
    timeout_seconds: int | None | Unset = UNSET
    max_retries: int | None | Unset = UNSET
    is_active: bool | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.http_integration_config_update_auth_config_type_0 import (
            HttpIntegrationConfigUpdateAuthConfigType0,
        )
        from ..models.http_integration_config_update_default_headers_type_0 import (
            HttpIntegrationConfigUpdateDefaultHeadersType0,
        )

        name: None | str | Unset
        if isinstance(self.name, Unset):
            name = UNSET
        else:
            name = self.name

        base_url: None | str | Unset
        if isinstance(self.base_url, Unset):
            base_url = UNSET
        else:
            base_url = self.base_url

        default_headers: dict[str, Any] | None | Unset
        if isinstance(self.default_headers, Unset):
            default_headers = UNSET
        elif isinstance(self.default_headers, HttpIntegrationConfigUpdateDefaultHeadersType0):
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
        elif isinstance(self.auth_config, HttpIntegrationConfigUpdateAuthConfigType0):
            auth_config = self.auth_config.to_dict()
        else:
            auth_config = self.auth_config

        timeout_seconds: int | None | Unset
        if isinstance(self.timeout_seconds, Unset):
            timeout_seconds = UNSET
        else:
            timeout_seconds = self.timeout_seconds

        max_retries: int | None | Unset
        if isinstance(self.max_retries, Unset):
            max_retries = UNSET
        else:
            max_retries = self.max_retries

        is_active: bool | None | Unset
        if isinstance(self.is_active, Unset):
            is_active = UNSET
        else:
            is_active = self.is_active

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if name is not UNSET:
            field_dict["name"] = name
        if base_url is not UNSET:
            field_dict["base_url"] = base_url
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
        if is_active is not UNSET:
            field_dict["is_active"] = is_active

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.http_integration_config_update_auth_config_type_0 import (
            HttpIntegrationConfigUpdateAuthConfigType0,
        )
        from ..models.http_integration_config_update_default_headers_type_0 import (
            HttpIntegrationConfigUpdateDefaultHeadersType0,
        )

        d = dict(src_dict)

        def _parse_name(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        name = _parse_name(d.pop("name", UNSET))

        def _parse_base_url(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        base_url = _parse_base_url(d.pop("base_url", UNSET))

        def _parse_default_headers(data: object) -> HttpIntegrationConfigUpdateDefaultHeadersType0 | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                default_headers_type_0 = HttpIntegrationConfigUpdateDefaultHeadersType0.from_dict(data)

                return default_headers_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(HttpIntegrationConfigUpdateDefaultHeadersType0 | None | Unset, data)

        default_headers = _parse_default_headers(d.pop("default_headers", UNSET))

        def _parse_auth_type(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        auth_type = _parse_auth_type(d.pop("auth_type", UNSET))

        def _parse_auth_config(data: object) -> HttpIntegrationConfigUpdateAuthConfigType0 | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                auth_config_type_0 = HttpIntegrationConfigUpdateAuthConfigType0.from_dict(data)

                return auth_config_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(HttpIntegrationConfigUpdateAuthConfigType0 | None | Unset, data)

        auth_config = _parse_auth_config(d.pop("auth_config", UNSET))

        def _parse_timeout_seconds(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        timeout_seconds = _parse_timeout_seconds(d.pop("timeout_seconds", UNSET))

        def _parse_max_retries(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        max_retries = _parse_max_retries(d.pop("max_retries", UNSET))

        def _parse_is_active(data: object) -> bool | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(bool | None | Unset, data)

        is_active = _parse_is_active(d.pop("is_active", UNSET))

        http_integration_config_update = cls(
            name=name,
            base_url=base_url,
            default_headers=default_headers,
            auth_type=auth_type,
            auth_config=auth_config,
            timeout_seconds=timeout_seconds,
            max_retries=max_retries,
            is_active=is_active,
        )

        http_integration_config_update.additional_properties = d
        return http_integration_config_update

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
