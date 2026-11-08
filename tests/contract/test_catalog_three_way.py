"""Three-way consistency: CSV, generated doc, shipped excluded list."""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

from agri_core.catalog import EXCLUDED_PARAM_IDS, load_catalog

pytestmark = pytest.mark.contract

ROOT = Path(__file__).resolve().parents[2]
CSV_PATH = ROOT / "docs" / "design" / "climate_catalog_v1.csv"
DOC_PATH = ROOT / "docs" / "CLIMATE_CATALOG.md"


def _csv_rows() -> list[dict[str, str]]:
    with CSV_PATH.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def _csv_excluded_ids() -> set[str]:
    return {r["param_id"] for r in _csv_rows() if r["status"] == "excluded"}


def test_shipped_excluded_set_matches_csv() -> None:
    assert _csv_excluded_ids() == set(EXCLUDED_PARAM_IDS)


def test_every_shipped_id_is_excluded_in_csv() -> None:
    csv_excluded = _csv_excluded_ids()
    for pid in EXCLUDED_PARAM_IDS:
        assert pid in csv_excluded, f"shipped id {pid!r} not in CSV excluded"


def test_every_shipped_id_is_excluded_only() -> None:
    csv_rows = _csv_rows()
    for pid in EXCLUDED_PARAM_IDS:
        matching = [r for r in csv_rows if r["param_id"] == pid]
        assert len(matching) == 1, f"{pid!r} appears {len(matching)} times"
        assert matching[0]["status"] == "excluded"


def test_generated_doc_lists_every_param_id() -> None:
    doc_text = DOC_PATH.read_text(encoding="utf-8")
    for r in _csv_rows():
        assert r["param_id"] in doc_text, f"{r['param_id']!r} missing from doc"


def test_loader_row_count_matches_csv() -> None:
    rows = load_catalog(CSV_PATH)
    assert len(rows) == len(_csv_rows())
