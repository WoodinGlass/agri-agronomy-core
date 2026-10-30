"""Lint behavior for sources.csv."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from agri_core.registry.sources import (
    CSV_HEADER,
    Finding,
    has_pd_basis,
    is_allowed_license,
    lint_csv_file,
    lint_csv_text,
)

pytestmark = pytest.mark.unit

TODAY = date(2026, 10, 18)
FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "sources"
HEADER_LINE = ",".join(CSV_HEADER) + "\n"


def _codes(findings: list[Finding]) -> list[str]:
    return [f.code for f in findings]


def test_empty_text() -> None:
    findings = lint_csv_text("", today=TODAY)
    assert _codes(findings) == ["SRC100"]


def test_header_only_ok() -> None:
    findings = lint_csv_text(HEADER_LINE, today=TODAY)
    assert findings == []


def test_header_mismatch() -> None:
    findings = lint_csv_text("a,b\n", today=TODAY)
    assert _codes(findings) == ["SRC101"]


def test_row_wrong_field_count() -> None:
    text = HEADER_LINE + "S001,https://x\n"
    findings = lint_csv_text(text, today=TODAY)
    assert "SRC102" in _codes(findings)


def test_row_invalid_url() -> None:
    text = HEADER_LINE + "S001,ftp://x,MIT,no,2026-01-15,doc\n"
    findings = lint_csv_text(text, today=TODAY)
    assert "SRC103" in _codes(findings)


def test_duplicate_id() -> None:
    text = (
        HEADER_LINE
        + "S001,https://x,MIT,no,2026-01-15,doc\n"
        + "S001,https://y,MIT,no,2026-01-15,doc\n"
    )
    findings = lint_csv_text(text, today=TODAY)
    assert "SRC104" in _codes(findings)


def test_nc_with_yes() -> None:
    text = HEADER_LINE + "S001,https://x,CC-BY-NC-4.0,yes,2026-01-15,doc\n"
    findings = lint_csv_text(text, today=TODAY)
    assert _codes(findings) == ["SRC001"]


def test_unclear_with_yes() -> None:
    text = HEADER_LINE + "S001,https://x,unclear,yes,2026-01-15,doc\n"
    findings = lint_csv_text(text, today=TODAY)
    assert _codes(findings) == ["SRC002"]


def test_nc_with_no_flagged() -> None:
    """ADR-005: commercial_use=no is an error even with an NC license."""
    text = HEADER_LINE + "S001,https://x,CC-BY-NC-4.0,no,2026-01-15,doc\n"
    findings = lint_csv_text(text, today=TODAY)
    assert "SRC005" in _codes(findings)


def test_unclear_with_unclear_flagged() -> None:
    """ADR-005: commercial_use=unclear is an error."""
    text = HEADER_LINE + "S001,https://x,unclear,unclear,2026-01-15,doc\n"
    findings = lint_csv_text(text, today=TODAY)
    assert "SRC005" in _codes(findings)


def test_future_date() -> None:
    # commercial_use=yes so SRC005 does not fire; isolates SRC004
    text = HEADER_LINE + "S001,https://x,MIT,yes,2099-01-01,doc\n"
    findings = lint_csv_text(text, today=TODAY)
    assert _codes(findings) == ["SRC004"]


def test_utf8_bom_is_stripped() -> None:
    text = "\ufeff" + HEADER_LINE
    findings = lint_csv_text(text, today=TODAY)
    assert findings == []


def test_crlf_is_handled() -> None:
    # commercial_use=yes so SRC005 does not fire; isolates CRLF handling
    text = (HEADER_LINE + "S001,https://x,MIT,yes,2026-01-15,doc\n").replace("\n", "\r\n")
    findings = lint_csv_text(text, today=TODAY)
    assert findings == []


def test_valid_fixture_clean() -> None:
    findings = lint_csv_file(FIXTURES / "valid.csv", today=TODAY)
    assert findings == []


def test_broken_fixture_collects_multiple() -> None:
    findings = lint_csv_file(FIXTURES / "broken.csv", today=TODAY)
    codes = set(_codes(findings))
    for expected in {"SRC001", "SRC002", "SRC103", "SRC104", "SRC004"}:
        assert expected in codes, f"missing {expected} in {sorted(codes)}"


def test_missing_file() -> None:
    findings = lint_csv_file(Path("/nonexistent/sources.csv"), today=TODAY)
    assert _codes(findings) == ["SRC000"]


def test_lint_file_findings_carry_real_path(tmp_path: Path) -> None:
    """SRC001/002/004 must report the actual file path, not a placeholder."""
    target = tmp_path / "sources.csv"
    target.write_text(
        HEADER_LINE
        + "S001,https://x,CC-BY-NC-4.0,yes,2099-01-01,doc\n"
        + "S002,https://x,unclear,yes,2026-01-15,doc\n",
        encoding="utf-8",
    )
    findings = lint_csv_file(target, today=TODAY)
    codes = {f.code for f in findings}
    assert {"SRC001", "SRC002", "SRC004"} <= codes, f"missing expected codes in {sorted(codes)}"
    for f in findings:
        assert f.location.file == str(target), (
            f"{f.code} reports file={f.location.file!r}, expected {str(target)!r}"
        )


def test_lint_text_honours_explicit_filename() -> None:
    """SRC001/002/004 honour the caller-supplied filename in lint_csv_text."""
    text = HEADER_LINE + "S001,https://x,CC-BY-NC-4.0,yes,2099-01-01,doc\n"
    findings = lint_csv_text(text, today=TODAY, filename="custom.csv")
    assert findings, "expected at least one finding"
    codes = {f.code for f in findings}
    assert {"SRC001", "SRC004"} <= codes
    for f in findings:
        assert f.location.file == "custom.csv"


@pytest.mark.parametrize(
    ("license_id", "expected"),
    [
        ("CC-BY-SA-4.0", True),
        ("CC-BY-SA-3.0", True),
        ("CC-BY-NC-SA-4.0", True),
        ("LicenseRef-ShareAlike-custom", True),
        ("CC-BY-4.0", False),
        ("CC0-1.0", False),
        ("NASDAQ", False),
        ("unclear", False),
    ],
)
def test_is_sa_license(license_id: str, expected: bool) -> None:
    from agri_core.registry.sources import is_sa_license

    assert is_sa_license(license_id) is expected


@pytest.mark.parametrize(
    ("license_id", "expected"),
    [
        ("CC-BY-ND-4.0", True),
        ("CC-BY-NC-ND-4.0", True),
        ("LicenseRef-NoDerivatives", True),
        ("CC-BY-4.0", False),
        ("CC0-1.0", False),
        ("INDIA", False),
        ("unclear", False),
    ],
)
def test_is_nd_license(license_id: str, expected: bool) -> None:
    from agri_core.registry.sources import is_nd_license

    assert is_nd_license(license_id) is expected


# ============================================================
# ADR-005: allowlist + PD basis (Cell C)
# ============================================================


@pytest.mark.parametrize(
    ("license_id", "expected"),
    [
        ("CC0-1.0", True),
        ("CC-BY-3.0", True),
        ("CC-BY-4.0", True),
        ("MIT", True),
        ("BSD-2-Clause", True),
        ("BSD-3-Clause", True),
        ("Apache-2.0", True),
        ("LicenseRef-PublicDomain", True),
        ("CC-BY-NC-4.0", False),
        ("CC-BY-SA-4.0", False),
        ("CC-BY-ND-4.0", False),
        ("ODbL-1.0", False),
        ("GPL-3.0", False),
        ("ISC", False),
        ("PSF-2.0", False),
        ("", False),
        ("unclear", False),
        ("NOASSERTION", False),
        ("MIT OR Apache-2.0", False),
        ("MIT AND Apache-2.0", False),
        ("GPL-2.0+", False),
        ("Apache-2.0 WITH LLVM-exception", False),
        ("LicenseRef-Foo", False),
        ("LicenseRef-Apa-Saja", False),
    ],
)
def test_is_allowed_license_sources(license_id: str, expected: bool) -> None:
    assert is_allowed_license(license_id, for_dataset=False) is expected


@pytest.mark.parametrize(
    ("license_id", "expected"),
    [
        ("CC0-1.0", True),
        ("CC-BY-4.0", True),
        ("MIT", True),
        ("LicenseRef-PublicDomain", False),
        ("ODbL-1.0", False),
        ("CC-BY-NC-4.0", False),
    ],
)
def test_is_allowed_license_datasets(license_id: str, expected: bool) -> None:
    assert is_allowed_license(license_id, for_dataset=True) is expected


@pytest.mark.parametrize(
    ("citation", "expected"),
    [
        ("basis: public domain under Indonesian copyright law", True),
        ("basis:", True),
        ("", False),
        (None, False),
        ("no prefix", False),
        ("Basis: uppercase", False),
    ],
)
def test_has_pd_basis(citation: str | None, expected: bool) -> None:
    assert has_pd_basis(citation) is expected


# ============================================================
# ADR-005: SRC005 — commercial_use must be yes (Cell B2)
# ============================================================


def test_no_with_valid_license_flagged() -> None:
    """commercial_use=no is an error even with a valid license."""
    text = HEADER_LINE + "S001,https://x,CC-BY-4.0,no,2026-01-15,doc\n"
    findings = lint_csv_text(text, today=TODAY)
    assert "SRC005" in _codes(findings)


def test_yes_with_valid_license_ok() -> None:
    """commercial_use=yes + valid license → no SRC005."""
    text = HEADER_LINE + "S001,https://x,CC-BY-4.0,yes,2026-01-15,doc\n"
    findings = lint_csv_text(text, today=TODAY)
    assert "SRC005" not in _codes(findings)


def test_src005_message_names_the_source() -> None:
    text = HEADER_LINE + "S042,https://x,CC-BY-4.0,no,2026-01-15,doc\n"
    findings = lint_csv_text(text, today=TODAY)
    src005 = [f for f in findings if f.code == "SRC005"]
    assert len(src005) == 1
    assert "S042" in src005[0].message
    assert "commercial_use=yes" in src005[0].message
