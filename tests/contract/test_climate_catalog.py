"""Climate parameter catalog: model and loader contracts."""

from __future__ import annotations

from pathlib import Path

import pytest

from agri_core.catalog import (
    CatalogKind,
    CatalogLoadError,
    CatalogOwner,
    CatalogRow,
    CatalogSafetyTier,
    CatalogStatus,
    CommercialUse,
    load_catalog,
)

pytestmark = pytest.mark.contract

CATALOG_CSV = Path(__file__).resolve().parents[2] / "docs" / "design" / "climate_catalog_v1.csv"

_HEADER = (
    "param_id,group,kind,unit,method_ref,owner_repo,commercial_use,"
    "safety_tier,status,milestone,test_id,checked_on,reason"
)

_FIELDS = [
    "param_id",
    "group",
    "kind",
    "unit",
    "method_ref",
    "owner_repo",
    "commercial_use",
    "safety_tier",
    "status",
    "milestone",
    "test_id",
    "checked_on",
    "reason",
]


def _write_csv(tmp_path: Path, rows: list[str]) -> Path:
    p = tmp_path / "catalog.csv"
    p.write_text("\n".join([_HEADER, *rows]) + "\n", encoding="utf-8")
    return p


def _row(**kwargs: str) -> str:
    base = {
        "param_id": "test_param",
        "group": "atmosphere",
        "kind": "computed",
        "unit": "kilopascal",
        "method_ref": "Tetens 1930",
        "owner_repo": "core",
        "commercial_use": "yes",
        "safety_tier": "low",
        "status": "planned",
        "milestone": "M11",
        "test_id": "TBD",
        "checked_on": "2026-11-09",
        "reason": "",
    }
    base.update(kwargs)
    return ",".join(base[h] for h in _FIELDS)


def _valid_row(**overrides: object) -> CatalogRow:
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
    base.update(overrides)
    return CatalogRow(**base)


def test_load_shipped_catalog() -> None:
    rows = load_catalog(CATALOG_CSV)
    assert len(rows) == 45
    assert len({r.param_id for r in rows}) == 45
    kinds = {r.kind for r in rows}
    assert kinds == {
        CatalogKind.COMPUTED,
        CatalogKind.INPUT,
        CatalogKind.PACK_VALUE,
        CatalogKind.EXCLUDED,
    }


def test_catalog_row_enum_values() -> None:
    row = _valid_row()
    assert row.kind.value == "computed"
    assert row.status.value == "planned"
    assert row.safety_tier.value == "low"
    assert row.commercial_use.value == "yes"
    assert row.owner_repo.value == "core"


def test_load_missing_header_raises(tmp_path: Path) -> None:
    p = tmp_path / "catalog.csv"
    p.write_text("param_id,group\nfoo,bar\n", encoding="utf-8")
    with pytest.raises(CatalogLoadError, match="missing columns"):
        load_catalog(p)


def test_load_duplicate_param_id_raises(tmp_path: Path) -> None:
    p = _write_csv(tmp_path, [_row(), _row()])
    with pytest.raises(CatalogLoadError, match="duplicate param_id"):
        load_catalog(p)


def test_load_empty_catalog_raises(tmp_path: Path) -> None:
    p = _write_csv(tmp_path, [])
    with pytest.raises(CatalogLoadError, match="empty"):
        load_catalog(p)


def test_load_bad_row_raises(tmp_path: Path) -> None:
    p = _write_csv(tmp_path, [_row(kind="not-a-kind")])
    with pytest.raises(CatalogLoadError, match="row 2"):
        load_catalog(p)


def test_catalog_row_rejects_bad_checked_on() -> None:
    with pytest.raises(ValueError, match="checked_on"):
        _valid_row(checked_on="not-a-date")


def test_catalog_row_rejects_uppercase_param_id() -> None:
    with pytest.raises(ValueError, match="param_id"):
        _valid_row(param_id="BadParam")
