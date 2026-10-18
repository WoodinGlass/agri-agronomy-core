"""SourceRow model validation."""

from __future__ import annotations

from datetime import date
from typing import Any

import pytest
from pydantic import ValidationError

from agri_core.registry.sources import SourceRow, is_nc_license

pytestmark = pytest.mark.unit


def _row(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "id": "S001",
        "url": "https://example.org/doc",
        "license": "MIT",
        "commercial_use": "yes",
        "access_date": "2026-01-15",
        "citation": "Example doc",
    }
    base.update(overrides)
    return base


def test_valid_row() -> None:
    row = SourceRow(**_row())
    assert row.id == "S001"
    assert row.commercial_use == "yes"
    assert row.access_date == date(2026, 1, 15)


def test_id_pattern() -> None:
    assert SourceRow(**_row(id="S001")).id == "S001"
    assert SourceRow(**_row(id="S12345")).id == "S12345"
    with pytest.raises(ValidationError):
        SourceRow(**_row(id="S1"))
    with pytest.raises(ValidationError):
        SourceRow(**_row(id="X001"))


def test_url_scheme() -> None:
    with pytest.raises(ValidationError):
        SourceRow(**_row(url="ftp://example.org/x"))
    with pytest.raises(ValidationError):
        SourceRow(**_row(url="not-a-url"))


def test_url_needs_host() -> None:
    with pytest.raises(ValidationError):
        SourceRow(**_row(url="https://"))


def test_license_unclear_ok() -> None:
    row = SourceRow(**_row(license="unclear", commercial_use="unclear"))
    assert row.license == "unclear"


def test_license_licenseref_ok() -> None:
    SourceRow(**_row(license="LicenseRef-custom-1", commercial_use="no"))


@pytest.mark.parametrize(
    "license_id",
    ["MIT", "Apache-2.0", "CC-BY-4.0", "CC-BY-NC-SA-4.0"],
)
def test_license_spdx_like_ok(license_id: str) -> None:
    SourceRow(**_row(license=license_id, commercial_use="no"))


@pytest.mark.parametrize(
    "license_id",
    ["MIT OR Apache-2.0", "", "random text", "  "],
)
def test_license_bad(license_id: str) -> None:
    with pytest.raises(ValidationError):
        SourceRow(**_row(license=license_id, commercial_use="unclear"))


def test_commercial_use_normalized() -> None:
    assert SourceRow(**_row(commercial_use="YES")).commercial_use == "yes"
    assert SourceRow(**_row(commercial_use="  no  ")).commercial_use == "no"


def test_commercial_use_invalid() -> None:
    with pytest.raises(ValidationError):
        SourceRow(**_row(commercial_use="maybe"))


def test_access_date_iso() -> None:
    assert SourceRow(**_row(access_date="2026-01-15")).access_date == date(2026, 1, 15)
    with pytest.raises(ValidationError):
        SourceRow(**_row(access_date="not-a-date"))
    with pytest.raises(ValidationError):
        SourceRow(**_row(access_date="15/01/2026"))


def test_citation_non_empty() -> None:
    with pytest.raises(ValidationError):
        SourceRow(**_row(citation=""))
    with pytest.raises(ValidationError):
        SourceRow(**_row(citation="   "))


def test_extra_forbidden() -> None:
    with pytest.raises(ValidationError):
        SourceRow(**_row(extra="boom"))


@pytest.mark.parametrize(
    ("license_id", "expected"),
    [
        ("CC-BY-NC-4.0", True),
        ("CC-BY-NC-SA-4.0", True),
        ("cc-by-nc", True),
        ("noncommercial", True),
        ("MIT", False),
        ("unclear", False),
        ("NCBI", False),
        ("CC-BY-4.0", False),
        ("BY-NC-ND-3.0", True),
    ],
)
def test_nc_token_detection(license_id: str, expected: bool) -> None:
    assert is_nc_license(license_id) is expected
