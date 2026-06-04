from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..types import UNSET, Unset
from typing import cast






T = TypeVar("T", bound="PayoutResponse")



@_attrs_define
class PayoutResponse:
    """ 
        Attributes:
            success (bool):
            amount (float):
            message (str):
            currency (str | Unset):  Default: 'USD'.
            payout_id (None | str | Unset):
     """

    success: bool
    amount: float
    message: str
    currency: str | Unset = 'USD'
    payout_id: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        success = self.success

        amount = self.amount

        message = self.message

        currency = self.currency

        payout_id: None | str | Unset
        if isinstance(self.payout_id, Unset):
            payout_id = UNSET
        else:
            payout_id = self.payout_id


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "success": success,
            "amount": amount,
            "message": message,
        })
        if currency is not UNSET:
            field_dict["currency"] = currency
        if payout_id is not UNSET:
            field_dict["payout_id"] = payout_id

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        success = d.pop("success")

        amount = d.pop("amount")

        message = d.pop("message")

        currency = d.pop("currency", UNSET)

        def _parse_payout_id(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        payout_id = _parse_payout_id(d.pop("payout_id", UNSET))


        payout_response = cls(
            success=success,
            amount=amount,
            message=message,
            currency=currency,
            payout_id=payout_id,
        )


        payout_response.additional_properties = d
        return payout_response

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
