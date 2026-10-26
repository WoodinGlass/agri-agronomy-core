"""SQLiteKnowledgeSet behavior and directory-content loader dispatch."""

from __future__ import annotations

import hashlib
import sqlite3
import tomllib
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from agri_core.pack import (
    InvalidPackError,
    PackHashMismatchError,
    PackSyntheticNotAllowedError,
    UnsupportedSchemaVersionError,
    load_knowledge_set,
    read_pack_bytes,
)
from agri_core.pack.sqlite_schema import SQLITE_SCHEMA_VERSION, write_built_pack

pytestmark = pytest.mark.contract

_SRC = Path(__file__).resolve().parents[2] / "src" / "agri_core" / "_samples" / "sample_pack"


# ---- helpers -----------------------------------------------------------


def _build_sample(tmp_path: Path) -> Path:
    files = read_pack_bytes(_SRC)
    out = tmp_path / "built"
    write_built_pack(files, out_dir=out)
    return out


def _flip_byte(path: Path, offset: int = 100) -> None:
    data = bytearray(path.read_bytes())
    data[offset] ^= 0xFF
    path.write_bytes(bytes(data))


def _update_artifact_sha256(pack_toml: Path, pack_sqlite: Path) -> None:
    actual = "sha256:" + hashlib.sha256(pack_sqlite.read_bytes()).hexdigest()
    new_lines = []
    for ln in pack_toml.read_text(encoding="utf-8").splitlines():
        if ln.startswith("artifact_sha256"):
            new_lines.append(f'artifact_sha256 = "{actual}"')
        else:
            new_lines.append(ln)
    pack_toml.write_text("\n".join(new_lines) + "\n", encoding="utf-8")


def _remove_line(pack_toml: Path, key: str) -> None:
    text = pack_toml.read_text(encoding="utf-8")
    new_lines = [ln for ln in text.splitlines() if not ln.startswith(f"{key} =")]
    pack_toml.write_text("\n".join(new_lines) + "\n", encoding="utf-8")


# ---- Protocol parity: built matches source -----------------------------


def test_built_taxa_matches_source(tmp_path: Path) -> None:
    built = _build_sample(tmp_path)
    src = load_knowledge_set(_SRC, allow_synthetic=True)
    ks = load_knowledge_set(built, allow_synthetic=True)
    assert [t.taxon_id for t in ks.taxa()] == [t.taxon_id for t in src.taxa()]


def test_built_facts_matches_source(tmp_path: Path) -> None:
    built = _build_sample(tmp_path)
    src = load_knowledge_set(_SRC, allow_synthetic=True)
    ks = load_knowledge_set(built, allow_synthetic=True)
    assert [f.fact_id for f in ks.facts()] == [f.fact_id for f in src.facts()]


def test_built_names_matches_source(tmp_path: Path) -> None:
    built = _build_sample(tmp_path)
    src = load_knowledge_set(_SRC, allow_synthetic=True)
    ks = load_knowledge_set(built, allow_synthetic=True)
    src_keys = [(n.taxon_id, n.name, n.language, n.script, n.kind) for n in src.names()]
    built_keys = [(n.taxon_id, n.name, n.language, n.script, n.kind) for n in ks.names()]
    assert built_keys == src_keys


def test_built_hazards_matches_source(tmp_path: Path) -> None:
    built = _build_sample(tmp_path)
    src = load_knowledge_set(_SRC, allow_synthetic=True)
    ks = load_knowledge_set(built, allow_synthetic=True)
    src_keys = [(h.taxon_id, h.hazard_code) for h in src.hazards()]
    built_keys = [(h.taxon_id, h.hazard_code) for h in ks.hazards()]
    assert built_keys == src_keys


def test_built_sources_match(tmp_path: Path) -> None:
    built = _build_sample(tmp_path)
    src = load_knowledge_set(_SRC, allow_synthetic=True)
    ks = load_knowledge_set(built, allow_synthetic=True)
    assert ks.source("S001") == src.source("S001")
    assert ks.source("S002") == src.source("S002")
    assert ks.source("S003") == src.source("S003")


def test_built_datasets_match(tmp_path: Path) -> None:
    built = _build_sample(tmp_path)
    src = load_knowledge_set(_SRC, allow_synthetic=True)
    ks = load_knowledge_set(built, allow_synthetic=True)
    assert ks.dataset("D000000001") == src.dataset("D000000001")


# ---- Lookup semantics --------------------------------------------------


def test_built_taxon_unknown_raises_keyerror(tmp_path: Path) -> None:
    built = _build_sample(tmp_path)
    ks = load_knowledge_set(built, allow_synthetic=True)
    with pytest.raises(KeyError):
        ks.taxon("T999999999")


def test_built_facts_for_unknown_raises_keyerror(tmp_path: Path) -> None:
    built = _build_sample(tmp_path)
    ks = load_knowledge_set(built, allow_synthetic=True)
    with pytest.raises(KeyError):
        ks.facts_for("T999999999")


def test_built_facts_for_known_no_facts_returns_empty(tmp_path: Path) -> None:
    # T000000005 (fungal) has no facts file in the sample pack
    built = _build_sample(tmp_path)
    ks = load_knowledge_set(built, allow_synthetic=True)
    assert ks.facts_for("T000000005") == ()


def test_built_source_unknown_raises_keyerror(tmp_path: Path) -> None:
    built = _build_sample(tmp_path)
    ks = load_knowledge_set(built, allow_synthetic=True)
    with pytest.raises(KeyError):
        ks.source("S999")


def test_built_dataset_unknown_raises_keyerror(tmp_path: Path) -> None:
    built = _build_sample(tmp_path)
    ks = load_knowledge_set(built, allow_synthetic=True)
    with pytest.raises(KeyError):
        ks.dataset("D999999999")


# ---- Properties --------------------------------------------------------


def test_built_verified_true(tmp_path: Path) -> None:
    built = _build_sample(tmp_path)
    ks = load_knowledge_set(built, allow_synthetic=True)
    assert ks.verified is True


def test_built_pack_hash_is_content_hash_not_artifact(tmp_path: Path) -> None:
    built = _build_sample(tmp_path)
    ks = load_knowledge_set(built, allow_synthetic=True)
    assert ks.pack_hash == ks.manifest.content_hash
    assert ks.pack_hash != ks.manifest.artifact_sha256


def test_built_manifest_fields_match_source(tmp_path: Path) -> None:
    built = _build_sample(tmp_path)
    src = load_knowledge_set(_SRC, allow_synthetic=True)
    ks = load_knowledge_set(built, allow_synthetic=True)
    assert ks.manifest.name == src.manifest.name
    assert ks.manifest.version == src.manifest.version
    assert ks.manifest.content_hash == src.manifest.content_hash
    assert ks.manifest.artifact_sha256 is not None
    assert ks.manifest.sqlite_schema_version == SQLITE_SCHEMA_VERSION
    assert ks.manifest.built_by is not None


# ---- Detection ---------------------------------------------------------


def test_load_rejects_both_sqlite_and_csv(tmp_path: Path) -> None:
    built = _build_sample(tmp_path)
    (built / "taxa.csv").write_bytes((_SRC / "taxa.csv").read_bytes())
    with pytest.raises(InvalidPackError, match="both"):
        load_knowledge_set(built, allow_synthetic=True)


def test_load_rejects_neither(tmp_path: Path) -> None:
    with pytest.raises(InvalidPackError, match="neither"):
        load_knowledge_set(tmp_path, allow_synthetic=True)


# ---- Integrity failures ------------------------------------------------


def test_load_rejects_artifact_sha256_mismatch(tmp_path: Path) -> None:
    built = _build_sample(tmp_path)
    _flip_byte(built / "pack.sqlite", offset=100)
    with pytest.raises(PackHashMismatchError, match="artifact_sha256"):
        load_knowledge_set(built, allow_synthetic=True)


def test_load_rejects_metadata_content_hash_mismatch(tmp_path: Path) -> None:
    built = _build_sample(tmp_path)
    conn = sqlite3.connect(str(built / "pack.sqlite"))
    try:
        conn.execute(
            "UPDATE metadata SET value = ? WHERE key = 'content_hash'",
            ("sha256:" + "0" * 64,),
        )
        conn.commit()
    finally:
        conn.close()
    _update_artifact_sha256(built / "pack.toml", built / "pack.sqlite")
    with pytest.raises(InvalidPackError, match="metadata mismatch"):
        load_knowledge_set(built, allow_synthetic=True)


def test_load_rejects_user_version_mismatch(tmp_path: Path) -> None:
    built = _build_sample(tmp_path)
    conn = sqlite3.connect(str(built / "pack.sqlite"))
    try:
        conn.execute("PRAGMA user_version = 999")
        conn.commit()
    finally:
        conn.close()
    _update_artifact_sha256(built / "pack.toml", built / "pack.sqlite")
    with pytest.raises(InvalidPackError, match="user_version"):
        load_knowledge_set(built, allow_synthetic=True)


def test_load_rejects_source_manifest_in_built_dir(tmp_path: Path) -> None:
    built = _build_sample(tmp_path)
    (built / "pack.toml").write_bytes((_SRC / "pack.toml").read_bytes())
    with pytest.raises(InvalidPackError, match="must declare"):
        load_knowledge_set(built, allow_synthetic=True)


# ---- Hash / gates ------------------------------------------------------


def test_load_built_expected_hash_compares_artifact(tmp_path: Path) -> None:
    built = _build_sample(tmp_path)
    manifest = tomllib.loads((built / "pack.toml").read_text(encoding="utf-8"))
    artifact = manifest["artifact_sha256"]
    content = manifest["content_hash"]

    ks = load_knowledge_set(built, allow_synthetic=True, expected_hash=artifact)
    assert ks.verified is True

    with pytest.raises(PackHashMismatchError, match="expected_hash"):
        load_knowledge_set(built, allow_synthetic=True, expected_hash=content)


def test_load_built_synthetic_gate(tmp_path: Path) -> None:
    built = _build_sample(tmp_path)
    with pytest.raises(PackSyntheticNotAllowedError):
        load_knowledge_set(built)


# ---- Concurrency -------------------------------------------------------


def test_built_concurrent_reads_identical(tmp_path: Path) -> None:
    built = _build_sample(tmp_path)
    ks = load_knowledge_set(built, allow_synthetic=True)

    def snapshot(_i: int) -> tuple[str, ...]:
        return tuple(f.fact_id for f in ks.facts_for("T000000001"))

    with ThreadPoolExecutor(max_workers=8) as ex:
        results = list(ex.map(snapshot, range(20)))
    first = results[0]
    for r in results[1:]:
        assert r == first


# ---- Extra coverage ----------------------------------------------------


def test_load_rejects_unsupported_sqlite_schema_version(tmp_path: Path) -> None:
    built = _build_sample(tmp_path)
    new_lines = []
    for ln in (built / "pack.toml").read_text(encoding="utf-8").splitlines():
        if ln.startswith("sqlite_schema_version"):
            new_lines.append("sqlite_schema_version = 999")
        else:
            new_lines.append(ln)
    (built / "pack.toml").write_text("\n".join(new_lines) + "\n", encoding="utf-8")
    with pytest.raises(UnsupportedSchemaVersionError):
        load_knowledge_set(built, allow_synthetic=True)


def test_load_rejects_built_pack_missing_content_hash(tmp_path: Path) -> None:
    built = _build_sample(tmp_path)
    _remove_line(built / "pack.toml", "content_hash")
    with pytest.raises(InvalidPackError, match="must declare content_hash"):
        load_knowledge_set(built, allow_synthetic=True)
