from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define

from ..models.sensitivity import Sensitivity
from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.personal_memory_claim_update_object_type_0 import PersonalMemoryClaimUpdateObjectType0


T = TypeVar("T", bound="PersonalMemoryClaimUpdate")


@_attrs_define
class PersonalMemoryClaimUpdate:
    """Request body for ``PATCH /claims/{id}`` (PATCH semantics).

    All fields Optional. Fields NOT in this schema (user_id,
    workspace_id, id, claim_type, scope, source_type, created_at,
    updated_at) cannot be changed via PATCH — ``extra="forbid"``
    raises 422 if a client tries.

    Note: ``claim_type`` / ``scope`` / ``source_type`` are
    intentionally NOT editable via PATCH because changing a claim's
    taxonomy would invalidate provenance. Re-create the claim if you
    need to reclassify.

        Attributes:
            subject (None | str | Unset):
            predicate (None | str | Unset):
            object_ (None | PersonalMemoryClaimUpdateObjectType0 | Unset):
            confidence (float | None | Unset):
            importance (float | None | Unset):
            sensitivity (None | Sensitivity | Unset):
            expires_at (datetime.datetime | None | Unset):
    """

    subject: None | str | Unset = UNSET
    predicate: None | str | Unset = UNSET
    object_: None | PersonalMemoryClaimUpdateObjectType0 | Unset = UNSET
    confidence: float | None | Unset = UNSET
    importance: float | None | Unset = UNSET
    sensitivity: None | Sensitivity | Unset = UNSET
    expires_at: datetime.datetime | None | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        from ..models.personal_memory_claim_update_object_type_0 import PersonalMemoryClaimUpdateObjectType0

        subject: None | str | Unset
        if isinstance(self.subject, Unset):
            subject = UNSET
        else:
            subject = self.subject

        predicate: None | str | Unset
        if isinstance(self.predicate, Unset):
            predicate = UNSET
        else:
            predicate = self.predicate

        object_: dict[str, Any] | None | Unset
        if isinstance(self.object_, Unset):
            object_ = UNSET
        elif isinstance(self.object_, PersonalMemoryClaimUpdateObjectType0):
            object_ = self.object_.to_dict()
        else:
            object_ = self.object_

        confidence: float | None | Unset
        if isinstance(self.confidence, Unset):
            confidence = UNSET
        else:
            confidence = self.confidence

        importance: float | None | Unset
        if isinstance(self.importance, Unset):
            importance = UNSET
        else:
            importance = self.importance

        sensitivity: None | str | Unset
        if isinstance(self.sensitivity, Unset):
            sensitivity = UNSET
        elif isinstance(self.sensitivity, Sensitivity):
            sensitivity = self.sensitivity.value
        else:
            sensitivity = self.sensitivity

        expires_at: None | str | Unset
        if isinstance(self.expires_at, Unset):
            expires_at = UNSET
        elif isinstance(self.expires_at, datetime.datetime):
            expires_at = self.expires_at.isoformat()
        else:
            expires_at = self.expires_at

        field_dict: dict[str, Any] = {}

        field_dict.update({})
        if subject is not UNSET:
            field_dict["subject"] = subject
        if predicate is not UNSET:
            field_dict["predicate"] = predicate
        if object_ is not UNSET:
            field_dict["object"] = object_
        if confidence is not UNSET:
            field_dict["confidence"] = confidence
        if importance is not UNSET:
            field_dict["importance"] = importance
        if sensitivity is not UNSET:
            field_dict["sensitivity"] = sensitivity
        if expires_at is not UNSET:
            field_dict["expires_at"] = expires_at

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.personal_memory_claim_update_object_type_0 import PersonalMemoryClaimUpdateObjectType0

        d = dict(src_dict)

        def _parse_subject(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        subject = _parse_subject(d.pop("subject", UNSET))

        def _parse_predicate(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        predicate = _parse_predicate(d.pop("predicate", UNSET))

        def _parse_object_(data: object) -> None | PersonalMemoryClaimUpdateObjectType0 | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                object_type_0 = PersonalMemoryClaimUpdateObjectType0.from_dict(data)

                return object_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | PersonalMemoryClaimUpdateObjectType0 | Unset, data)

        object_ = _parse_object_(d.pop("object", UNSET))

        def _parse_confidence(data: object) -> float | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(float | None | Unset, data)

        confidence = _parse_confidence(d.pop("confidence", UNSET))

        def _parse_importance(data: object) -> float | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(float | None | Unset, data)

        importance = _parse_importance(d.pop("importance", UNSET))

        def _parse_sensitivity(data: object) -> None | Sensitivity | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                sensitivity_type_0 = Sensitivity(data)

                return sensitivity_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | Sensitivity | Unset, data)

        sensitivity = _parse_sensitivity(d.pop("sensitivity", UNSET))

        def _parse_expires_at(data: object) -> datetime.datetime | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                expires_at_type_0 = datetime.datetime.fromisoformat(data)

                return expires_at_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(datetime.datetime | None | Unset, data)

        expires_at = _parse_expires_at(d.pop("expires_at", UNSET))

        personal_memory_claim_update = cls(
            subject=subject,
            predicate=predicate,
            object_=object_,
            confidence=confidence,
            importance=importance,
            sensitivity=sensitivity,
            expires_at=expires_at,
        )

        return personal_memory_claim_update
