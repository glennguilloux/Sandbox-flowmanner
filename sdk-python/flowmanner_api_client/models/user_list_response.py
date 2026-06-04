from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from typing import cast

if TYPE_CHECKING:
  from ..models.admin_user import AdminUser





T = TypeVar("T", bound="UserListResponse")



@_attrs_define
class UserListResponse:
    """ 
        Attributes:
            users (list[AdminUser]):
            total (int):
            page (int):
            page_size (int):
            pages (int):
     """

    users: list[AdminUser]
    total: int
    page: int
    page_size: int
    pages: int
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        from ..models.admin_user import AdminUser
        users = []
        for users_item_data in self.users:
            users_item = users_item_data.to_dict()
            users.append(users_item)



        total = self.total

        page = self.page

        page_size = self.page_size

        pages = self.pages


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "users": users,
            "total": total,
            "page": page,
            "page_size": page_size,
            "pages": pages,
        })

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.admin_user import AdminUser
        d = dict(src_dict)
        users = []
        _users = d.pop("users")
        for users_item_data in (_users):
            users_item = AdminUser.from_dict(users_item_data)



            users.append(users_item)


        total = d.pop("total")

        page = d.pop("page")

        page_size = d.pop("page_size")

        pages = d.pop("pages")

        user_list_response = cls(
            users=users,
            total=total,
            page=page,
            page_size=page_size,
            pages=pages,
        )


        user_list_response.additional_properties = d
        return user_list_response

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
