from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..types import UNSET, Unset
from dateutil.parser import isoparse
from typing import cast
from uuid import UUID
import datetime

if TYPE_CHECKING:
  from ..models.version_response_snapshot_type_0 import VersionResponseSnapshotType0





T = TypeVar("T", bound="VersionResponse")



@_attrs_define
class VersionResponse:
    """ 
        Attributes:
            id (UUID):
            mission_id (UUID):
            version_number (int):
            snapshot (None | VersionResponseSnapshotType0):
            change_summary (None | str):
            created_at (datetime.datetime | None | Unset):
            updated_at (datetime.datetime | None | Unset):
     """

    id: UUID
    mission_id: UUID
    version_number: int
    snapshot: None | VersionResponseSnapshotType0
    change_summary: None | str
    created_at: datetime.datetime | None | Unset = UNSET
    updated_at: datetime.datetime | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        from ..models.version_response_snapshot_type_0 import VersionResponseSnapshotType0
        id = str(self.id)

        mission_id = str(self.mission_id)

        version_number = self.version_number

        snapshot: dict[str, Any] | None
        if isinstance(self.snapshot, VersionResponseSnapshotType0):
            snapshot = self.snapshot.to_dict()
        else:
            snapshot = self.snapshot

        change_summary: None | str
        change_summary = self.change_summary

        created_at: None | str | Unset
        if isinstance(self.created_at, Unset):
            created_at = UNSET
        elif isinstance(self.created_at, datetime.datetime):
            created_at = self.created_at.isoformat()
        else:
            created_at = self.created_at

        updated_at: None | str | Unset
        if isinstance(self.updated_at, Unset):
            updated_at = UNSET
        elif isinstance(self.updated_at, datetime.datetime):
            updated_at = self.updated_at.isoformat()
        else:
            updated_at = self.updated_at


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "id": id,
            "mission_id": mission_id,
            "version_number": version_number,
            "snapshot": snapshot,
            "change_summary": change_summary,
        })
        if created_at is not UNSET:
            field_dict["created_at"] = created_at
        if updated_at is not UNSET:
            field_dict["updated_at"] = updated_at

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.version_response_snapshot_type_0 import VersionResponseSnapshotType0
        d = dict(src_dict)
        id = UUID(d.pop("id"))




        mission_id = UUID(d.pop("mission_id"))




        version_number = d.pop("version_number")

        def _parse_snapshot(data: object) -> None | VersionResponseSnapshotType0:
            if data is None:
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                snapshot_type_0 = VersionResponseSnapshotType0.from_dict(data)



                return snapshot_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | VersionResponseSnapshotType0, data)

        snapshot = _parse_snapshot(d.pop("snapshot"))


        def _parse_change_summary(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        change_summary = _parse_change_summary(d.pop("change_summary"))


        def _parse_created_at(data: object) -> datetime.datetime | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                created_at_type_0 = isoparse(data)



                return created_at_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(datetime.datetime | None | Unset, data)

        created_at = _parse_created_at(d.pop("created_at", UNSET))


        def _parse_updated_at(data: object) -> datetime.datetime | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                updated_at_type_0 = isoparse(data)



                return updated_at_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(datetime.datetime | None | Unset, data)

        updated_at = _parse_updated_at(d.pop("updated_at", UNSET))


        version_response = cls(
            id=id,
            mission_id=mission_id,
            version_number=version_number,
            snapshot=snapshot,
            change_summary=change_summary,
            created_at=created_at,
            updated_at=updated_at,
        )


        version_response.additional_properties = d
        return version_response

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
