from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from typing import cast

if TYPE_CHECKING:
  from ..models.delegation_response import DelegationResponse





T = TypeVar("T", bound="DelegationListResponse")



@_attrs_define
class DelegationListResponse:
    """ 
        Attributes:
            delegations (list[DelegationResponse]):
            total (int):
     """

    delegations: list[DelegationResponse]
    total: int
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        from ..models.delegation_response import DelegationResponse
        delegations = []
        for delegations_item_data in self.delegations:
            delegations_item = delegations_item_data.to_dict()
            delegations.append(delegations_item)



        total = self.total


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "delegations": delegations,
            "total": total,
        })

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.delegation_response import DelegationResponse
        d = dict(src_dict)
        delegations = []
        _delegations = d.pop("delegations")
        for delegations_item_data in (_delegations):
            delegations_item = DelegationResponse.from_dict(delegations_item_data)



            delegations.append(delegations_item)


        total = d.pop("total")

        delegation_list_response = cls(
            delegations=delegations,
            total=total,
        )


        delegation_list_response.additional_properties = d
        return delegation_list_response

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
