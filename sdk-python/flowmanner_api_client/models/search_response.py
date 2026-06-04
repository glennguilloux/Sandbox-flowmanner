from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..types import UNSET, Unset
from typing import cast

if TYPE_CHECKING:
  from ..models.search_response_query_analysis_type_0 import SearchResponseQueryAnalysisType0
  from ..models.search_response_results_item import SearchResponseResultsItem





T = TypeVar("T", bound="SearchResponse")



@_attrs_define
class SearchResponse:
    """ Search response model

        Attributes:
            query (str):
            results (list[SearchResponseResultsItem]):
            total_results (int):
            latency_ms (float):
            cached (bool):
            providers_used (list[str]):
            query_analysis (None | SearchResponseQueryAnalysisType0 | Unset):
     """

    query: str
    results: list[SearchResponseResultsItem]
    total_results: int
    latency_ms: float
    cached: bool
    providers_used: list[str]
    query_analysis: None | SearchResponseQueryAnalysisType0 | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        from ..models.search_response_query_analysis_type_0 import SearchResponseQueryAnalysisType0
        from ..models.search_response_results_item import SearchResponseResultsItem
        query = self.query

        results = []
        for results_item_data in self.results:
            results_item = results_item_data.to_dict()
            results.append(results_item)



        total_results = self.total_results

        latency_ms = self.latency_ms

        cached = self.cached

        providers_used = self.providers_used



        query_analysis: dict[str, Any] | None | Unset
        if isinstance(self.query_analysis, Unset):
            query_analysis = UNSET
        elif isinstance(self.query_analysis, SearchResponseQueryAnalysisType0):
            query_analysis = self.query_analysis.to_dict()
        else:
            query_analysis = self.query_analysis


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "query": query,
            "results": results,
            "total_results": total_results,
            "latency_ms": latency_ms,
            "cached": cached,
            "providers_used": providers_used,
        })
        if query_analysis is not UNSET:
            field_dict["query_analysis"] = query_analysis

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.search_response_query_analysis_type_0 import SearchResponseQueryAnalysisType0
        from ..models.search_response_results_item import SearchResponseResultsItem
        d = dict(src_dict)
        query = d.pop("query")

        results = []
        _results = d.pop("results")
        for results_item_data in (_results):
            results_item = SearchResponseResultsItem.from_dict(results_item_data)



            results.append(results_item)


        total_results = d.pop("total_results")

        latency_ms = d.pop("latency_ms")

        cached = d.pop("cached")

        providers_used = cast(list[str], d.pop("providers_used"))


        def _parse_query_analysis(data: object) -> None | SearchResponseQueryAnalysisType0 | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                query_analysis_type_0 = SearchResponseQueryAnalysisType0.from_dict(data)



                return query_analysis_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | SearchResponseQueryAnalysisType0 | Unset, data)

        query_analysis = _parse_query_analysis(d.pop("query_analysis", UNSET))


        search_response = cls(
            query=query,
            results=results,
            total_results=total_results,
            latency_ms=latency_ms,
            cached=cached,
            providers_used=providers_used,
            query_analysis=query_analysis,
        )


        search_response.additional_properties = d
        return search_response

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
