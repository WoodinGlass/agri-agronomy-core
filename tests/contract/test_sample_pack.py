"""Sample pack data hygiene and coverage."""

from __future__ import annotations

import re
import subprocess
import tomllib
from importlib.resources import files as _resource_files
from pathlib import Path
from urllib.parse import urlparse

import pytest

from agri_core.pack import (
    TABLES,
    compute_pack_hash,
    load_knowledge_set,
    read_pack_bytes,
    read_table,
)
from agri_core.pack.errors import PackHashMismatchError

pytestmark = pytest.mark.contract

SAMPLE = Path(str(_resource_files("agri_core") / "_samples" / "sample_pack"))


def _load_table(files, table_name: str):
    spec = TABLES[table_name]
    if spec.filename is None:
        raise ValueError(f"table {table_name!r} has no single filename")
    return read_table(spec, files[spec.filename], source_name=spec.filename)


def _load_facts(files) -> dict[str, list[dict]]:
    spec = TABLES["facts"]
    out: dict[str, list[dict]] = {}
    for key, data in files.items():
        if not key.startswith("facts/"):
            continue
        tid = key[len("facts/") : -len(".csv")]
        table = read_table(spec, data, source_name=key)
        out[tid] = [dict(r) for r in table.rows]
    return out


def test_sample_pack_has_8_taxa() -> None:
    files = read_pack_bytes(SAMPLE)
    table = _load_table(files, "taxa")
    assert len(table.rows) == 8


def test_sample_pack_covers_8_archetypes() -> None:
    files = read_pack_bytes(SAMPLE)
    table = _load_table(files, "taxa")
    archetypes = {dict(r)["archetype"] for r in table.rows}
    assert archetypes == {
        "annual",
        "aquatic",
        "biennial",
        "epiphyte",
        "fungal",
        "geophyte",
        "herbaceous_perennial",
        "woody_perennial",
    }


def test_sample_pack_one_taxon_without_facts() -> None:
    files = read_pack_bytes(SAMPLE)
    facts_by_taxon = _load_facts(files)
    taxa_with_facts = {tid for tid, rows in facts_by_taxon.items() if rows}
    taxa_table = _load_table(files, "taxa")
    all_ids = {dict(r)["taxon_id"] for r in taxa_table.rows}
    assert all_ids - taxa_with_facts == {"T000000005"}


def test_sample_pack_byte_hygiene() -> None:
    files = read_pack_bytes(SAMPLE)
    for relpath, raw in files.items():
        assert b"\r" not in raw, f"{relpath} contains CR"
        assert not raw.startswith(b"\xef\xbb\xbf"), f"{relpath} has BOM"
        raw.decode("utf-8")  # raises if invalid


def test_sample_pack_hash_valid() -> None:
    manifest_dict = tomllib.loads((SAMPLE / "pack.toml").read_text(encoding="utf-8"))
    expected = manifest_dict["content_hash"]
    assert expected.startswith("sha256:")
    assert compute_pack_hash(SAMPLE) == expected


def test_sample_pack_sources_example_org() -> None:
    files = read_pack_bytes(SAMPLE)
    table = _load_table(files, "sources")
    for r in table.rows:
        assert urlparse(dict(r)["url"]).hostname == "example.org"


def test_sample_pack_all_sources_used() -> None:
    files = read_pack_bytes(SAMPLE)
    facts_by_taxon = _load_facts(files)
    hazards_table = _load_table(files, "hazards")
    used: set[str] = set()
    for rows in facts_by_taxon.values():
        for r in rows:
            src = r.get("src") or []
            used.update(src)
    for r in hazards_table.rows:
        src = dict(r).get("src") or []
        used.update(src)
    assert used >= {"S001", "S002", "S003"}


def test_sample_pack_names_multilanguage() -> None:
    files = read_pack_bytes(SAMPLE)
    table = _load_table(files, "names")
    langs = {dict(r)["language"] for r in table.rows}
    assert len(langs) >= 2
    assert "ja" in langs


def test_sample_pack_names_non_ascii_parsed() -> None:
    files = read_pack_bytes(SAMPLE)
    table = _load_table(files, "names")
    names = {dict(r)["name"] for r in table.rows}
    assert "\u30c6\u30b9\u30c8\u4e00\u5e74\u8349" in names


def test_sample_pack_names_comma_quote_parsed() -> None:
    files = read_pack_bytes(SAMPLE)
    table = _load_table(files, "names")
    names = {dict(r)["name"] for r in table.rows}
    assert 'Test\'s "annual", test' in names


def test_sample_pack_manifest_flags() -> None:
    manifest = tomllib.loads((SAMPLE / "pack.toml").read_text(encoding="utf-8"))
    assert manifest["dictionary_min"] == "1.0.0"
    assert manifest["synthetic"] is True


def test_sample_pack_fact_ids_unique() -> None:
    files = read_pack_bytes(SAMPLE)
    facts_by_taxon = _load_facts(files)
    all_ids: list[str] = []
    for rows in facts_by_taxon.values():
        all_ids.extend(r["fact_id"] for r in rows)
    assert len(all_ids) == len(set(all_ids))
    pat = re.compile(r"^F[0-9A-HJKMNP-TV-Z]{11,}$")
    for fid in all_ids:
        assert pat.match(fid), f"bad fact_id {fid!r}"


def test_sample_pack_fact_filename_matches_taxon() -> None:
    files = read_pack_bytes(SAMPLE)
    facts_by_taxon = _load_facts(files)
    for tid, rows in facts_by_taxon.items():
        for r in rows:
            assert r["taxon_id"] == tid, (
                f"fact {r['fact_id']} in facts/{tid}.csv has taxon_id={r['taxon_id']!r}"
            )


def test_sample_pack_shape_coverage() -> None:
    files = read_pack_bytes(SAMPLE)
    facts_by_taxon = _load_facts(files)
    shapes: set[str] = set()
    for rows in facts_by_taxon.values():
        for r in rows:
            v = r["value"]
            shapes.add(v["shape"])
    expected = {"scalar", "range", "trapezoid", "enum", "enum_set", "unknown"}
    assert shapes == expected, f"missing={expected - shapes} extra={shapes - expected}"


# Expected content_hash of the sample pack at this commit. If a change
# to the sample pack data or format is intentional, update the literal
# here. This is a known-answer test: it does not re-derive the value,
# it pins it.
SAMPLE_PACK_CONTENT_HASH = "sha256:fc435d26c4e4f5550bd2b05e99ea1da2d1ab33eff63be69e6ba3bf0c9470d2cb"


def test_sample_pack_content_hash_kat() -> None:
    """Known-Answer Test: pin the sample pack content_hash.

    A failure means either the sample pack changed (data or format) or
    the hash algorithm changed. In both cases, review the diff before
    updating the constant. Do not re-derive the expected value; that
    would defeat the point of a KAT.
    """
    manifest = tomllib.loads((SAMPLE / "pack.toml").read_text(encoding="utf-8"))
    assert manifest["content_hash"] == SAMPLE_PACK_CONTENT_HASH
    assert compute_pack_hash(SAMPLE) == SAMPLE_PACK_CONTENT_HASH


def test_load_source_equals_load_built(tmp_path: Path) -> None:
    """`load(source)` and `load(build(source))` expose the same data.

    Catches build-time data loss: dropped rows, changed types,
    reordered lists. The `pack_hash` (content_hash) is preserved
    through the build; the `artifact_sha256` differs by design.
    """
    built = tmp_path / "built"
    built.mkdir()
    r = subprocess.run(
        ["agri-core", "pack", "build", "--pack", str(SAMPLE), "--out", str(built)],
        capture_output=True,
        text=True,
        timeout=120,
    )
    if r.returncode != 0:
        pytest.fail(f"agri-core pack build failed: {r.stderr[-1000:]}")

    ks_src = load_knowledge_set(SAMPLE, allow_synthetic=True)
    ks_built = load_knowledge_set(built, allow_synthetic=True)

    # Same content_hash (portable data hash, preserved into the built pack)
    assert ks_src.pack_hash == ks_built.pack_hash

    # Same data, row-for-row
    assert list(ks_src.taxa()) == list(ks_built.taxa())
    assert list(ks_src.names()) == list(ks_built.names())
    assert list(ks_src.facts()) == list(ks_built.facts())
    assert list(ks_src.hazards()) == list(ks_built.hazards())


def test_built_pack_tampered_artifact_rejected(tmp_path: Path) -> None:
    """Flipping a byte in pack.sqlite triggers PACK_HASH_MISMATCH.

    The hash is verified before any SQLite connection opens; a
    tampered artifact cannot be queried.
    """
    built = tmp_path / "built"
    built.mkdir()
    r = subprocess.run(
        ["agri-core", "pack", "build", "--pack", str(SAMPLE), "--out", str(built)],
        capture_output=True,
        text=True,
        timeout=120,
    )
    if r.returncode != 0:
        pytest.fail(f"agri-core pack build failed: {r.stderr[-1000:]}")

    sqlite_path = built / "pack.sqlite"
    data = bytearray(sqlite_path.read_bytes())
    data[-1] ^= 0xFF
    sqlite_path.write_bytes(data)

    with pytest.raises(PackHashMismatchError, match="artifact_sha256 mismatch"):
        load_knowledge_set(built, allow_synthetic=True)
