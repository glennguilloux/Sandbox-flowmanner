from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.plugin_health_report_top_crashing_item import PluginHealthReportTopCrashingItem


T = TypeVar("T", bound="PluginHealthReport")


@_attrs_define
class PluginHealthReport:
    """
    Attributes:
        total_plugins (int):
        healthy (int):
        degraded (int):
        unhealthy (int):
        pending_review (int):
        avg_error_rate (float):
        top_crashing (list[PluginHealthReportTopCrashingItem]):
    """

    total_plugins: int
    healthy: int
    degraded: int
    unhealthy: int
    pending_review: int
    avg_error_rate: float
    top_crashing: list[PluginHealthReportTopCrashingItem]
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        total_plugins = self.total_plugins

        healthy = self.healthy

        degraded = self.degraded

        unhealthy = self.unhealthy

        pending_review = self.pending_review

        avg_error_rate = self.avg_error_rate

        top_crashing = []
        for top_crashing_item_data in self.top_crashing:
            top_crashing_item = top_crashing_item_data.to_dict()
            top_crashing.append(top_crashing_item)

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "total_plugins": total_plugins,
                "healthy": healthy,
                "degraded": degraded,
                "unhealthy": unhealthy,
                "pending_review": pending_review,
                "avg_error_rate": avg_error_rate,
                "top_crashing": top_crashing,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.plugin_health_report_top_crashing_item import PluginHealthReportTopCrashingItem

        d = dict(src_dict)
        total_plugins = d.pop("total_plugins")

        healthy = d.pop("healthy")

        degraded = d.pop("degraded")

        unhealthy = d.pop("unhealthy")

        pending_review = d.pop("pending_review")

        avg_error_rate = d.pop("avg_error_rate")

        top_crashing = []
        _top_crashing = d.pop("top_crashing")
        for top_crashing_item_data in _top_crashing:
            top_crashing_item = PluginHealthReportTopCrashingItem.from_dict(top_crashing_item_data)

            top_crashing.append(top_crashing_item)

        plugin_health_report = cls(
            total_plugins=total_plugins,
            healthy=healthy,
            degraded=degraded,
            unhealthy=unhealthy,
            pending_review=pending_review,
            avg_error_rate=avg_error_rate,
            top_crashing=top_crashing,
        )

        plugin_health_report.additional_properties = d
        return plugin_health_report

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
