"""PACK_SAFETY_DOUBLE_REVIEW_MISSING rule (M7-5)."""

from __future__ import annotations

from importlib.resources import files as pkg_files
from pathlib import Path

import pytest

from agri_core.pack import validate_pack_report

pytestmark = pytest.mark.contract


def _csv_quote(s: str) -> str:
    return '"' + s.replace('"', '""') + '"'


def _sample_files() -> dict[str, bytes]:
    from agri_core.pack import read_pack_bytes

    src = Path(str(pkg_files("agri_core") / "_samples" / "sample_pack"))
    files = dict(read_pack_bytes(src))
    toml = files["pack.toml"].decode("utf-8")
    files["pack.toml"] = (
        "\n".join(ln for ln in toml.splitlines() if not ln.startswith("content_hash"))
    ).encode("utf-8") + b"\n"
    return files


def _add_safety_fact(files, fact_id, *, status, reviewed_by):
    value_json = '{"shape":"unknown","reason":"n/a"}'
    scope_json = '{"system":"field"}'
    row = (
        f"{fact_id},T000000001,n_max_per_application,,"
        f"{_csv_quote(value_json)},{_csv_quote(scope_json)},"
        f"curated,S001,,x,A,{status},{reviewed_by},2026-01-01,\n"
    )
    files["facts/T000000001.csv"] = files["facts/T000000001.csv"] + row.encode("utf-8")
    return files


def test_rule_fires_on_approved_single_reviewer() -> None:
    files = _sample_files()
    files = _add_safety_fact(files, "F99999999999", status="approved", reviewed_by="rev1")
    report, _ = validate_pack_report(files, allow_synthetic=True)
    codes = [f.code for f in report.findings]
    assert "PACK_SAFETY_DOUBLE_REVIEW_MISSING" in codes


def test_rule_passes_approved_two_reviewers() -> None:
    files = _sample_files()
    files = _add_safety_fact(files, "F99999999999", status="approved", reviewed_by="rev1|rev2")
    report, _ = validate_pack_report(files, allow_synthetic=True)
    codes = [f.code for f in report.findings]
    assert "PACK_SAFETY_DOUBLE_REVIEW_MISSING" not in codes


def test_rule_does_not_fire_on_reviewed() -> None:
    files = _sample_files()
    files = _add_safety_fact(files, "F99999999999", status="reviewed", reviewed_by="rev1")
    report, _ = validate_pack_report(files, allow_synthetic=True)
    codes = [f.code for f in report.findings]
    assert "PACK_SAFETY_DOUBLE_REVIEW_MISSING" not in codes


def test_rule_does_not_fire_on_non_safety_critical() -> None:
    files = _sample_files()
    report, _ = validate_pack_report(files, allow_synthetic=True)
    codes = [f.code for f in report.findings]
    assert "PACK_SAFETY_DOUBLE_REVIEW_MISSING" not in codes
