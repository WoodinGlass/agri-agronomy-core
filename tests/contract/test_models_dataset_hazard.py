"""Dataset and Hazard row model tests."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from agri_core.models.dataset import DatasetRow
from agri_core.models.hazard import HazardRow

pytestmark = pytest.mark.unit

_CHECKSUM = "sha256:" + "0" * 64


# --- DatasetRow ---


def _dataset(**kw):
    d = dict(
        dataset_id="D012345678",
        name="USDA PLANTS",
        version="2026.10",
        license="CC0-1.0",
        checksum=_CHECKSUM,
        url="https://plants.usda.gov",
        locator=None,
        access_date="2026-10-24",
    )
    d.update(kw)
    return d


def test_dataset_minimal_valid() -> None:
    row = DatasetRow(**_dataset())
    assert row.dataset_id == "D012345678"
    assert row.url == "https://plants.usda.gov"


def test_dataset_requires_url_or_locator() -> None:
    with pytest.raises(ValidationError, match="at least one of url or locator"):
        DatasetRow(**_dataset(url=None, locator=None))


def test_dataset_locator_only() -> None:
    row = DatasetRow(**_dataset(url=None, locator="page 42, table 2"))
    assert row.locator == "page 42, table 2"
    assert row.url is None


@pytest.mark.parametrize(
    "license_value",
    [
        "MIT",
        "CC-BY-4.0",
        "CC0-1.0",
        "Apache-2.0",
        "unclear",
        "LicenseRef-custom",
        "LicenseRef-my-org.1",
    ],
)
def test_dataset_license_valid(license_value: str) -> None:
    DatasetRow(**_dataset(license=license_value))


@pytest.mark.parametrize(
    "license_value",
    [
        "",
        " ",
        "not a license",
        "  bad spaces  ",
    ],
)
def test_dataset_license_invalid(license_value: str) -> None:
    with pytest.raises(ValidationError):
        DatasetRow(**_dataset(license=license_value))


def test_dataset_checksum_must_be_sha256() -> None:
    with pytest.raises(ValidationError):
        DatasetRow(**_dataset(checksum="md5:" + "0" * 32))


def test_dataset_checksum_uppercase_hex_rejected() -> None:
    with pytest.raises(ValidationError):
        DatasetRow(**_dataset(checksum="sha256:" + "A" * 64))


def test_dataset_url_scheme() -> None:
    with pytest.raises(ValidationError):
        DatasetRow(**_dataset(url="ftp://example.org"))
    with pytest.raises(ValidationError):
        DatasetRow(**_dataset(url="not-a-url"))


def test_dataset_access_date_iso() -> None:
    with pytest.raises(ValidationError):
        DatasetRow(**_dataset(access_date="24/10/2026"))


def test_dataset_frozen() -> None:
    row = DatasetRow(**_dataset())
    with pytest.raises((ValidationError, TypeError)):
        row.name = "other"  # type: ignore[misc]


def test_dataset_extra_forbidden() -> None:
    with pytest.raises(ValidationError):
        DatasetRow(**_dataset(extra="boom"))


# --- HazardRow ---


def _hazard(**kw):
    d = dict(
        taxon_id="T012345678",
        hazard_code="cites_appendix_i",
        severity="critical",
        reason="CITES Appendix I",
        as_of="2026-10-24",
        authority="CITES Secretariat",
        src=["S001"],
        dataset_id=None,
    )
    d.update(kw)
    return d


def test_hazard_minimal_valid() -> None:
    row = HazardRow(**_hazard())
    assert row.severity == "critical"
    assert row.src == ["S001"]


@pytest.mark.parametrize("severity", ["info", "warning", "critical"])
def test_hazard_severity_valid(severity: str) -> None:
    HazardRow(**_hazard(severity=severity))


def test_hazard_severity_invalid() -> None:
    with pytest.raises(ValidationError):
        HazardRow(**_hazard(severity="high"))


@pytest.mark.parametrize("code", ["cites_appendix_i", "perm_lhk_106", "x", "a1_b2"])
def test_hazard_code_valid(code: str) -> None:
    HazardRow(**_hazard(hazard_code=code))


@pytest.mark.parametrize("code", ["CITES", "1abc", "a-b", "with space", ""])
def test_hazard_code_invalid(code: str) -> None:
    with pytest.raises(ValidationError):
        HazardRow(**_hazard(hazard_code=code))


def test_hazard_as_of_iso() -> None:
    with pytest.raises(ValidationError):
        HazardRow(**_hazard(as_of="24/10/2026"))


def test_hazard_requires_src_or_dataset() -> None:
    with pytest.raises(ValidationError, match="at least one of src or dataset_id"):
        HazardRow(**_hazard(src=None, dataset_id=None))


def test_hazard_dataset_only() -> None:
    row = HazardRow(**_hazard(src=None, dataset_id="D012345678"))
    assert row.src is None
    assert row.dataset_id == "D012345678"


def test_hazard_reason_non_empty() -> None:
    with pytest.raises(ValidationError):
        HazardRow(**_hazard(reason=""))


def test_hazard_authority_non_empty() -> None:
    with pytest.raises(ValidationError):
        HazardRow(**_hazard(authority=""))


def test_hazard_frozen() -> None:
    row = HazardRow(**_hazard())
    with pytest.raises((ValidationError, TypeError)):
        row.severity = "info"  # type: ignore[misc]


def test_hazard_extra_forbidden() -> None:
    with pytest.raises(ValidationError):
        HazardRow(**_hazard(extra="boom"))
