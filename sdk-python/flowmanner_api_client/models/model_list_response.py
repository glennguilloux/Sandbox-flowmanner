from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from typing import cast

if TYPE_CHECKING:
  from ..models.frontend_model_info import FrontendModelInfo





T = TypeVar("T", bound="ModelListResponse")



@_attrs_define
class ModelListResponse:
    """ 
        Attributes:
            models (list[FrontendModelInfo]):
            total (int):
     """

    models: list[FrontendModelInfo]
    total: int
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        from ..models.frontend_model_info import FrontendModelInfo
        models = []
        for models_item_data in self.models:
            models_item = models_item_data.to_dict()
            models.append(models_item)



        total = self.total


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "models": models,
            "total": total,
        })

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.frontend_model_info import FrontendModelInfo
        d = dict(src_dict)
        models = []
        _models = d.pop("models")
        for models_item_data in (_models):
            models_item = FrontendModelInfo.from_dict(models_item_data)



            models.append(models_item)


        total = d.pop("total")

        model_list_response = cls(
            models=models,
            total=total,
        )


        model_list_response.additional_properties = d
        return model_list_response

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
