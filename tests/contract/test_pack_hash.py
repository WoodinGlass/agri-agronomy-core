"""Pack hash algorithm and verification tests."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from agri_core.pack import (
    InvalidPackError,
    PackHashMismatchError,
    PackManifest,
    PackTableInvalidError,
    compute_pack_hash,
    hash_pack_files,
    load_pack,
    load_sample_pack,
    read_pack_bytes,
    verify_pack_hash,
    verify_pack_hash_full,
)

pytestmark = pytest.mark.contract

_HEADERS = {
    "taxa.csv": (
        b"taxon_id,rank,scientific_name,accepted_name,organism_group,"
        b"archetype,uses,traits,parent_id,external_ids,src,dataset_id\n"
    ),
    "names.csv": (b"taxon_id,name,language,script,kind,preferred,src,dataset_id\n"),
    "hazards.csv": (b"taxon_id,hazard_code,severity,reason,as_of,authority,src,dataset_id\n"),
    "datasets.csv": (b"dataset_id,name,version,license,checksum,url,locator,access_date\n"),
    "sources.csv": (b"id,url,license,commercial_use,access_date,citation\n"),
}

_MINIMAL_TOML = b'name = "minimal"\nversion = "1.0.0"\nschema_version = 1\nengine_min = "0.0.0"\n'

# Golden vector: independent of production fixtures, locks the algorithm.
_GOLDEN_FILES: dict[str, bytes] = {
    "pack.toml": (b'name = "gold"\nversion = "1.0.0"\nschema_version = 1\nengine_min = "0.0.0"\n'),
    "sources.csv": b"id,url,license,commercial_use,access_date,citation\n",
}
_GOLDEN_HASH = "sha256:6a785b0148f6f23bcb5865265c21d57c965aa9221e7fe2628b7420ef9bee7d01"


# ---- helpers -----------------------------------------------------------


def _write_pack(
    root: Path,
    *,
    content_hash: str | None = None,
    extra_files: dict[str, bytes] | None = None,
) -> None:
    root.mkdir(parents=True, exist_ok=True)
    toml = _MINIMAL_TOML
    if content_hash is not None:
        toml = toml + f'content_hash = "{content_hash}"\n'.encode()
    (root / "pack.toml").write_bytes(toml)
    for fn, hdr in _HEADERS.items():
        (root / fn).write_bytes(hdr)
    for relpath, data in (extra_files or {}).items():
        p = root / relpath
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)


def _manifest(content_hash: str | None) -> PackManifest:
    data: dict[str, object] = {
        "name": "minimal",
        "version": "1.0.0",
        "schema_version": 1,
        "engine_min": "0.0.0",
    }
    if content_hash is not None:
        data["content_hash"] = content_hash
    return PackManifest.model_validate(data)


# ---- hash_pack_files: format and determinism --------------------------


def test_hash_returns_sha256_prefix() -> None:
    h = hash_pack_files(_GOLDEN_FILES)
    assert h.startswith("sha256:")
    assert len(h) == len("sha256:") + 64


def test_hash_deterministic() -> None:
    assert hash_pack_files(_GOLDEN_FILES) == hash_pack_files(_GOLDEN_FILES)


def test_hash_order_independent() -> None:
    a = {"pack.toml": _GOLDEN_FILES["pack.toml"], "sources.csv": _GOLDEN_FILES["sources.csv"]}
    b = {"sources.csv": _GOLDEN_FILES["sources.csv"], "pack.toml": _GOLDEN_FILES["pack.toml"]}
    assert hash_pack_files(a) == hash_pack_files(b)


def test_hash_golden_vector() -> None:
    assert hash_pack_files(_GOLDEN_FILES) == _GOLDEN_HASH


# ---- hash_pack_files: line ending normalization -----------------------


def test_hash_crlf_equals_lf() -> None:
    a = {"pack.toml": _MINIMAL_TOML, "sources.csv": b"a\nb\n"}
    b = {"pack.toml": _MINIMAL_TOML, "sources.csv": b"a\r\nb\r\n"}
    assert hash_pack_files(a) == hash_pack_files(b)


def test_hash_bare_cr_equals_lf() -> None:
    a = {"pack.toml": _MINIMAL_TOML, "sources.csv": b"a\nb\n"}
    b = {"pack.toml": _MINIMAL_TOML, "sources.csv": b"a\rb\r"}
    assert hash_pack_files(a) == hash_pack_files(b)


# ---- hash_pack_files: pack.toml canonicalization ----------------------


def test_hash_pack_toml_key_order_invariant() -> None:
    a = {"pack.toml": b'name = "x"\nversion = "1.0.0"\nschema_version = 1\nengine_min = "0.0.0"\n'}
    b = {"pack.toml": b'engine_min = "0.0.0"\nschema_version = 1\nversion = "1.0.0"\nname = "x"\n'}
    assert hash_pack_files(a) == hash_pack_files(b)


def test_hash_pack_toml_comment_invariant() -> None:
    a = {"pack.toml": _MINIMAL_TOML}
    b = {"pack.toml": b"# leading comment\n" + _MINIMAL_TOML}
    assert hash_pack_files(a) == hash_pack_files(b)


def test_hash_pack_toml_ignores_content_hash() -> None:
    a = {"pack.toml": _MINIMAL_TOML}
    b = {"pack.toml": _MINIMAL_TOML + b'content_hash = "sha256:' + b"0" * 64 + b'"\n'}
    assert hash_pack_files(a) == hash_pack_files(b)


# ---- hash_pack_files: sensitivity -------------------------------------


def test_hash_single_byte_change() -> None:
    a = {"pack.toml": _MINIMAL_TOML, "sources.csv": b"hello"}
    b = {"pack.toml": _MINIMAL_TOML, "sources.csv": b"hellp"}
    assert hash_pack_files(a) != hash_pack_files(b)


def test_hash_boundary_shift() -> None:
    a = {"pack.toml": _MINIMAL_TOML, "a.csv": b"ab", "b.csv": b"cdef"}
    b = {"pack.toml": _MINIMAL_TOML, "a.csv": b"abc", "b.csv": b"def"}
    assert hash_pack_files(a) != hash_pack_files(b)


def test_hash_requires_pack_toml() -> None:
    with pytest.raises(PackTableInvalidError, match=r"pack\.toml"):
        hash_pack_files({"sources.csv": b"x"})


def test_hash_invalid_toml_raises() -> None:
    with pytest.raises(PackTableInvalidError, match="not valid TOML"):
        hash_pack_files({"pack.toml": b"= bad =\n"})


# ---- compute_pack_hash: allowlist via read_pack_bytes -----------------


def test_compute_pack_hash_uses_allowlist(tmp_path: Path) -> None:
    _write_pack(tmp_path)
    h1 = compute_pack_hash(tmp_path)
    (tmp_path / "README.md").write_text("ignored\n", encoding="utf-8")
    (tmp_path / "custom.json").write_text("{}\n", encoding="utf-8")
    h2 = compute_pack_hash(tmp_path)
    assert h1 == h2


def test_compute_pack_hash_matches_hash_pack_files(tmp_path: Path) -> None:
    _write_pack(tmp_path)
    files = read_pack_bytes(tmp_path)
    assert compute_pack_hash(tmp_path) == hash_pack_files(files)


# ---- verify_pack_hash: legacy strict ----------------------------------


def test_verify_legacy_passes_on_match(tmp_path: Path) -> None:
    _write_pack(tmp_path)
    digest = compute_pack_hash(tmp_path)
    _write_pack(tmp_path, content_hash=digest)
    verify_pack_hash(tmp_path, _manifest(digest))


def test_verify_legacy_raises_on_missing(tmp_path: Path) -> None:
    _write_pack(tmp_path)
    with pytest.raises(InvalidPackError, match="missing content_hash"):
        verify_pack_hash(tmp_path, _manifest(None))


def test_verify_legacy_raises_on_mismatch_with_lock_hint(tmp_path: Path) -> None:
    _write_pack(tmp_path)
    wrong = "sha256:" + "0" * 64
    with pytest.raises(PackHashMismatchError, match="agri-core pack lock"):
        verify_pack_hash(tmp_path, _manifest(wrong))


# ---- verify_pack_hash_full: tuple return ------------------------------


def test_verify_full_no_sources_unverified(tmp_path: Path) -> None:
    _write_pack(tmp_path)
    verified, actual = verify_pack_hash_full(tmp_path, _manifest(None))
    assert verified is False
    assert actual.startswith("sha256:")
    assert actual == compute_pack_hash(tmp_path)


def test_verify_full_manifest_match_verified(tmp_path: Path) -> None:
    _write_pack(tmp_path)
    digest = compute_pack_hash(tmp_path)
    _write_pack(tmp_path, content_hash=digest)
    verified, actual = verify_pack_hash_full(tmp_path, _manifest(digest))
    assert verified is True
    assert actual == digest


def test_verify_full_manifest_mismatch_has_lock_hint(tmp_path: Path) -> None:
    _write_pack(tmp_path)
    wrong = "sha256:" + "0" * 64
    with pytest.raises(PackHashMismatchError) as exc_info:
        verify_pack_hash_full(tmp_path, _manifest(wrong))
    assert "agri-core pack lock" in str(exc_info.value)


def test_verify_full_expected_hash_match_verified(tmp_path: Path) -> None:
    _write_pack(tmp_path)
    digest = compute_pack_hash(tmp_path)
    verified, actual = verify_pack_hash_full(tmp_path, _manifest(None), expected_hash=digest)
    assert verified is True
    assert actual == digest


def test_verify_full_expected_hash_mismatch_no_lock_hint(tmp_path: Path) -> None:
    _write_pack(tmp_path)
    wrong = "sha256:" + "0" * 64
    with pytest.raises(PackHashMismatchError) as exc_info:
        verify_pack_hash_full(tmp_path, _manifest(None), expected_hash=wrong)
    msg = str(exc_info.value)
    assert "expected_hash mismatch" in msg
    assert "agri-core pack lock" not in msg


def test_verify_full_both_match_verified(tmp_path: Path) -> None:
    _write_pack(tmp_path)
    digest = compute_pack_hash(tmp_path)
    _write_pack(tmp_path, content_hash=digest)
    verified, actual = verify_pack_hash_full(tmp_path, _manifest(digest), expected_hash=digest)
    assert verified is True
    assert actual == digest


# ---- load_pack integration --------------------------------------------


def test_load_pack_rejects_tampered_hash(tmp_path: Path) -> None:
    _write_pack(tmp_path)
    digest = compute_pack_hash(tmp_path)
    _write_pack(tmp_path, content_hash=digest)
    (tmp_path / "sources.csv").write_bytes(
        _HEADERS["sources.csv"] + b"S001,x,CC0-1.0,yes,2026-01-01,x\n"
    )
    with pytest.raises(PackHashMismatchError, match="mismatch"):
        load_pack(tmp_path)


def test_load_pack_allows_dev_mode_without_verification(tmp_path: Path) -> None:
    _write_pack(tmp_path)
    with pytest.raises(InvalidPackError, match="missing content_hash"):
        load_pack(tmp_path)
    p = load_pack(tmp_path, verify_hash=False)
    assert p.manifest.name == "minimal"


def test_load_sample_pack_verifies_hash() -> None:
    pack = load_sample_pack()
    assert pack.manifest.content_hash is not None
    assert pack.manifest.content_hash.startswith("sha256:")


def test_sample_pack_tamper_rejected(tmp_path: Path) -> None:
    pack = load_sample_pack()
    shutil.copytree(pack.root, tmp_path / "tampered")
    (tmp_path / "tampered" / "sources.csv").write_bytes(
        _HEADERS["sources.csv"] + b"S001,x,CC0-1.0,yes,2026-01-01,x\n"
    )
    with pytest.raises(PackHashMismatchError, match="mismatch"):
        load_pack(tmp_path / "tampered")
