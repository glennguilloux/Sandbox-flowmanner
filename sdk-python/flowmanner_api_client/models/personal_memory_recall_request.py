from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define

from ..models.scope_2 import Scope2
from ..types import UNSET, Unset

T = TypeVar("T", bound="PersonalMemoryRecallRequest")


@_attrs_define
class PersonalMemoryRecallRequest:
    """Request body for ``POST /claims/recall``.

    ``query`` is matched against (subject, predicate) via a simple
    case-insensitive substring search in T19. T20+ will replace this
    with semantic search via embeddings.

        Attributes:
            query (str):
            scopes (list[Scope2] | None | Unset):
            top_k (int | Unset):  Default: 10.
            min_confidence (float | Unset):  Default: 0.0.
    """

    query: str
    scopes: list[Scope2] | None | Unset = UNSET
    top_k: int | Unset = 10
    min_confidence: float | Unset = 0.0

    def to_dict(self) -> dict[str, Any]:
        query = self.query

        scopes: list[str] | None | Unset
        if isinstance(self.scopes, Unset):
            scopes = UNSET
        elif isinstance(self.scopes, list):
            scopes = []
            for scopes_type_0_item_data in self.scopes:
                scopes_type_0_item = scopes_type_0_item_data.value
                scopes.append(scopes_type_0_item)

        else:
            scopes = self.scopes

        top_k = self.top_k

        min_confidence = self.min_confidence

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "query": query,
            }
        )
        if scopes is not UNSET:
            field_dict["scopes"] = scopes
        if top_k is not UNSET:
            field_dict["top_k"] = top_k
        if min_confidence is not UNSET:
            field_dict["min_confidence"] = min_confidence

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        query = d.pop("query")

        def _parse_scopes(data: object) -> list[Scope2] | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, list):
                    raise TypeError()
                scopes_type_0 = []
                _scopes_type_0 = data
                for scopes_type_0_item_data in _scopes_type_0:
                    scopes_type_0_item = Scope2(scopes_type_0_item_data)

                    scopes_type_0.append(scopes_type_0_item)

                return scopes_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(list[Scope2] | None | Unset, data)

        scopes = _parse_scopes(d.pop("scopes", UNSET))

        top_k = d.pop("top_k", UNSET)

        min_confidence = d.pop("min_confidence", UNSET)

        personal_memory_recall_request = cls(
            query=query,
            scopes=scopes,
            top_k=top_k,
            min_confidence=min_confidence,
        )

        return personal_memory_recall_request
