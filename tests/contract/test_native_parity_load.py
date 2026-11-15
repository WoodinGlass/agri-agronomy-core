"""Parity SQLiteKnowledgeSet vs RustKnowledgeSet (M21 G4-3).

Verifies the native in-memory loader behind ``agri_core._native`` returns
rows identical to the Python ``SQLiteKnowledgeSet`` on the sample pack,
and that the loader delegate in :mod:`agri_core.pack.loader` switches to
``RustKnowledgeSet`` when ``_NATIVE_LOAD`` is set (which G4-4 will flip
after the perf gate).

Skips cleanly when the native extension is stale (``load_built_pack_native``
absent). Rebuild with ``pip install -e . --no-deps --no-build-isolation``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from agri_core.pack import load_knowledge_set, read_pack_bytes
from agri_core.pack.knowledge_set import RustKnowledgeSet
from agri_core.pack.sqlite_schema import write_built_pack
from agri_core.registry import meta

pytestmark = pytest.mark.contract

_REPO = Path(__file__).resolve().parents[2]
_SRC = _REPO / "src" / "agri_core" / "_samples" / "sample_pack"

try:
    from agri_core import _native as _native_mod

    _NATIVE_HAS_LOAD = hasattr(_native_mod, "load_built_pack_native")
except ImportError:
    _native_mod = None  # type: ignore[assignment]
    _NATIVE_HAS_LOAD = False

_SKIP_NATIVE = pytest.mark.skipif(
    not _NATIVE_HAS_LOAD,
    reason="native load_built_pack_native not exported (rebuild with maturin)",
)


def _build_sample(tmp_path: Path) -> Path:
    files = read_pack_bytes(_SRC)
    out = tmp_path / "built"
    write_built_pack(files, out_dir=out)
    return out


def _make_rust_set(built: Path) -> RustKnowledgeSet:
    py = load_knowledge_set(built, allow_synthetic=True)
    manifest = py.manifest
    assert _native_mod is not None
    native = _native_mod.load_built_pack_native(
        str(built / "pack.sqlite"),
        manifest.model_dump(mode="json"),
        None,
        py.dictionary.version,
        10 * 1024 * 1024,
    )
    return RustKnowledgeSet(native, manifest=manifest, dictionary=py.dictionary)


def _dump(rows: Any) -> list[dict[str, Any]]:
    return [r.model_dump(mode="json") for r in rows]


# ---- properties ----------------------------------------------------------


@_SKIP_NATIVE
def test_properties_match(tmp_path: Path) -> None:
    built = _build_sample(tmp_path)
    py = load_knowledge_set(built, allow_synthetic=True)
    rs = _make_rust_set(built)
    assert rs.pack_hash == py.pack_hash
    assert rs.artifact_sha256 == py.manifest.artifact_sha256
    assert rs.dictionary_version == py.dictionary_version
    assert rs.verified == py.verified
    assert rs.manifest.model_dump() == py.manifest.model_dump()
    assert rs.dictionary.version == py.dictionary.version


# ---- iterators -----------------------------------------------------------


@_SKIP_NATIVE
def test_iterators_match(tmp_path: Path) -> None:
    built = _build_sample(tmp_path)
    py = load_knowledge_set(built, allow_synthetic=True)
    rs = _make_rust_set(built)
    assert sorted(_dump(rs.taxa()), key=lambda d: d["taxon_id"]) == sorted(
        _dump(py.taxa()), key=lambda d: d["taxon_id"]
    )
    assert sorted(_dump(rs.facts()), key=lambda d: d["fact_id"]) == sorted(
        _dump(py.facts()), key=lambda d: d["fact_id"]
    )
    assert sorted(_dump(rs.names()), key=lambda d: (d["taxon_id"], d["name"])) == sorted(
        _dump(py.names()), key=lambda d: (d["taxon_id"], d["name"])
    )
    assert sorted(_dump(rs.hazards()), key=lambda d: (d["taxon_id"], d["hazard_code"])) == sorted(
        _dump(py.hazards()), key=lambda d: (d["taxon_id"], d["hazard_code"])
    )


# ---- per-item lookups ----------------------------------------------------


@_SKIP_NATIVE
def test_lookups_match(tmp_path: Path) -> None:
    built = _build_sample(tmp_path)
    py = load_knowledge_set(built, allow_synthetic=True)
    rs = _make_rust_set(built)
    for t in py.taxa():
        assert rs.taxon(t.taxon_id).model_dump(mode="json") == t.model_dump(mode="json")


@_SKIP_NATIVE
def test_lookups_raise_on_missing(tmp_path: Path) -> None:
    built = _build_sample(tmp_path)
    rs = _make_rust_set(built)
    with pytest.raises(KeyError):
        rs.taxon("T-NOPE")
    with pytest.raises(KeyError):
        rs.source("S-NOPE")
    with pytest.raises(KeyError):
        rs.dataset("D-NOPE")


# ---- per-taxon -----------------------------------------------------------


@_SKIP_NATIVE
def test_per_taxon_matches(tmp_path: Path) -> None:
    built = _build_sample(tmp_path)
    py = load_knowledge_set(built, allow_synthetic=True)
    rs = _make_rust_set(built)
    for t in py.taxa():
        tid = t.taxon_id
        assert sorted(_dump(rs.facts_for(tid)), key=lambda d: d["fact_id"]) == sorted(
            _dump(py.facts_for(tid)), key=lambda d: d["fact_id"]
        )
        assert sorted(_dump(rs.names_for(tid)), key=lambda d: d["name"]) == sorted(
            _dump(py.names_for(tid)), key=lambda d: d["name"]
        )
        assert sorted(_dump(rs.hazards_for(tid)), key=lambda d: d["hazard_code"]) == sorted(
            _dump(py.hazards_for(tid)), key=lambda d: d["hazard_code"]
        )
    with pytest.raises(KeyError):
        rs.facts_for("T-NOPE")
    with pytest.raises(KeyError):
        rs.names_for("T-NOPE")
    with pytest.raises(KeyError):
        rs.hazards_for("T-NOPE")


@_SKIP_NATIVE
def test_facts_for_with_parameter(tmp_path: Path) -> None:
    built = _build_sample(tmp_path)
    py = load_knowledge_set(built, allow_synthetic=True)
    rs = _make_rust_set(built)
    for t in py.taxa():
        tid = t.taxon_id
        facts = py.facts_for(tid)
        for f in facts[:1]:
            assert sorted(
                _dump(rs.facts_for(tid, f.parameter)),
                key=lambda d: d["fact_id"],
            ) == sorted(
                _dump(py.facts_for(tid, f.parameter)),
                key=lambda d: d["fact_id"],
            )


# ---- ids_lock + names_index ----------------------------------------------


@_SKIP_NATIVE
def test_ids_lock_and_names_index(tmp_path: Path) -> None:
    built = _build_sample(tmp_path)
    py = load_knowledge_set(built, allow_synthetic=True)
    rs = _make_rust_set(built)
    assert rs.ids_lock() == py.ids_lock()
    for t in list(py.taxa())[:3]:
        q = t.scientific_name
        py_hits = [
            dict(
                taxon_id=e.taxon_id,
                name=e.name,
                normalized_name=e.normalized_name,
                language=e.language,
                kind=e.kind,
                preferred=e.preferred,
                matched_via=e.matched_via,
                rank=e.rank,
                scientific_name=e.scientific_name,
            )
            for e in py.names_index(q)
        ]
        rs_hits = [
            dict(
                taxon_id=e.taxon_id,
                name=e.name,
                normalized_name=e.normalized_name,
                language=e.language,
                kind=e.kind,
                preferred=e.preferred,
                matched_via=e.matched_via,
                rank=e.rank,
                scientific_name=e.scientific_name,
            )
            for e in rs.names_index(q)
        ]
        assert rs_hits == py_hits


# ---- loader delegate ------------------------------------------------------


@_SKIP_NATIVE
def test_loader_delegate_produces_rust_set(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    built = _build_sample(tmp_path)
    monkeypatch.setattr("agri_core.pack.loader._NATIVE_LOAD", True)
    result = load_knowledge_set(built, allow_synthetic=True)
    assert isinstance(result, RustKnowledgeSet)


@_SKIP_NATIVE
def test_meta_reports_native_when_flag_on(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    built = _build_sample(tmp_path)
    monkeypatch.setattr("agri_core.pack.loader._NATIVE_LOAD", True)
    ks = load_knowledge_set(built, allow_synthetic=True)
    m = meta(ks)
    assert m.backends["load_knowledge_set"] == "native"


def test_meta_reports_python_when_flag_off(tmp_path: Path) -> None:
    built = _build_sample(tmp_path)
    ks = load_knowledge_set(built, allow_synthetic=True)
    m = meta(ks)
    assert m.backends["load_knowledge_set"] == "python"
