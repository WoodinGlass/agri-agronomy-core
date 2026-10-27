"""CLI agri-core pack lock behavior."""

from __future__ import annotations

import os
import shutil
import tomllib
from datetime import date
from pathlib import Path

import pytest
from typer.testing import CliRunner

from agri_core.cli import app
from agri_core.pack import TABLES, compute_pack_hash, write_table

pytestmark = pytest.mark.unit


def _make_pack(root: Path, *, with_hash: bool = False) -> None:
    root.mkdir(parents=True, exist_ok=True)
    toml = (
        'name = "test"\n'
        'version = "1.0.0"\n'
        "schema_version = 1\n"
        'engine_min = "0.0.0"\n'
        'dictionary_min = "1.0.0"\n'
    )
    (root / "pack.toml").write_text(toml, encoding="utf-8")
    for name in ("taxa", "names", "hazards", "datasets", "sources"):
        spec = TABLES[name]
        assert spec.filename is not None
        (root / spec.filename).write_bytes(write_table(spec, []))
    if with_hash:
        digest = compute_pack_hash(root)
        (root / "pack.toml").write_text(toml + f'content_hash = "{digest}"\n', encoding="utf-8")


def _read_hash(root: Path) -> str:
    data = tomllib.loads((root / "pack.toml").read_text(encoding="utf-8"))
    return data["content_hash"]


def test_pack_lock_rejects_sample_keyword() -> None:
    result = CliRunner().invoke(app, ["pack", "lock", "--pack", "sample"])
    assert result.exit_code == 2
    assert "explicit path" in result.stderr
    assert "sample" in result.stderr


def test_pack_lock_writes_valid_hash(tmp_path: Path) -> None:
    root = tmp_path / "pack"
    _make_pack(root)
    result = CliRunner().invoke(app, ["pack", "lock", "--pack", str(root)])
    assert result.exit_code == 0, result.stdout + result.stderr
    assert "wrote content_hash" in result.stdout
    assert _read_hash(root) == compute_pack_hash(root)


def test_pack_lock_idempotent(tmp_path: Path) -> None:
    root = tmp_path / "pack"
    _make_pack(root)
    r1 = CliRunner().invoke(app, ["pack", "lock", "--pack", str(root)])
    assert r1.exit_code == 0
    first_bytes = (root / "pack.toml").read_bytes()
    r2 = CliRunner().invoke(app, ["pack", "lock", "--pack", str(root)])
    assert r2.exit_code == 0
    second_bytes = (root / "pack.toml").read_bytes()
    assert first_bytes == second_bytes


def test_pack_lock_normalized_key_order(tmp_path: Path) -> None:
    root = tmp_path / "pack"
    _make_pack(root)
    result = CliRunner().invoke(app, ["pack", "lock", "--pack", str(root)])
    assert result.exit_code == 0
    lines = (root / "pack.toml").read_text(encoding="utf-8").splitlines()
    non_empty = [ln for ln in lines if ln.strip()]
    expected_prefix = [
        "name =",
        "version =",
        "schema_version =",
        "engine_min =",
        "dictionary_min =",
        "synthetic =",
        "content_hash =",
    ]
    assert len(non_empty) == 7
    for line, prefix in zip(non_empty, expected_prefix, strict=True):
        assert line.startswith(prefix), f"line {line!r} does not start with {prefix!r}"


def test_pack_lock_preserves_required_fields(tmp_path: Path) -> None:
    root = tmp_path / "pack"
    _make_pack(root)
    result = CliRunner().invoke(app, ["pack", "lock", "--pack", str(root)])
    assert result.exit_code == 0
    data = tomllib.loads((root / "pack.toml").read_text(encoding="utf-8"))
    assert data["name"] == "test"
    assert data["version"] == "1.0.0"
    assert data["dictionary_min"] == "1.0.0"
    assert data["synthetic"] is False


def test_pack_lock_rejects_broken_pack(tmp_path: Path) -> None:
    root = tmp_path / "pack"
    _make_pack(root)
    before = (root / "pack.toml").read_bytes()

    source = {
        "id": "S001",
        "url": "https://example.org",
        "license": "CC0-1.0",
        "commercial_use": "yes",
        "access_date": date(2026, 1, 1),
        "citation": "x",
    }
    (root / "sources.csv").write_bytes(write_table(TABLES["sources"], [source]))

    taxon = {
        "taxon_id": "T000000001",
        "rank": "species",
        "scientific_name": "Testus",
        "accepted_name": None,
        "organism_group": "vascular_plant",
        "archetype": "annual",
        "uses": ["vegetable"],
        "traits": [],
        "parent_id": None,
        "external_ids": None,
        "src": ["S001"],
        "dataset_id": None,
    }
    (root / "taxa.csv").write_bytes(write_table(TABLES["taxa"], [taxon]))

    fact = {
        "fact_id": "F00000000001",
        "taxon_id": "T000000001",
        "parameter": "unknown_param",
        "phase": None,
        "value": {"shape": "scalar", "unit": "dimensionless", "value": 1.0},
        "scope": {},
        "provenance_kind": "curated",
        "src": ["S001"],
        "dataset_id": None,
        "locator": "t",
        "evidence": "A",
        "status": "approved",
        "reviewed_by": ["r"],
        "reviewed_at": date(2026, 1, 1),
        "superseded_by": None,
    }
    facts_dir = root / "facts"
    facts_dir.mkdir()
    (facts_dir / "T000000001.csv").write_bytes(write_table(TABLES["facts"], [fact]))

    result = CliRunner().invoke(app, ["pack", "lock", "--pack", str(root)])
    assert result.exit_code == 3
    assert "PACK_UNKNOWN_PARAMETER" in result.stderr
    after = (root / "pack.toml").read_bytes()
    assert before == after


def test_pack_lock_on_sample_by_path(tmp_path: Path) -> None:
    sample = Path(__file__).resolve().parents[2] / "src" / "agri_core" / "_samples" / "sample_pack"
    copy = tmp_path / "sample"
    shutil.copytree(sample, copy)
    before = (copy / "pack.toml").read_bytes()
    result = CliRunner().invoke(app, ["pack", "lock", "--pack", str(copy)])
    assert result.exit_code == 0, result.stdout + result.stderr
    after = (copy / "pack.toml").read_bytes()
    assert before == after


def test_pack_lock_atomic_no_partial_on_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "pack"
    _make_pack(root)
    before = (root / "pack.toml").read_bytes()

    def boom(src, dst):
        raise OSError("simulated replace failure")

    monkeypatch.setattr(os, "replace", boom)
    result = CliRunner().invoke(app, ["pack", "lock", "--pack", str(root)])
    assert result.exit_code == 70
    assert "OSError" in result.stderr
    after = (root / "pack.toml").read_bytes()
    assert before == after
    assert not (root / "pack.toml.tmp").exists()
