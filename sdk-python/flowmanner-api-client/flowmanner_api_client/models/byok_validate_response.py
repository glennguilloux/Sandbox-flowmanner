from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.byok_validate_response_status import BYOKValidateResponseStatus
from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.model_info import ModelInfo


T = TypeVar("T", bound="BYOKValidateResponse")


@_attrs_define
class BYOKValidateResponse:
    """
    Attributes:
        status (BYOKValidateResponseStatus):
        models (list[ModelInfo]):
        error (None | str | Unset):
    """

    status: BYOKValidateResponseStatus
    models: list[ModelInfo]
    error: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        status = self.status.value

        models = []
        for models_item_data in self.models:
            models_item = models_item_data.to_dict()
            models.append(models_item)

        error: None | str | Unset
        if isinstance(self.error, Unset):
            error = UNSET
        else:
            error = self.error

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "status": status,
                "models": models,
            }
        )
        if error is not UNSET:
            field_dict["error"] = error

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.model_info import ModelInfo

        d = dict(src_dict)
        status = BYOKValidateResponseStatus(d.pop("status"))

        models = []
        _models = d.pop("models")
        for models_item_data in _models:
            models_item = ModelInfo.from_dict(models_item_data)

            models.append(models_item)

        def _parse_error(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        error = _parse_error(d.pop("error", UNSET))

        byok_validate_response = cls(
            status=status,
            models=models,
            error=error,
        )

        byok_validate_response.additional_properties = d
        return byok_validate_response

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
