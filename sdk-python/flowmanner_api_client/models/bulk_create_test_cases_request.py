from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from typing import cast

if TYPE_CHECKING:
  from ..models.create_test_case_request import CreateTestCaseRequest





T = TypeVar("T", bound="BulkCreateTestCasesRequest")



@_attrs_define
class BulkCreateTestCasesRequest:
    """ 
        Attributes:
            cases (list[CreateTestCaseRequest]):
     """

    cases: list[CreateTestCaseRequest]
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        from ..models.create_test_case_request import CreateTestCaseRequest
        cases = []
        for cases_item_data in self.cases:
            cases_item = cases_item_data.to_dict()
            cases.append(cases_item)




        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "cases": cases,
        })

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.create_test_case_request import CreateTestCaseRequest
        d = dict(src_dict)
        cases = []
        _cases = d.pop("cases")
        for cases_item_data in (_cases):
            cases_item = CreateTestCaseRequest.from_dict(cases_item_data)



            cases.append(cases_item)


        bulk_create_test_cases_request = cls(
            cases=cases,
        )


        bulk_create_test_cases_request.additional_properties = d
        return bulk_create_test_cases_request

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
