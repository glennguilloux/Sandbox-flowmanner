from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.browser_chat_action import BrowserChatAction


T = TypeVar("T", bound="BrowserChatResponse")


@_attrs_define
class BrowserChatResponse:
    """
    Attributes:
        response (str):
        actions (list[BrowserChatAction] | Unset):
        final_url (None | str | Unset):
        screenshot (None | str | Unset):
        success (bool | Unset):  Default: True.
    """

    response: str
    actions: list[BrowserChatAction] | Unset = UNSET
    final_url: None | str | Unset = UNSET
    screenshot: None | str | Unset = UNSET
    success: bool | Unset = True
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        response = self.response

        actions: list[dict[str, Any]] | Unset = UNSET
        if not isinstance(self.actions, Unset):
            actions = []
            for actions_item_data in self.actions:
                actions_item = actions_item_data.to_dict()
                actions.append(actions_item)

        final_url: None | str | Unset
        if isinstance(self.final_url, Unset):
            final_url = UNSET
        else:
            final_url = self.final_url

        screenshot: None | str | Unset
        if isinstance(self.screenshot, Unset):
            screenshot = UNSET
        else:
            screenshot = self.screenshot

        success = self.success

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "response": response,
            }
        )
        if actions is not UNSET:
            field_dict["actions"] = actions
        if final_url is not UNSET:
            field_dict["final_url"] = final_url
        if screenshot is not UNSET:
            field_dict["screenshot"] = screenshot
        if success is not UNSET:
            field_dict["success"] = success

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.browser_chat_action import BrowserChatAction

        d = dict(src_dict)
        response = d.pop("response")

        _actions = d.pop("actions", UNSET)
        actions: list[BrowserChatAction] | Unset = UNSET
        if _actions is not UNSET:
            actions = []
            for actions_item_data in _actions:
                actions_item = BrowserChatAction.from_dict(actions_item_data)

                actions.append(actions_item)

        def _parse_final_url(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        final_url = _parse_final_url(d.pop("final_url", UNSET))

        def _parse_screenshot(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        screenshot = _parse_screenshot(d.pop("screenshot", UNSET))

        success = d.pop("success", UNSET)

        browser_chat_response = cls(
            response=response,
            actions=actions,
            final_url=final_url,
            screenshot=screenshot,
            success=success,
        )

        browser_chat_response.additional_properties = d
        return browser_chat_response

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
