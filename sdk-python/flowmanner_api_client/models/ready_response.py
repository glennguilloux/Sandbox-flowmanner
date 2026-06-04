from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset







T = TypeVar("T", bound="ReadyResponse")



@_attrs_define
class ReadyResponse:
    """ 
        Attributes:
            status (str):
            database (str):
            redis (str):
            qdrant (str):
     """

    status: str
    database: str
    redis: str
    qdrant: str
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        status = self.status

        database = self.database

        redis = self.redis

        qdrant = self.qdrant


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "status": status,
            "database": database,
            "redis": redis,
            "qdrant": qdrant,
        })

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        status = d.pop("status")

        database = d.pop("database")

        redis = d.pop("redis")

        qdrant = d.pop("qdrant")

        ready_response = cls(
            status=status,
            database=database,
            redis=redis,
            qdrant=qdrant,
        )


        ready_response.additional_properties = d
        return ready_response

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
