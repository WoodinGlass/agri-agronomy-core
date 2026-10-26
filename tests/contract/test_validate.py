"""Validate pack entry point (M6-4)."""

from __future__ import annotations

import re
import shutil
from importlib.resources import files as pkg_files
from pathlib import Path

import pytest

from agri_core.pack import (
    InvalidPackError,
    PackFKViolationError,
    PackHashMismatchError,
    PackSyntheticNotAllowedError,
    PackUnknownParameterError,
    hash_pack_files,
    read_pack_bytes,
)
from agri_core.pack.validate import validate_pack

pytestmark = pytest.mark.contract

_BAD_HASH = "sha256:" + ("0" * 64)


def _sample_source(tmp_path: Path) -> Path:
    src = Path(str(pkg_files("agri_core") / "_samples" / "sample_pack"))
    dst = tmp_path / "src"
    shutil.copytree(src, dst)
    return dst


def _load_files(src: Path) -> dict[str, bytes]:
    return dict(read_pack_bytes(src))


def _strip_hash(src: Path) -> None:
    toml = src / "pack.toml"
    lines = [
        ln
        for ln in toml.read_text(encoding="utf-8").splitlines()
        if not ln.startswith("content_hash")
    ]
    toml.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _break_hash(src: Path) -> None:
    toml = src / "pack.toml"
    text = toml.read_text(encoding="utf-8")
    toml.write_text(
        re.sub(r'content_hash = "[^"]*"', f'content_hash = "{_BAD_HASH}"', text),
        encoding="utf-8",
    )


def test_validate_pack_returns_knowledge_set(tmp_path: Path) -> None:
    src = _sample_source(tmp_path)
    ks = validate_pack(_load_files(src), allow_synthetic=True)
    assert ks.verified is True
    assert ks.manifest.synthetic is True


def test_validate_pack_broken_manifest(tmp_path: Path) -> None:
    src = _sample_source(tmp_path)
    files = _load_files(src)
    files["pack.toml"] = b"garbage = true\n"
    with pytest.raises(InvalidPackError, match=r"pack\.toml|extra|field"):
        validate_pack(files, allow_synthetic=True)


def test_validate_pack_hash_mismatch(tmp_path: Path) -> None:
    src = _sample_source(tmp_path)
    _break_hash(src)
    files = _load_files(src)
    with pytest.raises(PackHashMismatchError, match=r"content_hash"):
        validate_pack(files, allow_synthetic=True)


def test_validate_pack_skips_hash_when_content_hash_stripped(tmp_path: Path) -> None:
    src = _sample_source(tmp_path)
    _strip_hash(src)
    ks = validate_pack(_load_files(src), allow_synthetic=True)
    assert ks.verified is False


def test_validate_pack_fk_violation(tmp_path: Path) -> None:
    src = _sample_source(tmp_path)
    _strip_hash(src)
    facts = src / "facts" / "T000000001.csv"
    with facts.open("a", encoding="utf-8") as fh:
        fh.write(
            'F99999999999,T999999999,soil_ph,,"{""shape"":""scalar"",'
            '""unit"":""pH"",""value"":7.0}","{}",curated,S001,,x,'
            "A,approved,r,2026-01-01,\n"
        )
    with pytest.raises(PackFKViolationError, match=r"T999999999|foreign|taxon"):
        validate_pack(_load_files(src), allow_synthetic=True)


def test_validate_pack_unknown_parameter(tmp_path: Path) -> None:
    src = _sample_source(tmp_path)
    _strip_hash(src)
    facts = src / "facts" / "T000000001.csv"
    with facts.open("a", encoding="utf-8") as fh:
        fh.write(
            'F88888888888,T000000001,not_a_parameter,,"{""shape"":""scalar"",'
            '""unit"":""dimensionless"",""value"":1.0}","{}",curated,S001,,x,'
            "A,approved,r,2026-01-01,\n"
        )
    with pytest.raises(PackUnknownParameterError, match=r"not_a_parameter|unknown"):
        validate_pack(_load_files(src), allow_synthetic=True)


def test_validate_pack_rejects_synthetic_without_flag(tmp_path: Path) -> None:
    src = _sample_source(tmp_path)
    with pytest.raises(PackSyntheticNotAllowedError, match=r"synthetic"):
        validate_pack(_load_files(src), allow_synthetic=False)


def test_validate_pack_idempotent_hash(tmp_path: Path) -> None:
    src = _sample_source(tmp_path)
    files = _load_files(src)
    ks1 = validate_pack(files, allow_synthetic=True)
    ks2 = validate_pack(files, allow_synthetic=True)
    assert ks1.pack_hash == ks2.pack_hash


def test_validate_pack_expected_hash_match(tmp_path: Path) -> None:
    src = _sample_source(tmp_path)
    files = _load_files(src)
    expected = hash_pack_files(files)
    ks = validate_pack(files, allow_synthetic=True, expected_hash=expected)
    assert ks.pack_hash == expected


def test_validate_pack_expected_hash_mismatch(tmp_path: Path) -> None:
    src = _sample_source(tmp_path)
    files = _load_files(src)
    with pytest.raises(PackHashMismatchError, match=r"expected_hash"):
        validate_pack(files, allow_synthetic=True, expected_hash=_BAD_HASH)


def test_validate_pack_refuses_built_manifest_as_source(tmp_path: Path) -> None:
    src = _sample_source(tmp_path)
    toml = src / "pack.toml"
    toml.write_text(
        toml.read_text(encoding="utf-8")
        + 'artifact_sha256 = "sha256:'
        + ("0" * 64)
        + '"\n'
        + "sqlite_schema_version = 1\n"
        + 'built_by = "agri-core 0.1.0"\n',
        encoding="utf-8",
    )
    files = _load_files(src)
    with pytest.raises(InvalidPackError, match=r"build-only fields"):
        validate_pack(files, allow_synthetic=True)
