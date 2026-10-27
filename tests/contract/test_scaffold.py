"""Scaffold new taxon into existing source pack (M6-5)."""

from __future__ import annotations

import re
import shutil
from importlib.resources import files as pkg_files
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from agri_core.cli import app
from agri_core.models.ids import TAXON_ID_PATTERN
from agri_core.pack import TABLES, load_knowledge_set, write_table
from agri_core.pack.tables import read_table

pytestmark = pytest.mark.contract

_TAXON_ID_RE = re.compile(TAXON_ID_PATTERN)


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


def _read_taxa(src: Path) -> list[dict[str, Any]]:
    data = (src / "taxa.csv").read_bytes()
    table = read_table(TABLES["taxa"], data, source_name="taxa.csv")
    return [dict(row) for row in table.rows]


def _invoke(args: list[str]):
    return CliRunner().invoke(app, args)


def _scaffold_args(src: Path, **overrides: str) -> list[str]:
    defaults = {
        "name": "Foo bar",
        "archetype": "annual",
        "use": "vegetable",
    }
    defaults.update(overrides)
    return [
        "pack",
        "scaffold",
        "--pack",
        str(src),
        "--scientific-name",
        defaults["name"],
        "--archetype",
        defaults["archetype"],
        "--use",
        defaults["use"],
    ]


def test_scaffold_rejects_sample_keyword() -> None:
    r = _invoke(
        [
            "pack",
            "scaffold",
            "--pack",
            "sample",
            "--scientific-name",
            "X",
            "--archetype",
            "annual",
            "--use",
            "vegetable",
        ]
    )
    assert r.exit_code == 2
    assert "explicit path" in r.stderr


def test_scaffold_rejects_missing_pack_dir(tmp_path: Path) -> None:
    r = _invoke(_scaffold_args(tmp_path / "nope"))
    assert r.exit_code == 3
    assert "PACK_NOT_FOUND" in r.stderr


def test_scaffold_rejects_empty_scientific_name(tmp_path: Path) -> None:
    src = _sample_source(tmp_path)
    r = _invoke(_scaffold_args(src, name="   "))
    assert r.exit_code == 2
    assert "scientific-name" in r.stderr


def test_scaffold_rejects_unknown_archetype(tmp_path: Path) -> None:
    src = _sample_source(tmp_path)
    r = _invoke(_scaffold_args(src, archetype="not_a_real_archetype"))
    assert r.exit_code == 3
    assert "archetype" in r.stderr.lower()


def test_scaffold_happy_creates_row_and_facts_file(tmp_path: Path) -> None:
    src = _sample_source(tmp_path)
    before = _read_taxa(src)
    r = _invoke(_scaffold_args(src, name="Foo bar"))
    assert r.exit_code == 0, r.stdout + r.stderr
    after = _read_taxa(src)
    assert len(after) == len(before) + 1
    new_row = next(row for row in after if row["scientific_name"] == "Foo bar")
    assert (src / "facts" / f"{new_row['taxon_id']}.csv").is_file()


def test_scaffold_taxon_id_matches_pattern(tmp_path: Path) -> None:
    src = _sample_source(tmp_path)
    r = _invoke(_scaffold_args(src))
    assert r.exit_code == 0, r.stderr
    m = re.search(r"scaffolded: (T\S+)", r.stdout)
    assert m is not None
    assert _TAXON_ID_RE.match(m.group(1))


def test_scaffold_taxon_id_unique_vs_existing(tmp_path: Path) -> None:
    src = _sample_source(tmp_path)
    existing = {row["taxon_id"] for row in _read_taxa(src)}
    r = _invoke(_scaffold_args(src))
    assert r.exit_code == 0, r.stderr
    m = re.search(r"scaffolded: (T\S+)", r.stdout)
    assert m is not None
    assert m.group(1) not in existing


def test_scaffold_taxa_csv_sorted_after_scaffold(tmp_path: Path) -> None:
    src = _sample_source(tmp_path)
    before_bytes = (src / "taxa.csv").read_bytes()
    r = _invoke(_scaffold_args(src))
    assert r.exit_code == 0, r.stderr
    after_bytes = (src / "taxa.csv").read_bytes()
    assert after_bytes.startswith(b"taxon_id,")
    assert after_bytes != before_bytes
    # Deterministic: rewrite from parsed rows yields identical bytes.
    rows = _read_taxa(src)
    assert write_table(TABLES["taxa"], rows) == after_bytes


def test_scaffold_pack_stays_loadable_after_scaffold(tmp_path: Path) -> None:
    src = _sample_source(tmp_path, strip_hash=True)
    r = _invoke(_scaffold_args(src))
    assert r.exit_code == 0, r.stderr
    ks = load_knowledge_set(src, allow_synthetic=True)
    assert ks.verified is False


def test_scaffold_then_build_succeeds(tmp_path: Path) -> None:
    src = _sample_source(tmp_path, strip_hash=True)
    out = tmp_path / "out"
    r1 = _invoke(_scaffold_args(src))
    assert r1.exit_code == 0, r1.stderr
    r2 = _invoke(["pack", "build", "--pack", str(src), "--out", str(out)])
    assert r2.exit_code == 0, r2.stdout + r2.stderr
    assert (out / "pack.sqlite").is_file()


def _seed_collision_placeholder(src: Path) -> None:
    existing = _read_taxa(src)
    extra = {
        "taxon_id": "TAAAAAAAAA",
        "rank": "species",
        "scientific_name": "Placeholder",
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
    (src / "taxa.csv").write_bytes(write_table(TABLES["taxa"], [*existing, extra]))


def test_scaffold_collision_retries_and_succeeds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    src = _sample_source(tmp_path, strip_hash=True)
    _seed_collision_placeholder(src)
    from agri_core.pack import scaffold as scaffold_module

    seq = iter(["A"] * 9 + ["B"] * 9)
    monkeypatch.setattr(scaffold_module.secrets, "choice", lambda _alphabet: next(seq))
    r = _invoke(_scaffold_args(src))
    assert r.exit_code == 0, r.stdout + r.stderr
    m = re.search(r"scaffolded: (T\S+)", r.stdout)
    assert m is not None
    assert m.group(1) == "TBBBBBBBBB"


def test_scaffold_collision_exhausted_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    src = _sample_source(tmp_path, strip_hash=True)
    _seed_collision_placeholder(src)
    from agri_core.pack import scaffold as scaffold_module

    monkeypatch.setattr(scaffold_module.secrets, "choice", lambda _alphabet: "A")
    r = _invoke(_scaffold_args(src))
    assert r.exit_code == 3
    assert "cannot generate unique taxon_id" in r.stderr
