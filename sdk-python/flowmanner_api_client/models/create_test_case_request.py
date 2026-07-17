from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.create_test_case_request_rubric_type_0 import CreateTestCaseRequestRubricType0


T = TypeVar("T", bound="CreateTestCaseRequest")


@_attrs_define
class CreateTestCaseRequest:
    """
    Attributes:
        input_prompt (str):
        expected_behavior (str):
        task_type (str): code_generation, rag_accuracy, agent_reasoning, creative, general
        difficulty (str | Unset):  Default: 'medium'.
        tags (list[str] | Unset):
        rubric (CreateTestCaseRequestRubricType0 | None | Unset):
    """

    input_prompt: str
    expected_behavior: str
    task_type: str
    difficulty: str | Unset = "medium"
    tags: list[str] | Unset = UNSET
    rubric: CreateTestCaseRequestRubricType0 | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.create_test_case_request_rubric_type_0 import CreateTestCaseRequestRubricType0

        input_prompt = self.input_prompt

        expected_behavior = self.expected_behavior

        task_type = self.task_type

        difficulty = self.difficulty

        tags: list[str] | Unset = UNSET
        if not isinstance(self.tags, Unset):
            tags = self.tags

        rubric: dict[str, Any] | None | Unset
        if isinstance(self.rubric, Unset):
            rubric = UNSET
        elif isinstance(self.rubric, CreateTestCaseRequestRubricType0):
            rubric = self.rubric.to_dict()
        else:
            rubric = self.rubric

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "input_prompt": input_prompt,
                "expected_behavior": expected_behavior,
                "task_type": task_type,
            }
        )
        if difficulty is not UNSET:
            field_dict["difficulty"] = difficulty
        if tags is not UNSET:
            field_dict["tags"] = tags
        if rubric is not UNSET:
            field_dict["rubric"] = rubric

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.create_test_case_request_rubric_type_0 import CreateTestCaseRequestRubricType0

        d = dict(src_dict)
        input_prompt = d.pop("input_prompt")

        expected_behavior = d.pop("expected_behavior")

        task_type = d.pop("task_type")

        difficulty = d.pop("difficulty", UNSET)

        tags = cast(list[str], d.pop("tags", UNSET))

        def _parse_rubric(data: object) -> CreateTestCaseRequestRubricType0 | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                rubric_type_0 = CreateTestCaseRequestRubricType0.from_dict(data)

                return rubric_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(CreateTestCaseRequestRubricType0 | None | Unset, data)

        rubric = _parse_rubric(d.pop("rubric", UNSET))

        create_test_case_request = cls(
            input_prompt=input_prompt,
            expected_behavior=expected_behavior,
            task_type=task_type,
            difficulty=difficulty,
            tags=tags,
            rubric=rubric,
        )

        create_test_case_request.additional_properties = d
        return create_test_case_request

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
