"""CLI behaviour via typer's CliRunner."""

from __future__ import annotations

import json
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


# ---- M7-8: validate --json / --strict --------------------------------------


def test_validate_json_output() -> None:
    """--json emits pack + sources + report; exit 0 for clean sample."""
    result = CliRunner().invoke(app, ["validate", "--pack", "sample", "--json"])
    assert result.exit_code == 0, result.stdout + result.stderr
    # JSON must be the only stdout content (banner goes to stderr)
    data = json.loads(result.stdout)
    assert data["pack"]["name"] == "sample"
    assert data["pack"]["version"] == "0.1.0"
    assert data["pack"]["synthetic"] is True
    assert data["pack"]["verified"] is True
    assert data["sources"] == {
        "total": 3,
        "yes": 3,
        "no": 0,
        "unclear": 0,
    }
    assert data["report"]["ok"] is True
    assert data["report"]["findings"] == []
    assert data["report"]["report_version"] == 1


def test_validate_json_shape() -> None:
    """Top-level keys and report keys are exactly as documented."""
    result = CliRunner().invoke(app, ["validate", "--pack", "sample", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert set(data.keys()) == {"pack", "sources", "report"}
    assert set(data["pack"].keys()) == {"name", "version", "synthetic", "verified"}
    assert set(data["sources"].keys()) == {"total", "yes", "no", "unclear"}
    assert set(data["report"].keys()) == {"report_version", "ok", "findings"}


def test_validate_rule_error_finding_exit_1(tmp_path: Path) -> None:
    """A rule-error finding (not a load error) -> exit 1, report.ok=false."""
    # Valid SourceRow that triggers PACK_LICENSE_NC_COMMERCIAL (M7-4):
    # NC license + commercial_use=yes.
    src = (
        b"id,url,license,commercial_use,access_date,citation\n"
        b"S001,https://example.org/s1,CC-BY-NC-4.0,yes,2026-01-15,doc\n"
    )
    root = _make_pack(tmp_path, src)
    result = CliRunner().invoke(app, ["validate", "--pack", str(root), "--json"])
    assert result.exit_code == 1, result.stdout + result.stderr
    data = json.loads(result.stdout)
    assert data["report"]["ok"] is False
    codes = {f["code"] for f in data["report"]["findings"]}
    assert "PACK_LICENSE_NC_COMMERCIAL" in codes, codes


def test_validate_unreadable_exit_3_json(tmp_path: Path) -> None:
    """Pack not found -> exit 3, no JSON emitted (payload requires a pack)."""
    result = CliRunner().invoke(app, ["validate", "--pack", str(tmp_path / "nope"), "--json"])
    assert result.exit_code == 3
    assert result.stdout.strip() == ""
    assert "PACK_NOT_FOUND" in result.stderr


def test_validate_strict_no_warnings_exit_0() -> None:
    """--strict on a pack with 0 errors and 0 warnings still exits 0."""
    result = CliRunner().invoke(app, ["validate", "--pack", "sample", "--strict"])
    assert result.exit_code == 0, result.stdout + result.stderr


def test_compute_exit_code_errors_always_1() -> None:
    """Errors -> exit 1 regardless of --strict."""
    from agri_core.cli import EXIT_ERROR, EXIT_OK, _compute_exit_code

    assert _compute_exit_code(1, 0, strict=False) == EXIT_ERROR
    assert _compute_exit_code(1, 0, strict=True) == EXIT_ERROR
    assert _compute_exit_code(0, 0, strict=False) == EXIT_OK
    assert _compute_exit_code(0, 0, strict=True) == EXIT_OK


def test_compute_exit_code_strict_promotes_warnings() -> None:
    """Warnings-only: exit 1 under --strict, exit 0 without."""
    from agri_core.cli import EXIT_ERROR, EXIT_OK, _compute_exit_code

    assert _compute_exit_code(0, 1, strict=False) == EXIT_OK
    assert _compute_exit_code(0, 1, strict=True) == EXIT_ERROR


def test_compute_exit_code_warnings_and_errors_errors_win() -> None:
    """When both present, errors dominate (exit 1) -- same either way."""
    from agri_core.cli import EXIT_ERROR, _compute_exit_code

    assert _compute_exit_code(1, 5, strict=False) == EXIT_ERROR
    assert _compute_exit_code(1, 5, strict=True) == EXIT_ERROR
