"""CLI behaviour via typer's CliRunner."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from agri_core import __version__
from agri_core.cli import app
from agri_core.pack import compute_pack_hash
from agri_core.pack.tables import TABLES

pytestmark = pytest.mark.unit

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "sources"


def _header_bytes() -> bytes:
    return b"id,url,license,commercial_use,access_date,citation\n"


_HEADER_BY_TABLE: dict[str, str] = {
    "taxa": "taxon_id,rank,scientific_name,accepted_name,organism_group,"
    "archetype,uses,traits,parent_id,external_ids,src,dataset_id\n",
    "names": "taxon_id,name,language,script,kind,preferred,src,dataset_id\n",
    "hazards": "taxon_id,hazard_code,severity,reason,as_of,authority,src,dataset_id\n",
    "datasets": "dataset_id,name,version,license,checksum,url,locator,access_date\n",
}


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
        f'dictionary_min = "1.0.0"\n'
    )
    (root / "pack.toml").write_text(body, encoding="utf-8")
    for table, header in _HEADER_BY_TABLE.items():
        spec = TABLES[table]
        assert spec.filename is not None
        (root / spec.filename).write_text(header, encoding="utf-8")
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


# ---- M5-2b: banner + warning to stderr --------------------------------


def test_validate_synthetic_banner_on_stderr() -> None:
    result = CliRunner().invoke(app, ["validate", "--pack", "sample"])
    assert result.exit_code == 0, result.stdout
    assert "SYNTHETIC DATA" in result.stderr


def test_validate_unverified_warning_on_stderr(tmp_path: Path) -> None:
    root = _make_pack(tmp_path, _header_bytes())
    pt = root / "pack.toml"
    text = pt.read_text(encoding="utf-8")
    lines = [ln for ln in text.splitlines() if not ln.startswith("content_hash")]
    pt.write_text("\n".join(lines) + "\n", encoding="utf-8")
    result = CliRunner().invoke(app, ["validate", "--pack", str(root)])
    assert result.exit_code == 0, result.stdout
    assert "PACK_UNVERIFIED" in result.stderr


def test_validate_verified_silent_stderr(tmp_path: Path) -> None:
    root = _make_pack(tmp_path, _header_bytes())
    result = CliRunner().invoke(app, ["validate", "--pack", str(root)])
    assert result.exit_code == 0, result.stdout
    assert "PACK_UNVERIFIED" not in result.stderr
    assert "SYNTHETIC DATA" not in result.stderr


def test_lint_sources_ignores_structural_errors(tmp_path: Path) -> None:
    root = _make_pack(tmp_path, (FIXTURES / "broken.csv").read_bytes())
    result = CliRunner().invoke(app, ["lint-sources", "--pack", str(root)])
    assert result.exit_code == 1
    assert result.exit_code != 3


def test_validate_sample_by_path_succeeds() -> None:
    from pathlib import Path as _Path

    sample_path = (
        _Path(__file__).resolve().parents[2] / "src" / "agri_core" / "_samples" / "sample_pack"
    )
    result = CliRunner().invoke(app, ["validate", "--pack", str(sample_path)])
    assert result.exit_code == 0, result.stdout + result.stderr
    assert "SYNTHETIC DATA" in result.stderr
