from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..types import UNSET, Unset
from typing import cast
from uuid import UUID

if TYPE_CHECKING:
  from ..models.restore_response_snapshot_type_0 import RestoreResponseSnapshotType0





T = TypeVar("T", bound="RestoreResponse")



@_attrs_define
class RestoreResponse:
    """ 
        Attributes:
            message (str):
            version_id (UUID):
            version_number (int):
            snapshot (None | RestoreResponseSnapshotType0 | Unset):
     """

    message: str
    version_id: UUID
    version_number: int
    snapshot: None | RestoreResponseSnapshotType0 | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        from ..models.restore_response_snapshot_type_0 import RestoreResponseSnapshotType0
        message = self.message

        version_id = str(self.version_id)

        version_number = self.version_number

        snapshot: dict[str, Any] | None | Unset
        if isinstance(self.snapshot, Unset):
            snapshot = UNSET
        elif isinstance(self.snapshot, RestoreResponseSnapshotType0):
            snapshot = self.snapshot.to_dict()
        else:
            snapshot = self.snapshot


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "message": message,
            "version_id": version_id,
            "version_number": version_number,
        })
        if snapshot is not UNSET:
            field_dict["snapshot"] = snapshot

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.restore_response_snapshot_type_0 import RestoreResponseSnapshotType0
        d = dict(src_dict)
        message = d.pop("message")

        version_id = UUID(d.pop("version_id"))




        version_number = d.pop("version_number")

        def _parse_snapshot(data: object) -> None | RestoreResponseSnapshotType0 | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                snapshot_type_0 = RestoreResponseSnapshotType0.from_dict(data)



                return snapshot_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | RestoreResponseSnapshotType0 | Unset, data)

        snapshot = _parse_snapshot(d.pop("snapshot", UNSET))


        restore_response = cls(
            message=message,
            version_id=version_id,
            version_number=version_number,
            snapshot=snapshot,
        )


        restore_response.additional_properties = d
        return restore_response

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
