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
from agri_core.pack import TABLES, PackError, load_knowledge_set, write_table
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


# ===== Coverage: _load_vocab / _vocab_keys / infer_organism_group =====


class _FakeTraversable:
    """Minimal importlib.resources.Traversable stand-in for tests."""

    def __init__(self, base: Path) -> None:
        self._base = base

    def __truediv__(self, other: str) -> _FakeTraversable:
        return _FakeTraversable(self._base / other)

    def is_file(self) -> bool:
        return self._base.is_file()

    def read_text(self, encoding: str = "utf-8") -> str:
        return self._base.read_text(encoding=encoding)


class _NoFileTraversable:
    """Traversable that claims nothing is a file (forces repo fallback)."""

    def __truediv__(self, _other: str) -> _NoFileTraversable:
        return self

    def is_file(self) -> bool:
        return False

    def read_text(self, encoding: str = "utf-8") -> str:  # pragma: no cover
        raise AssertionError("should not be called")


class _FakeYamlNonMapping:
    @staticmethod
    def safe_load(_text: str) -> object:
        return ["not", "a", "mapping"]


def test_load_vocab_packaged_success(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from agri_core.pack import scaffold as mod

    target = tmp_path / "_dictionary" / "vocab" / "archetypes.yaml"
    target.parent.mkdir(parents=True)
    target.write_text("archetypes:\n  annual:\n    description: x\n", encoding="utf-8")
    monkeypatch.setattr(mod, "pkg_files", lambda _name: _FakeTraversable(tmp_path))
    data = mod._load_vocab("archetypes")
    assert "annual" in data["archetypes"]


def test_load_vocab_packaged_non_mapping(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from agri_core.pack import scaffold as mod

    target = tmp_path / "_dictionary" / "vocab" / "archetypes.yaml"
    target.parent.mkdir(parents=True)
    target.write_text("- not\n- a mapping\n", encoding="utf-8")
    monkeypatch.setattr(mod, "pkg_files", lambda _name: _FakeTraversable(tmp_path))
    with pytest.raises(PackError, match=r"not a mapping"):
        mod._load_vocab("archetypes")


def test_load_vocab_packaged_raises_falls_back(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from agri_core.pack import scaffold as mod

    def raising(_name: str) -> object:
        raise FileNotFoundError("simulated")

    monkeypatch.setattr(mod, "pkg_files", raising)
    data = mod._load_vocab("archetypes")
    assert "annual" in data["archetypes"]


def test_load_vocab_repo_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    from agri_core.pack import scaffold as mod

    monkeypatch.setattr(mod, "pkg_files", lambda _name: _NoFileTraversable())
    with pytest.raises(PackError, match=r"not found"):
        mod._load_vocab("definitely_not_a_real_vocab_xyz")


def test_load_vocab_repo_non_mapping(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from agri_core.pack import scaffold as mod

    monkeypatch.setattr(mod, "pkg_files", lambda _name: _NoFileTraversable())
    monkeypatch.setattr(mod, "yaml", _FakeYamlNonMapping)
    with pytest.raises(PackError, match=r"not a mapping"):
        mod._load_vocab("archetypes")


def test_vocab_keys_non_mapping_section(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from agri_core.pack import scaffold as mod

    monkeypatch.setattr(mod, "_load_vocab", lambda _name: {"archetypes": ["not", "a", "dict"]})
    with pytest.raises(PackError, match=r"is not a mapping"):
        mod._vocab_keys("archetypes", "archetypes")


def test_infer_organism_group_not_mapping(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from agri_core.pack import scaffold as mod

    monkeypatch.setattr(mod, "_load_vocab", lambda _name: {"organism_groups": ["not", "dict"]})
    with pytest.raises(PackError, match=r"must be a mapping"):
        mod.infer_organism_group("annual")


def test_infer_organism_group_skips_non_dict_spec(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from agri_core.pack import scaffold as mod

    monkeypatch.setattr(
        mod,
        "_load_vocab",
        lambda _name: {
            "organism_groups": {
                "bad_group": "not a dict",
                "vascular_plant": {"allowed_archetypes": ["annual"]},
            }
        },
    )
    assert mod.infer_organism_group("annual") == "vascular_plant"


def test_infer_organism_group_no_match(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from agri_core.pack import scaffold as mod

    monkeypatch.setattr(
        mod,
        "_load_vocab",
        lambda _name: {
            "organism_groups": {
                "vascular_plant": {"allowed_archetypes": ["annual"]},
            }
        },
    )
    with pytest.raises(PackError, match=r"matches 0 organism groups"):
        mod.infer_organism_group("nonexistent_archetype_xyz")


def test_infer_organism_group_ambiguous(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from agri_core.pack import scaffold as mod

    monkeypatch.setattr(
        mod,
        "_load_vocab",
        lambda _name: {
            "organism_groups": {
                "group_a": {"allowed_archetypes": ["annual"]},
                "group_b": {"allowed_archetypes": ["annual"]},
            }
        },
    )
    with pytest.raises(PackError, match=r"matches 2 organism groups"):
        mod.infer_organism_group("annual")


# ===== Coverage: _resolve_source_ids / _default_source_id =====


def test_resolve_source_ids_explicit() -> None:
    from agri_core.pack import scaffold as mod

    assert mod._resolve_source_ids(("S001", "S002"), {}) == ("S001", "S002")


def test_default_source_id_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    from agri_core.pack import scaffold as mod

    class _FakeTable:
        rows: tuple[dict[str, object], ...] = ()

    monkeypatch.setattr(mod, "read_table", lambda *_a, **_kw: _FakeTable())
    with pytest.raises(PackError, match=r"sources.csv is empty"):
        mod._default_source_id({"sources.csv": b""})


def test_default_source_id_missing_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from agri_core.pack import scaffold as mod

    class _FakeTable:
        rows: tuple[dict[str, object], ...] = ({"url": "x"},)

    monkeypatch.setattr(mod, "read_table", lambda *_a, **_kw: _FakeTable())
    with pytest.raises(PackError, match=r"no 'id' column value"):
        mod._default_source_id({"sources.csv": b""})


# ===== Coverage: direct scaffold_taxon validation =====


def test_scaffold_direct_empty_name(tmp_path: Path) -> None:
    from agri_core.pack.scaffold import scaffold_taxon

    with pytest.raises(PackError, match=r"scientific_name"):
        scaffold_taxon(tmp_path, scientific_name="", archetype="annual", uses=("veg",))


def test_scaffold_direct_empty_uses(tmp_path: Path) -> None:
    from agri_core.pack.scaffold import scaffold_taxon

    with pytest.raises(PackError, match=r"uses must contain"):
        scaffold_taxon(tmp_path, scientific_name="X", archetype="annual", uses=())


# ===== Coverage: OSError atomic cleanup =====


def test_scaffold_oserror_atomic_cleanup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    src = _sample_source(tmp_path, strip_hash=True)
    original_write = Path.write_bytes

    def fake_write(self: Path, data: bytes) -> int:
        if self.name.endswith(".tmp") and str(self).startswith(str(src)):
            raise OSError("simulated write failure")
        return original_write(self, data)

    monkeypatch.setattr(Path, "write_bytes", fake_write)
    r = _invoke(_scaffold_args(src))
    assert r.exit_code == 70
    assert "OSError" in r.stderr
    assert not any(src.rglob("*.tmp"))
