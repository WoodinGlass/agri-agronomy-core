"""Sample pack data hygiene and coverage."""

from __future__ import annotations

import re
import tomllib
from importlib.resources import files as _resource_files
from pathlib import Path

import pytest

from agri_core.pack import TABLES, compute_pack_hash, read_pack_bytes, read_table

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
        assert "example.org" in dict(r)["url"]


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
