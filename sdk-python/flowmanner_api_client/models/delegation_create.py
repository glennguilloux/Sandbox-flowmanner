from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..types import UNSET, Unset
from dateutil.parser import isoparse
from typing import cast
import datetime






T = TypeVar("T", bound="DelegationCreate")



@_attrs_define
class DelegationCreate:
    """ 
        Attributes:
            delegatee_id (int):
            role_id (str):
            tenant_id (None | str | Unset):
            reason (None | str | Unset):
            starts_at (datetime.datetime | None | Unset):
            ends_at (datetime.datetime | None | Unset):
     """

    delegatee_id: int
    role_id: str
    tenant_id: None | str | Unset = UNSET
    reason: None | str | Unset = UNSET
    starts_at: datetime.datetime | None | Unset = UNSET
    ends_at: datetime.datetime | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        delegatee_id = self.delegatee_id

        role_id = self.role_id

        tenant_id: None | str | Unset
        if isinstance(self.tenant_id, Unset):
            tenant_id = UNSET
        else:
            tenant_id = self.tenant_id

        reason: None | str | Unset
        if isinstance(self.reason, Unset):
            reason = UNSET
        else:
            reason = self.reason

        starts_at: None | str | Unset
        if isinstance(self.starts_at, Unset):
            starts_at = UNSET
        elif isinstance(self.starts_at, datetime.datetime):
            starts_at = self.starts_at.isoformat()
        else:
            starts_at = self.starts_at

        ends_at: None | str | Unset
        if isinstance(self.ends_at, Unset):
            ends_at = UNSET
        elif isinstance(self.ends_at, datetime.datetime):
            ends_at = self.ends_at.isoformat()
        else:
            ends_at = self.ends_at


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "delegatee_id": delegatee_id,
            "role_id": role_id,
        })
        if tenant_id is not UNSET:
            field_dict["tenant_id"] = tenant_id
        if reason is not UNSET:
            field_dict["reason"] = reason
        if starts_at is not UNSET:
            field_dict["starts_at"] = starts_at
        if ends_at is not UNSET:
            field_dict["ends_at"] = ends_at

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        delegatee_id = d.pop("delegatee_id")

        role_id = d.pop("role_id")

        def _parse_tenant_id(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        tenant_id = _parse_tenant_id(d.pop("tenant_id", UNSET))


        def _parse_reason(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        reason = _parse_reason(d.pop("reason", UNSET))


        def _parse_starts_at(data: object) -> datetime.datetime | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                starts_at_type_0 = isoparse(data)



                return starts_at_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(datetime.datetime | None | Unset, data)

        starts_at = _parse_starts_at(d.pop("starts_at", UNSET))


        def _parse_ends_at(data: object) -> datetime.datetime | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                ends_at_type_0 = isoparse(data)



                return ends_at_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(datetime.datetime | None | Unset, data)

        ends_at = _parse_ends_at(d.pop("ends_at", UNSET))


        delegation_create = cls(
            delegatee_id=delegatee_id,
            role_id=role_id,
            tenant_id=tenant_id,
            reason=reason,
            starts_at=starts_at,
            ends_at=ends_at,
        )


        delegation_create.additional_properties = d
        return delegation_create

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
