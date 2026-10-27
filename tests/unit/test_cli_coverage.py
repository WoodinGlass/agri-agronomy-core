"""CLI agri-core coverage behavior."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from agri_core.cli import app

pytestmark = pytest.mark.unit


def _invoke(*args: str):
    return CliRunner().invoke(app, ["coverage", *args])


def test_coverage_sample_exit_0() -> None:
    result = _invoke("--pack", "sample")
    assert result.exit_code == 0, result.stdout + result.stderr
    assert "distribution:" in result.stdout


def test_coverage_sample_distribution() -> None:
    result = _invoke("--pack", "sample")
    assert result.exit_code == 0
    assert "T0: 1" in result.stdout
    assert "T1: 7" in result.stdout
    assert "T2: 0" in result.stdout
    assert "T3: 0" in result.stdout


def test_coverage_sample_synthetic_banner() -> None:
    result = _invoke("--pack", "sample")
    assert result.exit_code == 0
    assert "SYNTHETIC DATA" in result.stderr


def test_coverage_pack_not_found_exit_3(tmp_path: Path) -> None:
    result = _invoke("--pack", str(tmp_path / "nonexistent"))
    assert result.exit_code == 3
    assert "PACK_NOT_FOUND" in result.stderr


def test_coverage_invalid_pack_exit_3(tmp_path: Path) -> None:
    result = _invoke("--pack", str(tmp_path))
    assert result.exit_code == 3
    assert "PACK_INVALID" in result.stderr


def test_coverage_json_output() -> None:
    result = _invoke("--pack", "sample", "--json")
    assert result.exit_code == 0, result.stderr
    data = json.loads(result.stdout)
    assert data["pack"]["name"] == "sample"
    assert data["pack"]["version"] == "0.1.0"
    assert data["pack"]["synthetic"] is True
    assert len(data["taxa"]) == 8
    taxon_ids = {t["taxon_id"] for t in data["taxa"]}
    expected_ids = {f"T{i:09d}" for i in range(1, 9)}
    assert taxon_ids == expected_ids


def test_coverage_json_summary() -> None:
    result = _invoke("--pack", "sample", "--json")
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert data["summary"] == {"T0": 1, "T1": 7, "T2": 0, "T3": 0}


def test_coverage_tier_filter_exact() -> None:
    result = _invoke("--pack", "sample", "--json", "--tier", "T0")
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert len(data["taxa"]) == 1
    assert data["taxa"][0]["taxon_id"] == "T000000005"
    assert data["taxa"][0]["tier"] == "T0"
    # summary is always total, not filtered
    assert data["summary"] == {"T0": 1, "T1": 7, "T2": 0, "T3": 0}


def test_coverage_tier_filter_multiple() -> None:
    result = _invoke("--pack", "sample", "--json", "--tier", "T0", "--tier", "T1")
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert len(data["taxa"]) == 8


def test_coverage_tier_filter_invalid_exit_2() -> None:
    result = _invoke("--pack", "sample", "--tier", "BAD")
    assert result.exit_code == 2
    assert "invalid --tier" in result.stderr


def test_coverage_no_verbose_truncates() -> None:
    result = _invoke("--pack", "sample")
    assert result.exit_code == 0
    # Sample T000000001 has 17 system_gaps -> shows (+14 more)
    assert "(+14 more)" in result.stdout
    # And missing 5 -> (+2 more)
    assert "(+2 more)" in result.stdout


def test_coverage_verbose_shows_full_lists() -> None:
    result = _invoke("--pack", "sample", "--verbose")
    assert result.exit_code == 0
    # No truncation markers in verbose mode
    assert "(+" not in result.stdout
