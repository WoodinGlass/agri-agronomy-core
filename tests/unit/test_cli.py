"""CLI behaviour via typer's CliRunner."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from agri_core import __version__
from agri_core.cli import app

pytestmark = pytest.mark.unit

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "sources"


def _header_bytes() -> bytes:
    return b"id,url,license,commercial_use,access_date,citation\n"


def _make_data_root(tmp_path: Path, sources_content: bytes) -> Path:
    root = tmp_path / "data"
    (root / "profiles").mkdir(parents=True)
    (root / "profiles" / "sources.csv").write_bytes(sources_content)
    (root / "schema").mkdir()
    return root


def test_version_exits_zero_and_prints() -> None:
    result = CliRunner().invoke(app, ["--version"])
    assert result.exit_code == 0
    assert __version__ in result.stdout


def test_help_exits_zero() -> None:
    result = CliRunner().invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "lint-sources" in result.stdout
    assert "validate" in result.stdout


def test_lint_sources_empty_data_ok(tmp_path: Path) -> None:
    root = _make_data_root(tmp_path, _header_bytes())
    result = CliRunner().invoke(app, ["lint-sources", "--data-dir", str(root)])
    assert result.exit_code == 0, result.stdout
    assert "data: override" in result.stdout
    assert "sources: 0" in result.stdout
    assert "errors: 0" in result.stdout


def test_lint_sources_broken_returns_one(tmp_path: Path) -> None:
    root = _make_data_root(tmp_path, (FIXTURES / "broken.csv").read_bytes())
    result = CliRunner().invoke(app, ["lint-sources", "--data-dir", str(root)])
    assert result.exit_code == 1, result.stdout


def test_lint_sources_data_not_found_returns_three(tmp_path: Path) -> None:
    missing = tmp_path / "nope"
    result = CliRunner().invoke(app, ["lint-sources", "--data-dir", str(missing)])
    assert result.exit_code == 3, result.stdout


def test_validate_empty_ok(tmp_path: Path) -> None:
    root = _make_data_root(tmp_path, _header_bytes())
    (root / "schema" / "empty.schema.json").write_text(
        '{"$schema": "https://json-schema.org/draft/2020-12/schema", "type": "object"}',
        encoding="utf-8",
    )
    result = CliRunner().invoke(app, ["validate", "--data-dir", str(root)])
    assert result.exit_code == 0, result.stdout
    assert "agri-core" in result.stdout
    assert "| data: override" in result.stdout
    assert "schemas: 1" in result.stdout
    assert "errors: 0" in result.stdout


def test_validate_invalid_schema_returns_one(tmp_path: Path) -> None:
    root = _make_data_root(tmp_path, _header_bytes())
    (root / "schema" / "bad.schema.json").write_text(
        '{"type": "not-a-real-type"}', encoding="utf-8"
    )
    result = CliRunner().invoke(app, ["validate", "--data-dir", str(root)])
    assert result.exit_code == 1, result.stdout
    assert "SCHEMA bad.schema.json" in result.stdout


def test_validate_data_not_found_returns_three(tmp_path: Path) -> None:
    result = CliRunner().invoke(app, ["validate", "--data-dir", str(tmp_path / "nope")])
    assert result.exit_code == 3, result.stdout


def test_validate_also_lints_sources(tmp_path: Path) -> None:
    root = _make_data_root(tmp_path, (FIXTURES / "broken.csv").read_bytes())
    (root / "schema" / "ok.schema.json").write_text(
        '{"$schema": "https://json-schema.org/draft/2020-12/schema", "type": "object"}',
        encoding="utf-8",
    )
    result = CliRunner().invoke(app, ["validate", "--data-dir", str(root)])
    assert result.exit_code == 1, result.stdout
    assert "SRC0" in result.stdout or "SRC1" in result.stdout
