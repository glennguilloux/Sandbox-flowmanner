from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.update_test_case_request_rubric_type_0 import (
        UpdateTestCaseRequestRubricType0,
    )


T = TypeVar("T", bound="UpdateTestCaseRequest")


@_attrs_define
class UpdateTestCaseRequest:
    """
    Attributes:
        input_prompt (None | str | Unset):
        expected_behavior (None | str | Unset):
        task_type (None | str | Unset):
        difficulty (None | str | Unset):
        tags (list[str] | None | Unset):
        rubric (None | Unset | UpdateTestCaseRequestRubricType0):
    """

    input_prompt: None | str | Unset = UNSET
    expected_behavior: None | str | Unset = UNSET
    task_type: None | str | Unset = UNSET
    difficulty: None | str | Unset = UNSET
    tags: list[str] | None | Unset = UNSET
    rubric: None | Unset | UpdateTestCaseRequestRubricType0 = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.update_test_case_request_rubric_type_0 import (
            UpdateTestCaseRequestRubricType0,
        )

        input_prompt: None | str | Unset
        if isinstance(self.input_prompt, Unset):
            input_prompt = UNSET
        else:
            input_prompt = self.input_prompt

        expected_behavior: None | str | Unset
        if isinstance(self.expected_behavior, Unset):
            expected_behavior = UNSET
        else:
            expected_behavior = self.expected_behavior

        task_type: None | str | Unset
        if isinstance(self.task_type, Unset):
            task_type = UNSET
        else:
            task_type = self.task_type

        difficulty: None | str | Unset
        if isinstance(self.difficulty, Unset):
            difficulty = UNSET
        else:
            difficulty = self.difficulty

        tags: list[str] | None | Unset
        if isinstance(self.tags, Unset):
            tags = UNSET
        elif isinstance(self.tags, list):
            tags = self.tags

        else:
            tags = self.tags

        rubric: dict[str, Any] | None | Unset
        if isinstance(self.rubric, Unset):
            rubric = UNSET
        elif isinstance(self.rubric, UpdateTestCaseRequestRubricType0):
            rubric = self.rubric.to_dict()
        else:
            rubric = self.rubric

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if input_prompt is not UNSET:
            field_dict["input_prompt"] = input_prompt
        if expected_behavior is not UNSET:
            field_dict["expected_behavior"] = expected_behavior
        if task_type is not UNSET:
            field_dict["task_type"] = task_type
        if difficulty is not UNSET:
            field_dict["difficulty"] = difficulty
        if tags is not UNSET:
            field_dict["tags"] = tags
        if rubric is not UNSET:
            field_dict["rubric"] = rubric

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.update_test_case_request_rubric_type_0 import (
            UpdateTestCaseRequestRubricType0,
        )

        d = dict(src_dict)

        def _parse_input_prompt(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        input_prompt = _parse_input_prompt(d.pop("input_prompt", UNSET))

        def _parse_expected_behavior(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        expected_behavior = _parse_expected_behavior(d.pop("expected_behavior", UNSET))

        def _parse_task_type(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        task_type = _parse_task_type(d.pop("task_type", UNSET))

        def _parse_difficulty(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        difficulty = _parse_difficulty(d.pop("difficulty", UNSET))

        def _parse_tags(data: object) -> list[str] | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, list):
                    raise TypeError()
                tags_type_0 = cast(list[str], data)

                return tags_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(list[str] | None | Unset, data)

        tags = _parse_tags(d.pop("tags", UNSET))

        def _parse_rubric(
            data: object,
        ) -> None | Unset | UpdateTestCaseRequestRubricType0:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                rubric_type_0 = UpdateTestCaseRequestRubricType0.from_dict(data)

                return rubric_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | Unset | UpdateTestCaseRequestRubricType0, data)

        rubric = _parse_rubric(d.pop("rubric", UNSET))

        update_test_case_request = cls(
            input_prompt=input_prompt,
            expected_behavior=expected_behavior,
            task_type=task_type,
            difficulty=difficulty,
            tags=tags,
            rubric=rubric,
        )

        update_test_case_request.additional_properties = d
        return update_test_case_request

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
