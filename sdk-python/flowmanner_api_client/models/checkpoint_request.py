from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.checkpoint_message import CheckpointMessage


T = TypeVar("T", bound="CheckpointRequest")


@_attrs_define
class CheckpointRequest:
    """
    Attributes:
        messages (list[CheckpointMessage]):
        trigger_tokens (int | Unset):  Default: 100000.
        summary_budget (int | Unset):  Default: 8000.
        tail_message_count (int | Unset):  Default: 10.
        head_message_count (int | Unset):  Default: 0.
        previous_summary (None | str | Unset):
        previous_last_index (int | Unset):  Default: -1.
    """

    messages: list[CheckpointMessage]
    trigger_tokens: int | Unset = 100000
    summary_budget: int | Unset = 8000
    tail_message_count: int | Unset = 10
    head_message_count: int | Unset = 0
    previous_summary: None | str | Unset = UNSET
    previous_last_index: int | Unset = -1
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        messages = []
        for messages_item_data in self.messages:
            messages_item = messages_item_data.to_dict()
            messages.append(messages_item)

        trigger_tokens = self.trigger_tokens

        summary_budget = self.summary_budget

        tail_message_count = self.tail_message_count

        head_message_count = self.head_message_count

        previous_summary: None | str | Unset
        if isinstance(self.previous_summary, Unset):
            previous_summary = UNSET
        else:
            previous_summary = self.previous_summary

        previous_last_index = self.previous_last_index

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "messages": messages,
            }
        )
        if trigger_tokens is not UNSET:
            field_dict["trigger_tokens"] = trigger_tokens
        if summary_budget is not UNSET:
            field_dict["summary_budget"] = summary_budget
        if tail_message_count is not UNSET:
            field_dict["tail_message_count"] = tail_message_count
        if head_message_count is not UNSET:
            field_dict["head_message_count"] = head_message_count
        if previous_summary is not UNSET:
            field_dict["previous_summary"] = previous_summary
        if previous_last_index is not UNSET:
            field_dict["previous_last_index"] = previous_last_index

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.checkpoint_message import CheckpointMessage

        d = dict(src_dict)
        messages = []
        _messages = d.pop("messages")
        for messages_item_data in _messages:
            messages_item = CheckpointMessage.from_dict(messages_item_data)

            messages.append(messages_item)

        trigger_tokens = d.pop("trigger_tokens", UNSET)

        summary_budget = d.pop("summary_budget", UNSET)

        tail_message_count = d.pop("tail_message_count", UNSET)

        head_message_count = d.pop("head_message_count", UNSET)

        def _parse_previous_summary(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        previous_summary = _parse_previous_summary(d.pop("previous_summary", UNSET))

        previous_last_index = d.pop("previous_last_index", UNSET)

        checkpoint_request = cls(
            messages=messages,
            trigger_tokens=trigger_tokens,
            summary_budget=summary_budget,
            tail_message_count=tail_message_count,
            head_message_count=head_message_count,
            previous_summary=previous_summary,
            previous_last_index=previous_last_index,
        )

        checkpoint_request.additional_properties = d
        return checkpoint_request

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
