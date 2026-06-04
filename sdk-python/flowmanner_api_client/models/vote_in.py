from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..types import UNSET, Unset






T = TypeVar("T", bound="VoteIn")



@_attrs_define
class VoteIn:
    """ 
        Attributes:
            item_id (str):
            vote_type (str | Unset):  Default: 'up'.
     """

    item_id: str
    vote_type: str | Unset = 'up'
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        item_id = self.item_id

        vote_type = self.vote_type


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "item_id": item_id,
        })
        if vote_type is not UNSET:
            field_dict["vote_type"] = vote_type

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        item_id = d.pop("item_id")

        vote_type = d.pop("vote_type", UNSET)

        vote_in = cls(
            item_id=item_id,
            vote_type=vote_type,
        )


        vote_in.additional_properties = d
        return vote_in

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
