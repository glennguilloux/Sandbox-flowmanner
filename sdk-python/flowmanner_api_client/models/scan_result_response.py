from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.scan_result_response_findings_item import ScanResultResponseFindingsItem


T = TypeVar("T", bound="ScanResultResponse")


@_attrs_define
class ScanResultResponse:
    """
    Attributes:
        risk_score (int):
        passed (bool):
        findings_count (int):
        findings (list[ScanResultResponseFindingsItem]):
        declared_permissions (list[str]):
        detected_permissions (list[str]):
        undeclared_permissions (list[str]):
        files_scanned (int):
    """

    risk_score: int
    passed: bool
    findings_count: int
    findings: list[ScanResultResponseFindingsItem]
    declared_permissions: list[str]
    detected_permissions: list[str]
    undeclared_permissions: list[str]
    files_scanned: int
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        risk_score = self.risk_score

        passed = self.passed

        findings_count = self.findings_count

        findings = []
        for findings_item_data in self.findings:
            findings_item = findings_item_data.to_dict()
            findings.append(findings_item)

        declared_permissions = self.declared_permissions

        detected_permissions = self.detected_permissions

        undeclared_permissions = self.undeclared_permissions

        files_scanned = self.files_scanned

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "risk_score": risk_score,
                "passed": passed,
                "findings_count": findings_count,
                "findings": findings,
                "declared_permissions": declared_permissions,
                "detected_permissions": detected_permissions,
                "undeclared_permissions": undeclared_permissions,
                "files_scanned": files_scanned,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.scan_result_response_findings_item import ScanResultResponseFindingsItem

        d = dict(src_dict)
        risk_score = d.pop("risk_score")

        passed = d.pop("passed")

        findings_count = d.pop("findings_count")

        findings = []
        _findings = d.pop("findings")
        for findings_item_data in _findings:
            findings_item = ScanResultResponseFindingsItem.from_dict(findings_item_data)

            findings.append(findings_item)

        declared_permissions = cast(list[str], d.pop("declared_permissions"))

        detected_permissions = cast(list[str], d.pop("detected_permissions"))

        undeclared_permissions = cast(list[str], d.pop("undeclared_permissions"))

        files_scanned = d.pop("files_scanned")

        scan_result_response = cls(
            risk_score=risk_score,
            passed=passed,
            findings_count=findings_count,
            findings=findings,
            declared_permissions=declared_permissions,
            detected_permissions=detected_permissions,
            undeclared_permissions=undeclared_permissions,
            files_scanned=files_scanned,
        )

        scan_result_response.additional_properties = d
        return scan_result_response

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
