from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Literal, TypeVar, cast

from attrs import define as _attrs_define

T = TypeVar("T", bound="WebhookTrigger")


@_attrs_define
class WebhookTrigger:
    """Webhook-driven trigger (incoming HTTP POST).

    Attributes:
        type_ (Literal['webhook']):
        secret (str):
        path (str):
    """

    type_: Literal["webhook"]
    secret: str
    path: str

    def to_dict(self) -> dict[str, Any]:
        type_ = self.type_

        secret = self.secret

        path = self.path

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "type": type_,
                "secret": secret,
                "path": path,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        type_ = cast(Literal["webhook"], d.pop("type"))
        if type_ != "webhook":
            raise ValueError(f"type must match const 'webhook', got '{type_}'")

        secret = d.pop("secret")

        path = d.pop("path")

        webhook_trigger = cls(
            type_=type_,
            secret=secret,
            path=path,
        )

        return webhook_trigger
