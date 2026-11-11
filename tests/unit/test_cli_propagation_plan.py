"""CLI propagation-plan subcommand (M15).

The sample pack has no propagation facts for any taxon; the happy path
is exercised by P5 unit tests using from_rows. This module tests the
CLI wrapper: unknown outcome, JSON mode, invalid date, pack not found.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from agri_core.cli import app

pytestmark = pytest.mark.unit


def _invoke(*args: str):
    return CliRunner().invoke(app, ["propagation-plan", *args])


def test_propagation_plan_unknown_exit_1() -> None:
    result = _invoke(
        "--pack",
        "sample",
        "--taxon",
        "T000000009",
        "--start-date",
        "2026-04-15",
        "--method",
        "seed",
    )
    assert result.exit_code == 1, result.stdout + result.stderr
    assert "unknown:" in result.stdout
    assert "no_match" in result.stdout


def test_propagation_plan_json_unknown() -> None:
    result = _invoke(
        "--pack",
        "sample",
        "--taxon",
        "T000000009",
        "--start-date",
        "2026-04-15",
        "--method",
        "seed",
        "--json",
    )
    assert result.exit_code == 1, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "unknown"
    assert payload["code"] == "no_match"


def test_propagation_plan_invalid_date_exit_2() -> None:
    result = _invoke(
        "--pack",
        "sample",
        "--taxon",
        "T000000009",
        "--start-date",
        "not-a-date",
        "--method",
        "seed",
    )
    assert result.exit_code == 2, result.stdout + result.stderr
    assert "invalid --start-date" in result.stderr


def test_propagation_plan_pack_not_found_exit_3(tmp_path: Path) -> None:
    result = _invoke(
        "--pack",
        str(tmp_path / "nonexistent"),
        "--taxon",
        "T000000009",
        "--start-date",
        "2026-04-15",
        "--method",
        "seed",
    )
    assert result.exit_code == 3, result.stdout + result.stderr
    assert "PACK_NOT_FOUND" in result.stderr
