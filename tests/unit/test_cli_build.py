"""CLI agri-core pack build behavior."""

from __future__ import annotations

import re
import shutil
import tomllib
from importlib.resources import files as pkg_files
from pathlib import Path

import pytest
from typer.testing import CliRunner

from agri_core.cli import app
from agri_core.pack import compute_pack_hash, load_knowledge_set

pytestmark = pytest.mark.unit

_BAD_HASH = "sha256:" + ("0" * 64)


def _sample_source(tmp_path: Path, *, strip_hash: bool = False) -> Path:
    src = Path(str(pkg_files("agri_core") / "_samples" / "sample_pack"))
    dst = tmp_path / "src"
    shutil.copytree(src, dst)
    if strip_hash:
        toml = dst / "pack.toml"
        lines = [
            ln
            for ln in toml.read_text(encoding="utf-8").splitlines()
            if not ln.startswith("content_hash")
        ]
        toml.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return dst


def _break_hash(src: Path) -> None:
    toml = src / "pack.toml"
    text = toml.read_text(encoding="utf-8")
    toml.write_text(
        re.sub(r'content_hash = "[^"]*"', f'content_hash = "{_BAD_HASH}"', text),
        encoding="utf-8",
    )


def test_build_rejects_sample_keyword() -> None:
    result = CliRunner().invoke(app, ["pack", "build", "--pack", "sample", "--out", "out"])
    assert result.exit_code == 2
    assert "explicit path" in result.stderr


def test_build_rejects_out_with_existing_sqlite(tmp_path: Path) -> None:
    src = _sample_source(tmp_path)
    out = tmp_path / "out"
    out.mkdir()
    (out / "pack.sqlite").write_bytes(b"stub")
    result = CliRunner().invoke(app, ["pack", "build", "--pack", str(src), "--out", str(out)])
    assert result.exit_code == 2
    assert "already exists" in result.stderr


def test_build_rejects_out_with_existing_toml(tmp_path: Path) -> None:
    src = _sample_source(tmp_path)
    out = tmp_path / "out"
    out.mkdir()
    (out / "pack.toml").write_bytes(b"stub")
    result = CliRunner().invoke(app, ["pack", "build", "--pack", str(src), "--out", str(out)])
    assert result.exit_code == 2
    assert "already exists" in result.stderr


def test_build_rejects_pack_not_found(tmp_path: Path) -> None:
    result = CliRunner().invoke(
        app,
        [
            "pack",
            "build",
            "--pack",
            str(tmp_path / "nope"),
            "--out",
            str(tmp_path / "out"),
        ],
    )
    assert result.exit_code == 3
    assert "PACK_NOT_FOUND" in result.stderr


def test_build_rejects_invalid_source_pack(tmp_path: Path) -> None:
    src = _sample_source(tmp_path, strip_hash=True)
    facts = src / "facts" / "T000000001.csv"
    with facts.open("a", encoding="utf-8") as fh:
        fh.write(
            'F99999999999,T999999999,soil_ph,,"{""shape"":""scalar"",'
            '""unit"":""pH"",""value"":7.0}","{}",curated,S001,,x,'
            "A,approved,r,2026-01-01,\n"
        )
    result = CliRunner().invoke(
        app,
        ["pack", "build", "--pack", str(src), "--out", str(tmp_path / "out")],
    )
    assert result.exit_code == 3
    assert "PACK_FK_VIOLATION" in result.stderr


def test_build_rejects_broken_source_hash(tmp_path: Path) -> None:
    src = _sample_source(tmp_path)
    _break_hash(src)
    result = CliRunner().invoke(
        app,
        ["pack", "build", "--pack", str(src), "--out", str(tmp_path / "out")],
    )
    assert result.exit_code == 3
    assert "PACK_HASH_MISMATCH" in result.stderr
    assert not (tmp_path / "out" / "pack.sqlite").exists()


def test_build_creates_out_files(tmp_path: Path) -> None:
    src = _sample_source(tmp_path)
    out = tmp_path / "out"
    result = CliRunner().invoke(app, ["pack", "build", "--pack", str(src), "--out", str(out)])
    assert result.exit_code == 0, result.stdout + result.stderr
    assert (out / "pack.sqlite").is_file()
    assert (out / "pack.toml").is_file()


def test_build_prints_hash_summary(tmp_path: Path) -> None:
    src = _sample_source(tmp_path)
    out = tmp_path / "out"
    result = CliRunner().invoke(app, ["pack", "build", "--pack", str(src), "--out", str(out)])
    assert result.exit_code == 0, result.stdout + result.stderr
    assert "source:" in result.stdout
    assert "built:" in result.stdout
    assert "content_hash: sha256:" in result.stdout
    assert "artifact_sha256: sha256:" in result.stdout


def test_build_built_pack_loads(tmp_path: Path) -> None:
    src = _sample_source(tmp_path)
    out = tmp_path / "out"
    result = CliRunner().invoke(app, ["pack", "build", "--pack", str(src), "--out", str(out)])
    assert result.exit_code == 0, result.stdout + result.stderr
    ks = load_knowledge_set(out, allow_synthetic=True)
    assert ks.verified is True


def test_build_repeated_to_fresh_dir_byte_identical(tmp_path: Path) -> None:
    src = _sample_source(tmp_path)
    out1 = tmp_path / "out1"
    out2 = tmp_path / "out2"
    r1 = CliRunner().invoke(app, ["pack", "build", "--pack", str(src), "--out", str(out1)])
    r2 = CliRunner().invoke(app, ["pack", "build", "--pack", str(src), "--out", str(out2)])
    assert r1.exit_code == 0, r1.stderr
    assert r2.exit_code == 0, r2.stderr
    assert (out1 / "pack.sqlite").read_bytes() == (out2 / "pack.sqlite").read_bytes()


def test_update_source_hash_default_off(tmp_path: Path) -> None:
    src = _sample_source(tmp_path)
    _break_hash(src)
    before = (src / "pack.toml").read_bytes()
    result = CliRunner().invoke(
        app, ["pack", "build", "--pack", str(src), "--out", str(tmp_path / "out")]
    )
    assert result.exit_code == 3
    assert "PACK_HASH_MISMATCH" in result.stderr
    assert (src / "pack.toml").read_bytes() == before


def test_update_source_hash_rewrites_when_stale(tmp_path: Path) -> None:
    src = _sample_source(tmp_path)
    _break_hash(src)
    result = CliRunner().invoke(
        app,
        [
            "pack",
            "build",
            "--pack",
            str(src),
            "--out",
            str(tmp_path / "out"),
            "--update-source-hash",
        ],
    )
    assert result.exit_code == 0, result.stdout + result.stderr
    assert "source_hash: updated" in result.stdout
    data = tomllib.loads((src / "pack.toml").read_text(encoding="utf-8"))
    assert data["content_hash"] == compute_pack_hash(src)


def test_update_source_hash_noop_when_current(tmp_path: Path) -> None:
    src = _sample_source(tmp_path)
    before = (src / "pack.toml").read_bytes()
    result = CliRunner().invoke(
        app,
        [
            "pack",
            "build",
            "--pack",
            str(src),
            "--out",
            str(tmp_path / "out"),
            "--update-source-hash",
        ],
    )
    assert result.exit_code == 0, result.stdout + result.stderr
    assert "source_hash: unchanged" in result.stdout
    assert (src / "pack.toml").read_bytes() == before


def test_build_sample_by_explicit_path_succeeds(tmp_path: Path) -> None:
    src = Path(str(pkg_files("agri_core") / "_samples" / "sample_pack"))
    out = tmp_path / "out"
    result = CliRunner().invoke(app, ["pack", "build", "--pack", str(src), "--out", str(out)])
    assert result.exit_code == 0, result.stdout + result.stderr
    assert (out / "pack.sqlite").is_file()


def test_build_out_dir_with_taxa_csv_rejected(tmp_path: Path) -> None:
    src = _sample_source(tmp_path)
    out = tmp_path / "out"
    out.mkdir()
    (out / "taxa.csv").write_bytes(b"taxon_id\n")
    result = CliRunner().invoke(app, ["pack", "build", "--pack", str(src), "--out", str(out)])
    assert result.exit_code == 3
    assert "PACK_ERROR" in result.stderr


def test_build_prints_content_hash_even_without_flag(tmp_path: Path) -> None:
    src = _sample_source(tmp_path)
    out = tmp_path / "out"
    result = CliRunner().invoke(app, ["pack", "build", "--pack", str(src), "--out", str(out)])
    assert result.exit_code == 0, result.stdout + result.stderr
    assert "content_hash: sha256:" in result.stdout
    assert "artifact_sha256: sha256:" in result.stdout
