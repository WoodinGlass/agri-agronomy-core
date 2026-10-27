"""Duplicate fact + superseded_by rules (M7-3)."""

from __future__ import annotations

import csv
import io
from importlib.resources import files as pkg_files
from pathlib import Path

import pytest

from agri_core.pack import validate_pack_report

pytestmark = pytest.mark.contract


def _sample_files() -> dict[str, bytes]:
    """Read the sample pack, stripping content_hash so mutations load."""
    from agri_core.pack import read_pack_bytes

    src = Path(str(pkg_files("agri_core") / "_samples" / "sample_pack"))
    files = dict(read_pack_bytes(src))
    toml = files["pack.toml"].decode("utf-8")
    files["pack.toml"] = (
        "\n".join(ln for ln in toml.splitlines() if not ln.startswith("content_hash")).encode(
            "utf-8"
        )
        + b"\n"
    )
    return files


def _mutate_facts(facts_bytes: bytes, changes: dict[str, dict[str, str]]) -> bytes:
    """changes = {fact_id: {column: new_value}}."""
    text = facts_bytes.decode("utf-8")
    rows = list(csv.reader(io.StringIO(text)))
    header = rows[0]
    idx = {col: header.index(col) for col in header}
    for row in rows[1:]:
        fid = row[idx["fact_id"]]
        if fid in changes:
            for col, val in changes[fid].items():
                row[idx[col]] = val
    buf = io.StringIO()
    csv.writer(buf, lineterminator="\n").writerows(rows)
    return buf.getvalue().encode("utf-8")


def _add_fact(facts_bytes: bytes, new_row: dict[str, str]) -> bytes:
    """Append a fact row (missing columns become empty)."""
    text = facts_bytes.decode("utf-8")
    rows = list(csv.reader(io.StringIO(text)))
    header = rows[0]
    new_values = [new_row.get(col, "") for col in header]
    rows.append(new_values)
    buf = io.StringIO()
    csv.writer(buf, lineterminator="\n").writerows(rows)
    return buf.getvalue().encode("utf-8")


def test_sample_pack_no_findings() -> None:
    files = _sample_files()
    report, ks = validate_pack_report(files, allow_synthetic=True)
    assert ks is not None
    assert report.ok is True
    assert report.findings == ()


def test_self_supersede_flagged() -> None:
    files = _sample_files()
    files["facts/T000000001.csv"] = _mutate_facts(
        files["facts/T000000001.csv"],
        {"F00000000002": {"superseded_by": "F00000000002"}},
    )
    report, _ = validate_pack_report(files, allow_synthetic=True)
    codes = [f.code for f in report.errors]
    assert "PACK_SUPERSEDED_SELF" in codes
    # Only one finding for the self-loop, not a cycle finding too.
    assert "PACK_SUPERSEDED_CYCLE" not in codes
    self_err = next(f for f in report.errors if f.code == "PACK_SUPERSEDED_SELF")
    assert self_err.location.fact_id == "F00000000002"


def test_simple_cycle_flagged() -> None:
    files = _sample_files()
    files["facts/T000000001.csv"] = _mutate_facts(
        files["facts/T000000001.csv"],
        {
            "F00000000001": {"superseded_by": "F00000000002"},
            "F00000000002": {"superseded_by": "F00000000001"},
        },
    )
    report, _ = validate_pack_report(files, allow_synthetic=True)
    cycle_errors = [f for f in report.errors if f.code == "PACK_SUPERSEDED_CYCLE"]
    assert len(cycle_errors) == 1
    # Anchor is min fact_id in cycle
    assert cycle_errors[0].location.fact_id == "F00000000001"
    assert "F00000000001" in cycle_errors[0].message
    assert "F00000000002" in cycle_errors[0].message


def test_longer_cycle_flagged() -> None:
    files = _sample_files()
    files["facts/T000000001.csv"] = _mutate_facts(
        files["facts/T000000001.csv"],
        {
            "F00000000001": {"superseded_by": "F00000000002"},
            "F00000000002": {"superseded_by": "F00000000003"},
            "F00000000003": {"superseded_by": "F00000000001"},
        },
    )
    report, _ = validate_pack_report(files, allow_synthetic=True)
    cycle_errors = [f for f in report.errors if f.code == "PACK_SUPERSEDED_CYCLE"]
    assert len(cycle_errors) == 1
    assert cycle_errors[0].location.fact_id == "F00000000001"
    for fid in ("F00000000001", "F00000000002", "F00000000003"):
        assert fid in cycle_errors[0].message


def test_linear_chain_ok() -> None:
    files = _sample_files()
    files["facts/T000000001.csv"] = _mutate_facts(
        files["facts/T000000001.csv"],
        {
            "F00000000001": {"superseded_by": "F00000000002"},
            "F00000000002": {"superseded_by": "F00000000003"},
        },
    )
    report, ks = validate_pack_report(files, allow_synthetic=True)
    assert ks is not None
    cycle_codes = [f.code for f in report.findings if f.code == "PACK_SUPERSEDED_CYCLE"]
    assert cycle_codes == []
    assert "PACK_SUPERSEDED_SELF" not in [f.code for f in report.findings]


def test_duplicate_key_conflicting_value_flagged() -> None:
    files = _sample_files()
    # F00000000002 = (T1, gdd_base, no phase, scope={}, value=8.0, src=S001).
    # Add F99999999999 with same key, different value (9.0).
    files["facts/T000000001.csv"] = _add_fact(
        files["facts/T000000001.csv"],
        {
            "fact_id": "F99999999999",
            "taxon_id": "T000000001",
            "parameter": "gdd_base",
            "phase": "",
            "value": '{"shape":"scalar","unit":"degree_Celsius","value":9.0}',
            "scope": "{}",
            "provenance_kind": "curated",
            "src": "S002",
            "dataset_id": "",
            "locator": "x",
            "evidence": "A",
            "status": "approved",
            "reviewed_by": "test-reviewer",
            "reviewed_at": "2026-01-01",
            "superseded_by": "",
        },
    )
    report, _ = validate_pack_report(files, allow_synthetic=True)
    dup_errors = [f for f in report.errors if f.code == "PACK_FACT_KEY_DUPLICATE"]
    assert len(dup_errors) == 1
    msg = dup_errors[0].message
    assert "F00000000002" in msg
    assert "F99999999999" in msg


def test_duplicate_key_same_value_corroboration_ok() -> None:
    files = _sample_files()
    # Same key + same value as F00000000002 (8.0), different src (S002).
    files["facts/T000000001.csv"] = _add_fact(
        files["facts/T000000001.csv"],
        {
            "fact_id": "F99999999999",
            "taxon_id": "T000000001",
            "parameter": "gdd_base",
            "phase": "",
            "value": '{"shape":"scalar","unit":"degree_Celsius","value":8.0}',
            "scope": "{}",
            "provenance_kind": "curated",
            "src": "S002",
            "dataset_id": "",
            "locator": "x",
            "evidence": "A",
            "status": "approved",
            "reviewed_by": "test-reviewer",
            "reviewed_at": "2026-01-01",
            "superseded_by": "",
        },
    )
    report, _ = validate_pack_report(files, allow_synthetic=True)
    codes = [f.code for f in report.findings]
    assert "PACK_FACT_KEY_DUPLICATE" not in codes


def test_superseded_excluded_from_duplicate_check() -> None:
    files = _sample_files()
    # Mark F2 as superseded by F3 (FK satisfied). Then add F99 with same
    # key as F2 but different value. Since F2 is excluded (superseded),
    # F99 is the only live fact with this key -> no conflict.
    files["facts/T000000001.csv"] = _mutate_facts(
        files["facts/T000000001.csv"],
        {"F00000000002": {"superseded_by": "F00000000003"}},
    )
    files["facts/T000000001.csv"] = _add_fact(
        files["facts/T000000001.csv"],
        {
            "fact_id": "F99999999999",
            "taxon_id": "T000000001",
            "parameter": "gdd_base",
            "phase": "",
            "value": '{"shape":"scalar","unit":"degree_Celsius","value":9.0}',
            "scope": "{}",
            "provenance_kind": "curated",
            "src": "S002",
            "dataset_id": "",
            "locator": "x",
            "evidence": "A",
            "status": "approved",
            "reviewed_by": "test-reviewer",
            "reviewed_at": "2026-01-01",
            "superseded_by": "",
        },
    )
    report, _ = validate_pack_report(files, allow_synthetic=True)
    codes = [f.code for f in report.findings]
    assert "PACK_FACT_KEY_DUPLICATE" not in codes
