from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

T = TypeVar("T", bound="OIDCLogoutResponse")


@_attrs_define
class OIDCLogoutResponse:
    """
    Attributes:
        end_session_url (None | str):
    """

    end_session_url: None | str
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        end_session_url: None | str
        end_session_url = self.end_session_url

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "end_session_url": end_session_url,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)

        def _parse_end_session_url(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        end_session_url = _parse_end_session_url(d.pop("end_session_url"))

        oidc_logout_response = cls(
            end_session_url=end_session_url,
        )

        oidc_logout_response.additional_properties = d
        return oidc_logout_response

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
