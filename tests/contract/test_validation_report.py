"""ValidationReport + validate_pack_report (M7-1)."""

from __future__ import annotations

import json
from importlib.resources import files as pkg_files
from pathlib import Path

import pytest
from pydantic import ValidationError

from agri_core.models.finding import (
    REPORT_VERSION,
    Finding,
    FindingLocation,
    FindingSeverity,
)
from agri_core.pack import validate_pack_report
from agri_core.pack.validate import ValidationReport

pytestmark = pytest.mark.contract


def _sample_files() -> dict[str, bytes]:
    from agri_core.pack import read_pack_bytes

    src = Path(str(pkg_files("agri_core") / "_samples" / "sample_pack"))
    return dict(read_pack_bytes(src))


def test_report_ok_true_when_no_findings() -> None:
    report = ValidationReport(findings=())
    assert report.ok is True
    assert report.errors == ()
    assert report.warnings == ()


def test_report_ok_false_with_error() -> None:
    finding = Finding(code="PACK_INVALID", severity=FindingSeverity.ERROR, message="x")
    report = ValidationReport(findings=(finding,))
    assert report.ok is False
    assert len(report.errors) == 1


def test_report_ok_true_with_warning_only() -> None:
    finding = Finding(code="SRC100", severity=FindingSeverity.WARNING, message="w")
    report = ValidationReport(findings=(finding,))
    assert report.ok is True
    assert report.warnings == (finding,)


def test_finding_frozen() -> None:
    finding = Finding(code="PACK_INVALID", severity=FindingSeverity.ERROR, message="x")
    with pytest.raises(ValidationError, match=r"[Ff]rozen"):
        finding.code = "OTHER"  # type: ignore[misc]


def test_finding_extra_forbid() -> None:
    with pytest.raises(ValidationError, match=r"[Ee]xtra"):
        Finding(  # type: ignore[call-arg]
            code="PACK_INVALID",
            severity=FindingSeverity.ERROR,
            message="x",
            unexpected="y",
        )


def test_finding_code_pattern() -> None:
    with pytest.raises(ValidationError, match=r"pattern"):
        Finding(code="bad", severity=FindingSeverity.ERROR, message="x")


def test_report_version_constant() -> None:
    assert REPORT_VERSION == 1
    report = ValidationReport(findings=())
    assert report.report_version == REPORT_VERSION


def test_report_json_roundtrip() -> None:
    finding = Finding(
        code="PACK_INVALID",
        severity=FindingSeverity.ERROR,
        message="x",
        location=FindingLocation(file="pack.toml", line=3),
    )
    report = ValidationReport(findings=(finding,))
    data = json.loads(report.model_dump_json())
    assert data["ok"] is False
    assert data["findings"][0]["code"] == "PACK_INVALID"
    assert data["findings"][0]["location"]["file"] == "pack.toml"


def test_validate_pack_report_empty_returns_error() -> None:
    report, ks = validate_pack_report({}, allow_synthetic=True)
    assert ks is None
    assert report.ok is False
    assert any(f.code == "PACK_INVALID" for f in report.errors)


def test_validate_pack_report_sample_ok() -> None:
    files = _sample_files()
    report, ks = validate_pack_report(files, allow_synthetic=True)
    assert ks is not None
    assert report.ok is True
    assert report.findings == ()


def test_validate_pack_report_deterministic_order() -> None:
    files = _sample_files()
    r1, _ = validate_pack_report(files, allow_synthetic=True)
    r2, _ = validate_pack_report(files, allow_synthetic=True)
    assert r1.findings == r2.findings


def test_validate_pack_preserves_m6_4_behavior() -> None:
    from agri_core.pack import validate_pack

    files = _sample_files()
    ks = validate_pack(files, allow_synthetic=True)
    assert ks is not None
    assert ks.verified is True
