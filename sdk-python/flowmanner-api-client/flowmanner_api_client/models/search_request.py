from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="SearchRequest")


@_attrs_define
class SearchRequest:
    """Search request model

    Attributes:
        query (str):
        max_results (int | Unset):  Default: 10.
        providers (list[str] | None | Unset):
        use_query_understanding (bool | Unset):  Default: True.
        use_reranking (bool | Unset):  Default: True.
        use_cache (bool | Unset):  Default: True.
    """

    query: str
    max_results: int | Unset = 10
    providers: list[str] | None | Unset = UNSET
    use_query_understanding: bool | Unset = True
    use_reranking: bool | Unset = True
    use_cache: bool | Unset = True
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        query = self.query

        max_results = self.max_results

        providers: list[str] | None | Unset
        if isinstance(self.providers, Unset):
            providers = UNSET
        elif isinstance(self.providers, list):
            providers = self.providers

        else:
            providers = self.providers

        use_query_understanding = self.use_query_understanding

        use_reranking = self.use_reranking

        use_cache = self.use_cache

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "query": query,
            }
        )
        if max_results is not UNSET:
            field_dict["max_results"] = max_results
        if providers is not UNSET:
            field_dict["providers"] = providers
        if use_query_understanding is not UNSET:
            field_dict["use_query_understanding"] = use_query_understanding
        if use_reranking is not UNSET:
            field_dict["use_reranking"] = use_reranking
        if use_cache is not UNSET:
            field_dict["use_cache"] = use_cache

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        query = d.pop("query")

        max_results = d.pop("max_results", UNSET)

        def _parse_providers(data: object) -> list[str] | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, list):
                    raise TypeError()
                providers_type_0 = cast(list[str], data)

                return providers_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(list[str] | None | Unset, data)

        providers = _parse_providers(d.pop("providers", UNSET))

        use_query_understanding = d.pop("use_query_understanding", UNSET)

        use_reranking = d.pop("use_reranking", UNSET)

        use_cache = d.pop("use_cache", UNSET)

        search_request = cls(
            query=query,
            max_results=max_results,
            providers=providers,
            use_query_understanding=use_query_understanding,
            use_reranking=use_reranking,
            use_cache=use_cache,
        )

        search_request.additional_properties = d
        return search_request

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
