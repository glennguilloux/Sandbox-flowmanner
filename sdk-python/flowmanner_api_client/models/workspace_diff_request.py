from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

T = TypeVar("T", bound="WorkspaceDiffRequest")


@_attrs_define
class WorkspaceDiffRequest:
    """
    Attributes:
        before_root (str):
        after_root (str):
        workspace (str):
    """

    before_root: str
    after_root: str
    workspace: str
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        before_root = self.before_root

        after_root = self.after_root

        workspace = self.workspace

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "before_root": before_root,
                "after_root": after_root,
                "workspace": workspace,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        before_root = d.pop("before_root")

        after_root = d.pop("after_root")

        workspace = d.pop("workspace")

        workspace_diff_request = cls(
            before_root=before_root,
            after_root=after_root,
            workspace=workspace,
        )

        workspace_diff_request.additional_properties = d
        return workspace_diff_request

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
