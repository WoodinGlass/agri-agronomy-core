"""Catalog lint rules."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from agri_core.catalog import (
    CatalogKind,
    CatalogOwner,
    CatalogRow,
    CatalogSafetyTier,
    CatalogStatus,
    CommercialUse,
    lint_catalog,
    load_catalog,
)
from agri_core.models.finding import Finding, FindingSeverity
from agri_core.pack.loader import _default_dictionary

pytestmark = pytest.mark.contract

CATALOG_CSV = Path(__file__).resolve().parents[2] / "docs" / "design" / "climate_catalog_v1.csv"


def _row(**kwargs: object) -> CatalogRow:
    base: dict[str, object] = {
        "param_id": "test_param",
        "group": "atmosphere",
        "kind": CatalogKind.COMPUTED,
        "unit": "kilopascal",
        "method_ref": "Tetens 1930",
        "owner_repo": CatalogOwner.CORE,
        "commercial_use": CommercialUse.YES,
        "safety_tier": CatalogSafetyTier.LOW,
        "status": CatalogStatus.PLANNED,
        "milestone": "M11",
        "test_id": "TBD",
        "checked_on": "2026-11-09",
        "reason": "",
    }
    base.update(kwargs)
    return CatalogRow(**base)


def _codes(findings: list[Finding]) -> set[str]:
    return {f.code for f in findings}


def _errors(findings: list[Finding]) -> list[Finding]:
    return [f for f in findings if f.severity == FindingSeverity.ERROR]


def test_clean_catalog_has_no_findings() -> None:
    rows = load_catalog(CATALOG_CSV)
    dictionary_keys = set(_default_dictionary().parameters.keys())
    findings = lint_catalog(
        rows,
        dictionary_keys=dictionary_keys,
        reference_date=date(2026, 11, 10),
    )
    assert findings == []


def test_commercial_use_required_for_non_excluded() -> None:
    findings = lint_catalog([_row(commercial_use=CommercialUse.NO)])
    assert "CATALOG_COMMERCIAL_USE" in _codes(findings)


def test_commercial_use_ok_for_excluded() -> None:
    row = _row(
        kind=CatalogKind.EXCLUDED,
        commercial_use=CommercialUse.NO,
        status=CatalogStatus.EXCLUDED,
        reason="test",
    )
    findings = lint_catalog([row])
    assert "CATALOG_COMMERCIAL_USE" not in _codes(findings)


def test_high_safety_must_be_excluded() -> None:
    findings = lint_catalog([_row(safety_tier=CatalogSafetyTier.HIGH)])
    assert "CATALOG_HIGH_SAFETY_NOT_EXCLUDED" in _codes(findings)


def test_high_safety_ok_when_excluded() -> None:
    row = _row(
        kind=CatalogKind.EXCLUDED,
        safety_tier=CatalogSafetyTier.HIGH,
        status=CatalogStatus.EXCLUDED,
        reason="test",
    )
    findings = lint_catalog([row])
    assert "CATALOG_HIGH_SAFETY_NOT_EXCLUDED" not in _codes(findings)


def test_implemented_computed_requires_method_and_test() -> None:
    row = _row(
        status=CatalogStatus.IMPLEMENTED,
        method_ref="TBD",
        test_id="TBD",
    )
    findings = lint_catalog([row])
    codes = _codes(findings)
    assert "CATALOG_COMPUTED_NO_METHOD" in codes
    assert "CATALOG_COMPUTED_NO_TEST" in codes


def test_implemented_computed_ok_with_method_and_test() -> None:
    row = _row(
        status=CatalogStatus.IMPLEMENTED,
        method_ref="Tetens 1930",
        test_id="test_vpd_golden",
    )
    findings = lint_catalog([row])
    assert _errors(findings) == []


def test_planned_computed_allows_tbd() -> None:
    row = _row(status=CatalogStatus.PLANNED, method_ref="", test_id="")
    findings = lint_catalog([row])
    assert _errors(findings) == []


def test_missing_reason_for_excluded() -> None:
    row = _row(kind=CatalogKind.EXCLUDED, status=CatalogStatus.EXCLUDED, reason="")
    findings = lint_catalog([row])
    assert "CATALOG_MISSING_REASON" in _codes(findings)


def test_missing_reason_for_backlog() -> None:
    row = _row(kind=CatalogKind.INPUT, status=CatalogStatus.BACKLOG, reason="")
    findings = lint_catalog([row])
    assert "CATALOG_MISSING_REASON" in _codes(findings)


def test_unparseable_unit() -> None:
    findings = lint_catalog([_row(unit="not-a-unit-xyz")])
    assert "CATALOG_UNIT_UNPARSEABLE" in _codes(findings)


def test_canonical_unit_accepted() -> None:
    findings = lint_catalog([_row(unit="degree_day")])
    assert "CATALOG_UNIT_UNPARSEABLE" not in _codes(findings)


def test_pint_parseable_unit_accepted() -> None:
    findings = lint_catalog([_row(unit="hour")])
    assert "CATALOG_UNIT_UNPARSEABLE" not in _codes(findings)


def test_pack_value_must_match_dictionary() -> None:
    row = _row(
        param_id="not_a_real_key",
        kind=CatalogKind.PACK_VALUE,
        unit="degree_Celsius",
        method_ref="",
    )
    dictionary_keys = set(_default_dictionary().parameters.keys())
    findings = lint_catalog([row], dictionary_keys=dictionary_keys)
    assert "CATALOG_PACK_VALUE_NOT_IN_DICTIONARY" in _codes(findings)


def test_pack_value_ok_when_in_dictionary() -> None:
    row = _row(
        param_id="gdd_base",
        kind=CatalogKind.PACK_VALUE,
        unit="degree_Celsius",
        method_ref="",
    )
    dictionary_keys = set(_default_dictionary().parameters.keys())
    findings = lint_catalog([row], dictionary_keys=dictionary_keys)
    assert "CATALOG_PACK_VALUE_NOT_IN_DICTIONARY" not in _codes(findings)


def test_stale_license_check_is_warning() -> None:
    row = _row(checked_on="2020-01-01")
    findings = lint_catalog([row], reference_date=date(2026, 11, 9))
    stale = [f for f in findings if f.code == "CATALOG_STALE_LICENSE_CHECK"]
    assert len(stale) == 1
    assert stale[0].severity == FindingSeverity.WARNING


def test_fresh_license_check_not_warned() -> None:
    row = _row(checked_on="2026-11-01")
    findings = lint_catalog([row], reference_date=date(2026, 11, 9))
    assert "CATALOG_STALE_LICENSE_CHECK" not in _codes(findings)
