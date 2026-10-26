"""Pack loader behavior."""

from __future__ import annotations

from pathlib import Path

import pytest

from agri_core.pack import (
    EngineTooOldError,
    InvalidPackError,
    Pack,
    PackNotFoundError,
    UnsupportedSchemaVersionError,
    compute_pack_hash,
    load_pack,
    load_sample_pack,
)
from agri_core.pack.tables import TABLES

pytestmark = pytest.mark.unit

HEADER = b"id,url,license,commercial_use,access_date,citation\n"


_HEADER_BY_TABLE: dict[str, str] = {
    "taxa": "taxon_id,rank,scientific_name,accepted_name,organism_group,"
    "archetype,uses,traits,parent_id,external_ids,src,dataset_id\n",
    "names": "taxon_id,name,language,script,kind,preferred,src,dataset_id\n",
    "hazards": "taxon_id,hazard_code,severity,reason,as_of,authority,src,dataset_id\n",
    "datasets": "dataset_id,name,version,license,checksum,url,locator,access_date\n",
}


def _make_pack(
    tmp_path: Path,
    *,
    name: str = "pack1",
    version: str = "1.0.0",
    schema_version: int = 1,
    engine_min: str = "0.0.0",
    sources: bytes | None = None,
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
    if sources is not None:
        (root / "sources.csv").write_bytes(sources)
        digest = compute_pack_hash(root)
        (root / "pack.toml").write_text(body + f'content_hash = "{digest}"\n', encoding="utf-8")
    return root


def test_load_sample_pack_ok() -> None:
    p = load_sample_pack()
    assert isinstance(p, Pack)
    assert p.kind == "sample"
    assert p.manifest.name == "sample"
    assert p.manifest.version == "0.1.0"
    assert p.sources_csv.is_file()


def test_load_pack_ok(tmp_path: Path) -> None:
    root = _make_pack(tmp_path, sources=HEADER)
    p = load_pack(root)
    assert p.kind == "directory"
    assert p.manifest.name == "pack1"
    assert p.root == root


def test_load_pack_not_found(tmp_path: Path) -> None:
    with pytest.raises(PackNotFoundError):
        load_pack(tmp_path / "nope")


def test_load_pack_missing_manifest(tmp_path: Path) -> None:
    root = tmp_path / "pack"
    root.mkdir()
    (root / "sources.csv").write_bytes(HEADER)
    with pytest.raises(InvalidPackError):
        load_pack(root)


def test_load_pack_bad_toml(tmp_path: Path) -> None:
    root = tmp_path / "pack"
    root.mkdir()
    (root / "pack.toml").write_text("= bad =", encoding="utf-8")
    (root / "sources.csv").write_bytes(HEADER)
    with pytest.raises(InvalidPackError):
        load_pack(root)


def test_load_pack_bad_manifest_fields(tmp_path: Path) -> None:
    root = _make_pack(tmp_path, name="UPPER", sources=HEADER)
    with pytest.raises(InvalidPackError):
        load_pack(root)


def test_load_pack_bad_version(tmp_path: Path) -> None:
    root = _make_pack(tmp_path, version="1.0", sources=HEADER)
    with pytest.raises(InvalidPackError):
        load_pack(root)


def test_load_pack_missing_sources(tmp_path: Path) -> None:
    root = _make_pack(tmp_path)
    with pytest.raises(InvalidPackError):
        load_pack(root)


def test_unsupported_schema_version(tmp_path: Path) -> None:
    root = _make_pack(tmp_path, schema_version=2, sources=HEADER)
    with pytest.raises(UnsupportedSchemaVersionError):
        load_pack(root)


def test_engine_too_old(tmp_path: Path) -> None:
    root = _make_pack(tmp_path, engine_min="99.0.0", sources=HEADER)
    with pytest.raises(EngineTooOldError):
        load_pack(root)
