"""load_knowledge_set + load_knowledge_set_from_files behavior."""

from __future__ import annotations

import shutil
from datetime import date
from pathlib import Path

import pytest

from agri_core.models.dictionary import Dictionary
from agri_core.pack import (
    TABLES,
    EngineTooOldError,
    InvalidPackError,
    PackDictionaryIncompatibleError,
    PackDuplicateKeyError,
    PackEnumInvalidError,
    PackFeatureUnsupportedError,
    PackFKViolationError,
    PackHashMismatchError,
    PackNotFoundError,
    PackPhaseInvalidError,
    PackSafetyViolationError,
    PackScopeInvalidError,
    PackShapeMismatchError,
    PackSyntheticNotAllowedError,
    PackTableInvalidError,
    PackUnitMismatchError,
    PackUnknownParameterError,
    PackValueOutOfRangeError,
    UnsupportedSchemaVersionError,
    compute_pack_hash,
    load_knowledge_set,
    load_knowledge_set_from_files,
    read_pack_bytes,
    write_table,
)

pytestmark = pytest.mark.contract

_REPO = Path(__file__).resolve().parents[2]
_DICT_PATH = _REPO / "dictionary" / "parameters.core.yaml"
_SAMPLE = _REPO / "src" / "agri_core" / "_samples" / "sample_pack"
_DICT = Dictionary.load(_DICT_PATH)

_DEFAULT_TOML = (
    'name = "test"\n'
    'version = "1.0.0"\n'
    "schema_version = 1\n"
    'engine_min = "0.0.0"\n'
    'dictionary_min = "1.0.0"\n'
)


# ---- fixtures ----------------------------------------------------------


def _taxon(
    tid: str = "T000000001", archetype: str = "annual", organism_group: str = "vascular_plant"
) -> dict:
    return {
        "taxon_id": tid,
        "rank": "species",
        "scientific_name": "Testus",
        "accepted_name": None,
        "organism_group": organism_group,
        "archetype": archetype,
        "uses": ["vegetable"],
        "traits": [],
        "parent_id": None,
        "external_ids": None,
        "src": ["S001"],
        "dataset_id": None,
    }


def _source(sid: str = "S001") -> dict:
    return {
        "id": sid,
        "url": f"https://example.org/{sid}",
        "license": "CC0-1.0",
        "commercial_use": "yes",
        "access_date": date(2026, 1, 1),
        "citation": f"Source {sid}",
    }


def _fact(
    fid: str = "F00000000001",
    tid: str = "T000000001",
    parameter: str = "gdd_base",
    phase: str | None = None,
    value: dict | None = None,
    scope: dict | None = None,
    src: list[str] | None = None,
    status: str = "approved",
) -> dict:
    if value is None:
        value = {"shape": "scalar", "unit": "degree_Celsius", "value": 10.0}
    reviewed = status in ("reviewed", "approved")
    return {
        "fact_id": fid,
        "taxon_id": tid,
        "parameter": parameter,
        "phase": phase,
        "value": value,
        "scope": scope or {},
        "provenance_kind": "curated",
        "src": src or ["S001"],
        "dataset_id": None,
        "locator": "table 1",
        "evidence": "A",
        "status": status,
        "reviewed_by": "r" if reviewed else None,
        "reviewed_at": date(2026, 1, 1) if reviewed else None,
        "superseded_by": None,
    }


def _write_pack(
    root: Path,
    *,
    taxa: list[dict] | None = None,
    names: list[dict] | None = None,
    facts: list[dict] | None = None,
    hazards: list[dict] | None = None,
    datasets: list[dict] | None = None,
    sources: list[dict] | None = None,
    advisories: bytes | None = None,
    toml_override: str | None = None,
    with_hash: bool = False,
) -> None:
    root.mkdir(parents=True, exist_ok=True)
    toml = toml_override if toml_override is not None else _DEFAULT_TOML
    (root / "pack.toml").write_text(toml, encoding="utf-8")

    for name, rows in (
        ("taxa", taxa or []),
        ("names", names or []),
        ("hazards", hazards or []),
        ("datasets", datasets or []),
        ("sources", sources or []),
    ):
        spec = TABLES[name]
        assert spec.filename is not None
        (root / spec.filename).write_bytes(write_table(spec, rows))

    facts = facts or []
    if facts:
        by_taxon: dict[str, list[dict]] = {}
        for f in facts:
            by_taxon.setdefault(f["taxon_id"], []).append(f)
        facts_dir = root / "facts"
        facts_dir.mkdir(exist_ok=True)
        for tid, rows in by_taxon.items():
            (facts_dir / f"{tid}.csv").write_bytes(write_table(TABLES["facts"], rows))

    if advisories is not None:
        (root / "advisories.csv").write_bytes(advisories)

    if with_hash:
        digest = compute_pack_hash(root)
        current = (root / "pack.toml").read_text(encoding="utf-8")
        if "content_hash" not in current:
            (root / "pack.toml").write_text(
                current + f'content_hash = "{digest}"\n', encoding="utf-8"
            )


# ---- baseline (3) ------------------------------------------------------


def test_minimal_pack_loads(tmp_path: Path) -> None:
    _write_pack(tmp_path)
    ks = load_knowledge_set(tmp_path, dictionary=_DICT)
    assert list(ks.taxa()) == []
    assert list(ks.facts()) == []
    assert ks.verified is False


def test_sample_pack_loads_allow_synthetic() -> None:
    ks = load_knowledge_set(_SAMPLE, allow_synthetic=True, dictionary=_DICT)
    assert len(list(ks.taxa())) == 8
    assert ks.manifest.synthetic is True
    assert ks.verified is True


def test_sample_pack_without_allow_raises() -> None:
    with pytest.raises(PackSyntheticNotAllowedError):
        load_knowledge_set(_SAMPLE, dictionary=_DICT)


# ---- loading errors (6) ------------------------------------------------


def test_not_found_raises(tmp_path: Path) -> None:
    with pytest.raises(PackNotFoundError):
        load_knowledge_set(tmp_path / "nope", dictionary=_DICT)


def test_not_a_directory_raises(tmp_path: Path) -> None:
    f = tmp_path / "file.txt"
    f.write_text("x", encoding="utf-8")
    with pytest.raises(InvalidPackError):
        load_knowledge_set(f, dictionary=_DICT)


def test_invalid_toml_raises(tmp_path: Path) -> None:
    _write_pack(tmp_path, toml_override="= bad =")
    with pytest.raises(InvalidPackError):
        load_knowledge_set(tmp_path, dictionary=_DICT)


def test_missing_dictionary_min_raises(tmp_path: Path) -> None:
    _write_pack(
        tmp_path,
        toml_override=(
            'name = "test"\nversion = "1.0.0"\nschema_version = 1\nengine_min = "0.0.0"\n'
        ),
    )
    with pytest.raises(InvalidPackError, match="dictionary_min"):
        load_knowledge_set(tmp_path, dictionary=_DICT)


def test_schema_unsupported_raises(tmp_path: Path) -> None:
    _write_pack(
        tmp_path,
        toml_override=(
            'name = "test"\n'
            'version = "1.0.0"\n'
            "schema_version = 999\n"
            'engine_min = "0.0.0"\n'
            'dictionary_min = "1.0.0"\n'
        ),
    )
    with pytest.raises(UnsupportedSchemaVersionError):
        load_knowledge_set(tmp_path, dictionary=_DICT)


def test_engine_too_old_raises(tmp_path: Path) -> None:
    _write_pack(
        tmp_path,
        toml_override=(
            'name = "test"\n'
            'version = "1.0.0"\n'
            "schema_version = 1\n"
            'engine_min = "99.0.0"\n'
            'dictionary_min = "1.0.0"\n'
        ),
    )
    with pytest.raises(EngineTooOldError):
        load_knowledge_set(tmp_path, dictionary=_DICT)


# ---- hash (3) ----------------------------------------------------------


def test_hash_mismatch_raises(tmp_path: Path) -> None:
    _write_pack(
        tmp_path,
        taxa=[_taxon()],
        sources=[_source()],
        facts=[_fact()],
        with_hash=True,
    )
    # tamper: replace sources.csv with a superset row, hash stale
    (tmp_path / "sources.csv").write_bytes(
        write_table(TABLES["sources"], [_source(), _source("S002")])
    )
    with pytest.raises(PackHashMismatchError):
        load_knowledge_set(tmp_path, dictionary=_DICT)


def test_expected_hash_match_verified_true(tmp_path: Path) -> None:
    _write_pack(tmp_path, taxa=[_taxon()], sources=[_source()], facts=[_fact()])
    digest = compute_pack_hash(tmp_path)
    ks = load_knowledge_set(tmp_path, expected_hash=digest, dictionary=_DICT)
    assert ks.verified is True


def test_no_hash_unverified(tmp_path: Path) -> None:
    _write_pack(tmp_path)
    ks = load_knowledge_set(tmp_path, dictionary=_DICT)
    assert ks.verified is False


# ---- dictionary compat (3) ---------------------------------------------


def test_dictionary_major_mismatch_raises(tmp_path: Path) -> None:
    _write_pack(
        tmp_path,
        toml_override=(
            'name = "test"\n'
            'version = "1.0.0"\n'
            "schema_version = 1\n"
            'engine_min = "0.0.0"\n'
            'dictionary_min = "2.0.0"\n'
        ),
    )
    with pytest.raises(PackDictionaryIncompatibleError):
        load_knowledge_set(tmp_path, dictionary=_DICT)


def test_dictionary_minor_newer_raises(tmp_path: Path) -> None:
    _write_pack(
        tmp_path,
        toml_override=(
            'name = "test"\n'
            'version = "1.0.0"\n'
            "schema_version = 1\n"
            'engine_min = "0.0.0"\n'
            'dictionary_min = "1.99.0"\n'
        ),
    )
    with pytest.raises(PackDictionaryIncompatibleError):
        load_knowledge_set(tmp_path, dictionary=_DICT)


def test_dictionary_newer_than_required_ok(tmp_path: Path) -> None:
    _write_pack(tmp_path)  # requires 1.0.0
    fake = _DICT.model_copy(update={"version": "1.5.0"})
    load_knowledge_set(tmp_path, dictionary=fake)  # no raise


# ---- advisories (3 parametrized) ---------------------------------------


@pytest.mark.parametrize(
    ("body", "should_raise"),
    [
        (b"fact_id,reason,replacement_fact_id,issued_at,issued_by\nF01,x,,2026-01-01,r\n", True),
        (b"", False),
        (b"\n\n", False),
    ],
)
def test_advisories_behavior(tmp_path: Path, body: bytes, should_raise: bool) -> None:
    _write_pack(tmp_path, advisories=body)
    if should_raise:
        with pytest.raises(PackFeatureUnsupportedError):
            load_knowledge_set(tmp_path, dictionary=_DICT)
    else:
        load_knowledge_set(tmp_path, dictionary=_DICT)


# ---- FK (4) ------------------------------------------------------------


def test_fk_name_taxon_unknown(tmp_path: Path) -> None:
    _write_pack(
        tmp_path,
        taxa=[_taxon()],
        sources=[_source()],
        names=[
            {
                "taxon_id": "T999999999",
                "name": "Foo",
                "language": "en",
                "script": "Latn",
                "kind": "common",
                "preferred": True,
                "src": ["S001"],
                "dataset_id": None,
            }
        ],
    )
    with pytest.raises(PackFKViolationError, match=r"name\.taxon_id"):
        load_knowledge_set(tmp_path, dictionary=_DICT)


def test_fk_fact_taxon_unknown(tmp_path: Path) -> None:
    _write_pack(
        tmp_path,
        taxa=[_taxon()],
        sources=[_source()],
        facts=[_fact(tid="T999999999")],
    )
    with pytest.raises(PackFKViolationError, match=r"fact\.taxon_id"):
        load_knowledge_set(tmp_path, dictionary=_DICT)


def test_fk_fact_src_unknown(tmp_path: Path) -> None:
    _write_pack(
        tmp_path,
        taxa=[_taxon()],
        sources=[_source()],
        facts=[_fact(src=["S999"])],
    )
    with pytest.raises(PackFKViolationError, match=r"fact\.src"):
        load_knowledge_set(tmp_path, dictionary=_DICT)


def test_fk_parent_unknown(tmp_path: Path) -> None:
    # parent_id is syntactically a TaxonId but references no row.
    # TaxonRow.model_validate accepts it (parent_id != taxon_id);
    # the loader's structural FK check catches it.
    t = _taxon()
    t["parent_id"] = "T999999999"
    _write_pack(tmp_path, taxa=[t], sources=[_source()])
    with pytest.raises(PackFKViolationError, match="parent_id"):
        load_knowledge_set(tmp_path, dictionary=_DICT)


def test_fk_parent_self_raises_table_invalid(tmp_path: Path) -> None:
    # TaxonRow's Pydantic validator rejects parent_id == taxon_id before
    # the loader's structural check runs, so the error is PackTableInvalidError,
    # not PackFKViolationError.
    t = _taxon()
    t["parent_id"] = t["taxon_id"]
    _write_pack(tmp_path, taxa=[t], sources=[_source()])
    with pytest.raises(PackTableInvalidError, match="parent_id"):
        load_knowledge_set(tmp_path, dictionary=_DICT)


# ---- duplicate PK (2) --------------------------------------------------


def test_duplicate_taxon_id(tmp_path: Path) -> None:
    _write_pack(
        tmp_path,
        taxa=[_taxon("T000000001"), _taxon("T000000001")],
        sources=[_source()],
    )
    with pytest.raises(PackDuplicateKeyError, match="taxon_id"):
        load_knowledge_set(tmp_path, dictionary=_DICT)


def test_duplicate_fact_id(tmp_path: Path) -> None:
    _write_pack(
        tmp_path,
        taxa=[_taxon()],
        sources=[_source()],
        facts=[_fact("F00000000001"), _fact("F00000000001")],
    )
    with pytest.raises(PackDuplicateKeyError, match="fact_id"):
        load_knowledge_set(tmp_path, dictionary=_DICT)


# ---- facts-file internal consistency (1) -------------------------------


def test_facts_file_taxon_id_mismatch(tmp_path: Path) -> None:
    _write_pack(
        tmp_path,
        taxa=[_taxon("T000000001"), _taxon("T000000002")],
        sources=[_source()],
    )
    # write facts/T000000001.csv but with a row that references T000000002
    facts_dir = tmp_path / "facts"
    facts_dir.mkdir()
    (facts_dir / "T000000001.csv").write_bytes(
        write_table(TABLES["facts"], [_fact(tid="T000000002")])
    )
    with pytest.raises(PackFKViolationError, match="taxon_id"):
        load_knowledge_set(tmp_path, dictionary=_DICT)


# ---- dictionary (4) ----------------------------------------------------


def test_unknown_parameter(tmp_path: Path) -> None:
    _write_pack(
        tmp_path,
        taxa=[_taxon()],
        sources=[_source()],
        facts=[_fact(parameter="unknown_param")],
    )
    with pytest.raises(PackUnknownParameterError):
        load_knowledge_set(tmp_path, dictionary=_DICT)


def test_shape_mismatch(tmp_path: Path) -> None:
    _write_pack(
        tmp_path,
        taxa=[_taxon()],
        sources=[_source()],
        facts=[
            _fact(
                parameter="soil_ph",
                value={"shape": "scalar", "unit": "pH", "value": 7.0},
            )
        ],
    )
    with pytest.raises(PackShapeMismatchError):
        load_knowledge_set(tmp_path, dictionary=_DICT)


def test_phase_invalid(tmp_path: Path) -> None:
    _write_pack(
        tmp_path,
        taxa=[_taxon()],
        sources=[_source()],
        facts=[
            _fact(
                parameter="kc",
                phase="bogus",
                value={"shape": "scalar", "unit": "dimensionless", "value": 0.8},
            )
        ],
    )
    with pytest.raises(PackPhaseInvalidError):
        load_knowledge_set(tmp_path, dictionary=_DICT)


def test_scope_key_invalid(tmp_path: Path) -> None:
    _write_pack(
        tmp_path,
        taxa=[_taxon()],
        sources=[_source()],
        facts=[_fact(scope={"yield_target": "high"})],
    )
    with pytest.raises(PackScopeInvalidError):
        load_knowledge_set(tmp_path, dictionary=_DICT)


# ---- value checks (4) --------------------------------------------------


def test_value_out_of_range_scalar(tmp_path: Path) -> None:
    _write_pack(
        tmp_path,
        taxa=[_taxon()],
        sources=[_source()],
        facts=[_fact(value={"shape": "scalar", "unit": "degree_Celsius", "value": 999.0})],
    )
    with pytest.raises(PackValueOutOfRangeError):
        load_knowledge_set(tmp_path, dictionary=_DICT)


def test_enum_invalid(tmp_path: Path) -> None:
    _write_pack(
        tmp_path,
        taxa=[_taxon()],
        sources=[_source()],
        facts=[
            _fact(
                parameter="managed_cycle",
                value={"shape": "enum", "value": "never"},
            )
        ],
    )
    with pytest.raises(PackEnumInvalidError):
        load_knowledge_set(tmp_path, dictionary=_DICT)


def test_unit_mismatch(tmp_path: Path) -> None:
    _write_pack(
        tmp_path,
        taxa=[_taxon()],
        sources=[_source()],
        facts=[_fact(value={"shape": "scalar", "unit": "kelvin", "value": 10.0})],
    )
    with pytest.raises(PackUnitMismatchError):
        load_knowledge_set(tmp_path, dictionary=_DICT)


def test_safety_violation(tmp_path: Path) -> None:
    _write_pack(
        tmp_path,
        taxa=[_taxon()],
        sources=[_source()],
        facts=[
            _fact(
                parameter="n_max_per_application",
                value={"shape": "scalar", "unit": "kilogram/hectare", "value": 100.0},
                status="draft",
            )
        ],
    )
    with pytest.raises(PackSafetyViolationError):
        load_knowledge_set(tmp_path, dictionary=_DICT)


# ---- CRITICAL: unknown-shape skips value checks -----------------------


def test_unknown_shape_skips_value_checks(tmp_path: Path) -> None:
    _write_pack(
        tmp_path,
        taxa=[_taxon()],
        sources=[_source()],
        facts=[
            _fact(
                parameter="water_temp_max",
                value={"shape": "unknown", "reason": "not recorded"},
            )
        ],
    )
    # water_temp_max has unit=degree_Celsius and physical_range=[0,50].
    # An unknown-shape fact must NOT trigger unit/range/enum checks.
    ks = load_knowledge_set(tmp_path, dictionary=_DICT)
    assert len(list(ks.facts())) == 1


# ---- aggregation (2) ---------------------------------------------------


def test_findings_max_20(tmp_path: Path) -> None:
    facts = [_fact(fid=f"F{i:011d}", tid="T999999999") for i in range(25)]
    _write_pack(tmp_path, taxa=[_taxon()], sources=[_source()], facts=facts)
    with pytest.raises(PackFKViolationError) as exc_info:
        load_knowledge_set(tmp_path, dictionary=_DICT)
    assert len(exc_info.value.findings) <= 20
    assert len(exc_info.value.findings) >= 1


def test_first_finding_type_preserved(tmp_path: Path) -> None:
    _write_pack(
        tmp_path,
        taxa=[_taxon()],
        sources=[_source()],
        facts=[_fact(parameter="unknown_param")],
    )
    with pytest.raises(PackUnknownParameterError):
        load_knowledge_set(tmp_path, dictionary=_DICT)


# ---- determinism (1) ---------------------------------------------------


def test_deterministic_across_loads(tmp_path: Path) -> None:
    _write_pack(
        tmp_path,
        taxa=[_taxon(), _taxon("T000000002")],
        sources=[_source()],
        facts=[_fact(), _fact("F00000000002", "T000000002")],
    )
    ks1 = load_knowledge_set(tmp_path, dictionary=_DICT)
    ks2 = load_knowledge_set(tmp_path, dictionary=_DICT)
    assert [t.taxon_id for t in ks1.taxa()] == [t.taxon_id for t in ks2.taxa()]
    assert [f.fact_id for f in ks1.facts()] == [f.fact_id for f in ks2.facts()]


# ---- from_files API (2) ------------------------------------------------


def test_from_files_equivalent(tmp_path: Path) -> None:
    _write_pack(
        tmp_path,
        taxa=[_taxon()],
        sources=[_source()],
        facts=[_fact()],
    )
    files = read_pack_bytes(tmp_path)
    ks_a = load_knowledge_set(tmp_path, dictionary=_DICT)
    ks_b = load_knowledge_set_from_files(files, dictionary=_DICT)
    assert [t.taxon_id for t in ks_a.taxa()] == [t.taxon_id for t in ks_b.taxa()]
    assert [f.fact_id for f in ks_a.facts()] == [f.fact_id for f in ks_b.facts()]


def test_from_files_no_disk_read(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _write_pack(
        tmp_path,
        taxa=[_taxon()],
        sources=[_source()],
        facts=[_fact()],
    )
    files = read_pack_bytes(tmp_path)

    def boom(*args, **kwargs):
        raise AssertionError("from_files touched disk")

    monkeypatch.setattr(Path, "read_bytes", boom)
    monkeypatch.setattr(Path, "read_text", boom)
    ks = load_knowledge_set_from_files(files, dictionary=_DICT)
    assert [t.taxon_id for t in ks.taxa()] == ["T000000001"]


# ---- ported from test_pack_loader.py and test_pack_hash.py -------------


def test_missing_pack_toml_raises(tmp_path: Path) -> None:
    _write_pack(tmp_path)
    (tmp_path / "pack.toml").unlink()
    with pytest.raises(InvalidPackError, match=r"pack\.toml"):
        load_knowledge_set(tmp_path, dictionary=_DICT)


def test_missing_sources_raises(tmp_path: Path) -> None:
    _write_pack(tmp_path)
    (tmp_path / "sources.csv").unlink()
    with pytest.raises(InvalidPackError, match=r"sources\.csv"):
        load_knowledge_set(tmp_path, dictionary=_DICT)


def test_invalid_manifest_fields_raises(tmp_path: Path) -> None:
    _write_pack(
        tmp_path,
        toml_override=(
            'name = "UPPER"\n'
            'version = "1.0.0"\n'
            "schema_version = 1\n"
            'engine_min = "0.0.0"\n'
            'dictionary_min = "1.0.0"\n'
        ),
    )
    with pytest.raises(InvalidPackError):
        load_knowledge_set(tmp_path, dictionary=_DICT)


def test_invalid_manifest_version_raises(tmp_path: Path) -> None:
    _write_pack(
        tmp_path,
        toml_override=(
            'name = "test"\n'
            'version = "1.0"\n'
            "schema_version = 1\n"
            'engine_min = "0.0.0"\n'
            'dictionary_min = "1.0.0"\n'
        ),
    )
    with pytest.raises(InvalidPackError):
        load_knowledge_set(tmp_path, dictionary=_DICT)


def test_sample_pack_tampered_raises(tmp_path: Path) -> None:
    tampered = tmp_path / "tampered"
    shutil.copytree(_SAMPLE, tampered)
    sources = tampered / "sources.csv"
    sources.write_bytes(sources.read_bytes() + b"S999,x,CC0-1.0,yes,2026-01-01,x\n")
    with pytest.raises(PackHashMismatchError):
        load_knowledge_set(tampered, allow_synthetic=True, dictionary=_DICT)
