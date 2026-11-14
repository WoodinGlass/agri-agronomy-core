"""Contract tests for the review sheet export (M16).

Locks the column set, the manifest shape, the CSV format (UTF-8, LF,
QUOTE_ALL, no timestamp), determinism, filter behavior, and the golden
oracle used by the Rust migration.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
from pathlib import Path
from typing import Any

import pytest

from agri_core.export.review_sheet import (
    ALL_COLUMNS,
    FILLIN_COLUMNS,
    READONLY_COLUMNS,
    SHEET_SCHEMA_VERSION,
    ReviewSheetFilters,
    generate_review_sheet,
)
from agri_core.pack import load_knowledge_set
from agri_core.pack.loader import _default_dictionary

pytestmark = pytest.mark.contract

REPO_ROOT = Path(__file__).resolve().parents[2]
SAMPLE = REPO_ROOT / "src" / "agri_core" / "_samples" / "sample_pack"
GOLDEN_DIR = REPO_ROOT / "tests" / "golden" / "exports"
GOLDEN_CSV = GOLDEN_DIR / "review_sheet.csv"
GOLDEN_MANIFEST = GOLDEN_DIR / "review_sheet.manifest.json"


@pytest.fixture(scope="module")
def ks() -> Any:
    return load_knowledge_set(SAMPLE, allow_synthetic=True)


@pytest.fixture(scope="module")
def dictionary() -> Any:
    return _default_dictionary()


@pytest.fixture(scope="module")
def default_output(ks: Any, dictionary: Any) -> tuple[str, dict[str, Any]]:
    return generate_review_sheet(ks, dictionary, ReviewSheetFilters())


# ---- columns ------------------------------------------------------------


def test_columns_match_spec() -> None:
    assert len(ALL_COLUMNS) == 22
    assert len(READONLY_COLUMNS) == 17
    assert len(FILLIN_COLUMNS) == 5
    assert READONLY_COLUMNS + FILLIN_COLUMNS == ALL_COLUMNS


def test_expected_columns_present() -> None:
    required_readonly = {
        "fact_id", "taxon_id", "scientific_name", "parameter", "phase",
        "value_pretty", "value_json", "unit", "scope", "evidence",
        "status", "safety_class", "taxon_tier", "source_citation",
        "source_url", "source_license", "current_reviewed_by",
    }
    assert set(READONLY_COLUMNS) == required_readonly
    assert set(FILLIN_COLUMNS) == {
        "reviewer_id", "decision", "corrected_value_json",
        "comment", "reviewed_on",
    }


def test_header_matches_all_columns(default_output: tuple[str, dict[str, Any]]) -> None:
    csv_text, _ = default_output
    header_line = csv_text.splitlines()[0]
    header = [c.strip('"') for c in header_line.split('","')]
    assert header == list(ALL_COLUMNS)


# ---- default filters ----------------------------------------------------


def test_default_row_count(default_output: tuple[str, dict[str, Any]]) -> None:
    _, manifest = default_output
    assert manifest["row_count"] == 6, (
        "sample pack has 62 facts, 56 approved, 6 non-approved; "
        "default max_status='reviewed' yields 6"
    )


def test_approved_row_count(ks: Any, dictionary: Any) -> None:
    _, manifest = generate_review_sheet(
        ks, dictionary, ReviewSheetFilters(max_status="approved")
    )
    assert manifest["row_count"] == 62


def test_draft_row_count(ks: Any, dictionary: Any) -> None:
    _, manifest = generate_review_sheet(
        ks, dictionary, ReviewSheetFilters(max_status="draft")
    )
    assert manifest["row_count"] == 0


def test_safety_critical_row_count(ks: Any, dictionary: Any) -> None:
    _, manifest = generate_review_sheet(
        ks, dictionary, ReviewSheetFilters(safety_critical_only=True)
    )
    assert manifest["row_count"] == 6


# ---- determinism --------------------------------------------------------


def test_determinism(ks: Any, dictionary: Any) -> None:
    csv_a, manifest_a = generate_review_sheet(
        ks, dictionary, ReviewSheetFilters()
    )
    csv_b, manifest_b = generate_review_sheet(
        ks, dictionary, ReviewSheetFilters()
    )
    assert csv_a == csv_b
    assert manifest_a == manifest_b


def test_row_order(ks: Any, dictionary: Any) -> None:
    csv_text, _ = generate_review_sheet(ks, dictionary, ReviewSheetFilters())
    rows = list(csv.DictReader(io.StringIO(csv_text)))
    keys = [(r["taxon_id"], r["fact_id"]) for r in rows]
    assert keys == sorted(keys)


# ---- format -------------------------------------------------------------


def test_utf8_lf_only(default_output: tuple[str, dict[str, Any]]) -> None:
    csv_text, _ = default_output
    assert "\r" not in csv_text
    csv_text.encode("utf-8")


def test_quote_all(default_output: tuple[str, dict[str, Any]]) -> None:
    csv_text, _ = default_output
    for i, line in enumerate(csv_text.splitlines(), 1):
        assert line.startswith('"'), (
            f"line {i} does not start with a quote: {line[:60]!r}"
        )
        assert line.endswith('"'), (
            f"line {i} does not end with a quote: {line[-60:]!r}"
        )


def test_no_timestamp_columns() -> None:
    for col in ALL_COLUMNS:
        assert col not in {"timestamp", "generated_at", "exported_at"}, (
            f"unexpected timestamp column: {col}"
        )


def test_csv_parse_round_trip(default_output: tuple[str, dict[str, Any]]) -> None:
    csv_text, _ = default_output
    reader = csv.DictReader(io.StringIO(csv_text))
    rows = list(reader)
    assert len(rows) > 0
    for row in rows:
        assert set(row.keys()) == set(ALL_COLUMNS)


def test_value_json_always_object(default_output: tuple[str, dict[str, Any]]) -> None:
    csv_text, _ = default_output
    rows = list(csv.DictReader(io.StringIO(csv_text)))
    for row in rows:
        assert row["value_json"].startswith("{"), (
            f"value_json must start with '{{': {row['value_json'][:60]!r}"
        )


# ---- manifest -----------------------------------------------------------


def test_manifest_csv_sha_matches(default_output: tuple[str, dict[str, Any]]) -> None:
    csv_text, manifest = default_output
    actual = hashlib.sha256(csv_text.encode("utf-8")).hexdigest()
    assert manifest["csv_sha256"] == actual


def test_manifest_row_count_matches(default_output: tuple[str, dict[str, Any]]) -> None:
    csv_text, manifest = default_output
    row_count = sum(1 for _ in csv.DictReader(io.StringIO(csv_text)))
    assert manifest["row_count"] == row_count


def test_manifest_pack_fields(ks: Any, default_output: tuple[str, dict[str, Any]]) -> None:
    _, manifest = default_output
    assert manifest["pack_name"] == ks.manifest.name
    assert manifest["pack_version"] == ks.manifest.version
    assert manifest["pack_hash"] == ks.pack_hash
    assert manifest["synthetic"] is True


def test_manifest_sheet_schema_version(default_output: tuple[str, dict[str, Any]]) -> None:
    _, manifest = default_output
    assert manifest["sheet_schema_version"] == SHEET_SCHEMA_VERSION


def test_manifest_filters_echoed(ks: Any, dictionary: Any) -> None:
    filters = ReviewSheetFilters(
        max_status="reviewed",
        tiers=("T1",),
        taxon_ids=("T000000001",),
        safety_critical_only=False,
    )
    _, manifest = generate_review_sheet(ks, dictionary, filters)
    f = manifest["filters"]
    assert f["max_status"] == "reviewed"
    assert f["tiers"] == ["T1"]
    assert f["taxon_ids"] == ["T000000001"]
    assert f["safety_critical_only"] is False


# ---- golden (byte-identical oracle) -------------------------------------


def test_golden_csv_matches(default_output: tuple[str, dict[str, Any]]) -> None:
    assert GOLDEN_CSV.is_file(), (
        f"missing golden: {GOLDEN_CSV}. Regenerate with "
        "`python -c \"from pathlib import Path; "
        "from agri_core.pack import load_knowledge_set; "
        "from agri_core.pack.loader import _default_dictionary; "
        "from agri_core.export.review_sheet import write_review_sheet; "
        "ks = load_knowledge_set(Path('src/agri_core/_samples/sample_pack'), allow_synthetic=True); "
        "write_review_sheet(ks, _default_dictionary(), Path('tests/golden/exports'))\"`."
    )
    csv_text, _ = default_output
    golden = GOLDEN_CSV.read_text(encoding="utf-8")
    assert csv_text == golden


def test_golden_manifest_matches(default_output: tuple[str, dict[str, Any]]) -> None:
    assert GOLDEN_MANIFEST.is_file(), f"missing golden: {GOLDEN_MANIFEST}"
    _, manifest = default_output
    golden = json.loads(GOLDEN_MANIFEST.read_text(encoding="utf-8"))
    assert manifest == golden
