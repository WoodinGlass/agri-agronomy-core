"""CLI suitability subcommand (M15)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from agri_core.cli import app

pytestmark = pytest.mark.unit


def _invoke(*args: str):
    return CliRunner().invoke(app, ["suitability", *args])


_TROPICAL = (
    "--soil-ph",
    "6.5",
    "--soil-ec",
    "1.5",
    "--air-temp-day",
    "30.0",
    "--air-temp-night",
    "25.0",
    "--air-rh",
    "70.0",
    "--vpd",
    "1.0",
    "--dli",
    "25.0",
)


def test_suitability_suitable_individual_flags() -> None:
    result = _invoke(
        "--pack",
        "sample",
        "--taxon",
        "T000000009",
        "--phase",
        "flowering",
        *_TROPICAL,
    )
    assert result.exit_code == 0, result.stdout + result.stderr
    assert "ok_category: suitable" in result.stdout


def test_suitability_unsuitable() -> None:
    flags = (
        "--soil-ph",
        "6.5",
        "--soil-ec",
        "1.5",
        "--air-temp-day",
        "5.0",  # < abs_min 20 for tropical T000000009
        "--air-temp-night",
        "25.0",
        "--air-rh",
        "70.0",
        "--vpd",
        "1.0",
        "--dli",
        "25.0",
    )
    result = _invoke(
        "--pack",
        "sample",
        "--taxon",
        "T000000009",
        "--phase",
        "flowering",
        *flags,
    )
    assert result.exit_code == 0, result.stdout + result.stderr
    assert "ok_category: unsuitable" in result.stdout


def test_suitability_batch_multiple_taxa() -> None:
    result = _invoke(
        "--pack",
        "sample",
        "--taxon",
        "T000000009",
        "--taxon",
        "T000000001",
        "--phase",
        "flowering",
        *_TROPICAL,
    )
    # T000000009 -> suitable (ok_category); T000000001 -> unknown (missing 6 params)
    # Mixed -> exit 1
    assert result.exit_code == 1, result.stdout + result.stderr
    assert "ok_category: suitable" in result.stdout
    assert "unknown:" in result.stdout


def test_suitability_json_mode() -> None:
    result = _invoke(
        "--pack",
        "sample",
        "--taxon",
        "T000000009",
        "--phase",
        "flowering",
        *_TROPICAL,
        "--json",
    )
    assert result.exit_code == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "ok_category"
    assert payload["category"] == "suitable"


def test_suitability_conflict_site_json_and_flags() -> None:
    result = _invoke(
        "--pack",
        "sample",
        "--taxon",
        "T000000009",
        "--site-json",
        '{"soil_ph": 6.5}',
        "--soil-ph",
        "6.5",
    )
    assert result.exit_code == 2, result.stdout + result.stderr
    assert "use either" in result.stderr


def test_suitability_pack_not_found_exit_3(tmp_path: Path) -> None:
    result = _invoke(
        "--pack",
        str(tmp_path / "nonexistent"),
        "--taxon",
        "T000000009",
        "--phase",
        "flowering",
        *_TROPICAL,
    )
    assert result.exit_code == 3, result.stdout + result.stderr
    assert "PACK_NOT_FOUND" in result.stderr
