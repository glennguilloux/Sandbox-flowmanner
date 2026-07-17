from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

T = TypeVar("T", bound="AuthLoopAlert")


@_attrs_define
class AuthLoopAlert:
    """
    Attributes:
        redirect_count (int):
        window_ms (int):
        threshold (int):
        pathname (str):
        session_error (str):
        has_user (bool):
    """

    redirect_count: int
    window_ms: int
    threshold: int
    pathname: str
    session_error: str
    has_user: bool
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        redirect_count = self.redirect_count

        window_ms = self.window_ms

        threshold = self.threshold

        pathname = self.pathname

        session_error = self.session_error

        has_user = self.has_user

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "redirectCount": redirect_count,
                "windowMs": window_ms,
                "threshold": threshold,
                "pathname": pathname,
                "sessionError": session_error,
                "hasUser": has_user,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        redirect_count = d.pop("redirectCount")

        window_ms = d.pop("windowMs")

        threshold = d.pop("threshold")

        pathname = d.pop("pathname")

        session_error = d.pop("sessionError")

        has_user = d.pop("hasUser")

        auth_loop_alert = cls(
            redirect_count=redirect_count,
            window_ms=window_ms,
            threshold=threshold,
            pathname=pathname,
            session_error=session_error,
            has_user=has_user,
        )

        auth_loop_alert.additional_properties = d
        return auth_loop_alert

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
