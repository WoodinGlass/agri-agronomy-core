"""CLI behaviour via typer's CliRunner."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from agri_core import __version__
from agri_core.cli import app
from agri_core.pack import compute_pack_hash

pytestmark = pytest.mark.unit

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "sources"


def _header_bytes() -> bytes:
    return b"id,url,license,commercial_use,access_date,citation\n"


def _make_pack(
    tmp_path: Path,
    sources_content: bytes,
    *,
    name: str = "pack1",
    version: str = "1.0.0",
    schema_version: int = 1,
    engine_min: str = "0.0.0",
) -> Path:
    root = tmp_path / "pack"
    root.mkdir()
    body = (
        f'name = "{name}"\n'
        f'version = "{version}"\n'
        f"schema_version = {schema_version}\n"
        f'engine_min = "{engine_min}"\n'
    )
    (root / "pack.toml").write_text(body, encoding="utf-8")
    (root / "sources.csv").write_bytes(sources_content)
    digest = compute_pack_hash(root)
    (root / "pack.toml").write_text(body + f'content_hash = "{digest}"\n', encoding="utf-8")
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


def test_lint_sources_sample_ok() -> None:
    result = CliRunner().invoke(app, ["lint-sources", "--pack", "sample"])
    assert result.exit_code == 0, result.stdout
    assert "pack: sample 0.1.0 (sample)" in result.stdout


def test_validate_sample_ok() -> None:
    result = CliRunner().invoke(app, ["validate", "--pack", "sample"])
    assert result.exit_code == 0, result.stdout
    assert "pack: sample 0.1.0 (sample)" in result.stdout


def test_validate_directory_pack(tmp_path: Path) -> None:
    root = _make_pack(tmp_path, _header_bytes())
    result = CliRunner().invoke(app, ["validate", "--pack", str(root)])
    assert result.exit_code == 0, result.stdout
    assert "pack: pack1 1.0.0 (" in result.stdout


def test_pack_not_found_exit_3(tmp_path: Path) -> None:
    result = CliRunner().invoke(app, ["validate", "--pack", str(tmp_path / "nope")])
    assert result.exit_code == 3


def test_invalid_manifest_exit_3(tmp_path: Path) -> None:
    root = tmp_path / "pack"
    root.mkdir()
    (root / "pack.toml").write_text("garbage = true\n", encoding="utf-8")
    (root / "sources.csv").write_bytes(_header_bytes())
    result = CliRunner().invoke(app, ["validate", "--pack", str(root)])
    assert result.exit_code == 3


def test_unsupported_schema_version_exit_3(tmp_path: Path) -> None:
    root = _make_pack(tmp_path, _header_bytes(), schema_version=999)
    result = CliRunner().invoke(app, ["validate", "--pack", str(root)])
    assert result.exit_code == 3


def test_data_dir_option_rejected_exit_2() -> None:
    result = CliRunner().invoke(app, ["validate", "--data-dir", "."])
    assert result.exit_code == 2


def test_pack_option_required() -> None:
    result = CliRunner().invoke(app, ["validate"])
    assert result.exit_code == 2


def test_lint_sources_broken_exit_1(tmp_path: Path) -> None:
    root = _make_pack(tmp_path, (FIXTURES / "broken.csv").read_bytes())
    result = CliRunner().invoke(app, ["lint-sources", "--pack", str(root)])
    assert result.exit_code == 1
