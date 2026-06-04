from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from typing import cast

if TYPE_CHECKING:
  from ..models.feedback_compare_response_missions_item import FeedbackCompareResponseMissionsItem
  from ..models.feedback_compare_response_score_delta import FeedbackCompareResponseScoreDelta





T = TypeVar("T", bound="FeedbackCompareResponse")



@_attrs_define
class FeedbackCompareResponse:
    """ 
        Attributes:
            missions (list[FeedbackCompareResponseMissionsItem]):
            score_delta (FeedbackCompareResponseScoreDelta):
            improvements (list[str]):
            regressions (list[str]):
     """

    missions: list[FeedbackCompareResponseMissionsItem]
    score_delta: FeedbackCompareResponseScoreDelta
    improvements: list[str]
    regressions: list[str]
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        from ..models.feedback_compare_response_missions_item import FeedbackCompareResponseMissionsItem
        from ..models.feedback_compare_response_score_delta import FeedbackCompareResponseScoreDelta
        missions = []
        for missions_item_data in self.missions:
            missions_item = missions_item_data.to_dict()
            missions.append(missions_item)



        score_delta = self.score_delta.to_dict()

        improvements = self.improvements



        regressions = self.regressions




        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "missions": missions,
            "score_delta": score_delta,
            "improvements": improvements,
            "regressions": regressions,
        })

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.feedback_compare_response_missions_item import FeedbackCompareResponseMissionsItem
        from ..models.feedback_compare_response_score_delta import FeedbackCompareResponseScoreDelta
        d = dict(src_dict)
        missions = []
        _missions = d.pop("missions")
        for missions_item_data in (_missions):
            missions_item = FeedbackCompareResponseMissionsItem.from_dict(missions_item_data)



            missions.append(missions_item)


        score_delta = FeedbackCompareResponseScoreDelta.from_dict(d.pop("score_delta"))




        improvements = cast(list[str], d.pop("improvements"))


        regressions = cast(list[str], d.pop("regressions"))


        feedback_compare_response = cls(
            missions=missions,
            score_delta=score_delta,
            improvements=improvements,
            regressions=regressions,
        )


        feedback_compare_response.additional_properties = d
        return feedback_compare_response

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
