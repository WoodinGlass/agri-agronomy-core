"""Pack content-hash contract tests."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from agri_core.pack import (
    InvalidPackError,
    PackManifest,
    compute_pack_hash,
    load_pack,
    load_sample_pack,
    verify_pack_hash,
)

pytestmark = pytest.mark.contract


def _write_minimal_pack(root: Path, *, content_hash: str | None = None) -> None:
    root.mkdir(parents=True, exist_ok=True)
    lines = [
        'name = "minimal"',
        'version = "1.0.0"',
        "schema_version = 1",
        'engine_min = "0.0.0"',
    ]
    if content_hash is not None:
        lines.append(f'content_hash = "{content_hash}"')
    (root / "pack.toml").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (root / "sources.csv").write_text(
        "id,url,license,commercial_use,access_date,citation\n",
        encoding="utf-8",
    )


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


def test_compute_pack_hash_is_deterministic(tmp_path: Path) -> None:
    _write_minimal_pack(tmp_path)
    assert compute_pack_hash(tmp_path) == compute_pack_hash(tmp_path)


def test_compute_pack_hash_changes_when_file_changes(tmp_path: Path) -> None:
    _write_minimal_pack(tmp_path)
    before = compute_pack_hash(tmp_path)
    (tmp_path / "sources.csv").write_text(
        "id,url,license,commercial_use,access_date,citation\nS001,x,CC0-1.0,yes,2026-01-01,x\n",
        encoding="utf-8",
    )
    assert compute_pack_hash(tmp_path) != before


def test_compute_pack_hash_ignores_content_hash_line(tmp_path: Path) -> None:
    _write_minimal_pack(tmp_path, content_hash="sha256:" + "0" * 64)
    before = compute_pack_hash(tmp_path)
    _write_minimal_pack(tmp_path, content_hash="sha256:" + "f" * 64)
    assert compute_pack_hash(tmp_path) == before


def test_verify_pack_hash_passes_on_matching(tmp_path: Path) -> None:
    _write_minimal_pack(tmp_path)
    digest = compute_pack_hash(tmp_path)
    _write_minimal_pack(tmp_path, content_hash=digest)
    verify_pack_hash(tmp_path, _manifest(digest))


def test_verify_pack_hash_raises_when_missing(tmp_path: Path) -> None:
    _write_minimal_pack(tmp_path)
    with pytest.raises(InvalidPackError, match="content_hash"):
        verify_pack_hash(tmp_path, _manifest(None))


def test_verify_pack_hash_raises_on_mismatch(tmp_path: Path) -> None:
    _write_minimal_pack(tmp_path)
    wrong = "sha256:" + "0" * 64
    with pytest.raises(InvalidPackError, match="mismatch"):
        verify_pack_hash(tmp_path, _manifest(wrong))


def test_load_pack_rejects_tampered_hash(tmp_path: Path) -> None:
    _write_minimal_pack(tmp_path)
    digest = compute_pack_hash(tmp_path)
    _write_minimal_pack(tmp_path, content_hash=digest)
    (tmp_path / "sources.csv").write_text(
        "id,url,license,commercial_use,access_date,citation\nS001,x,CC0-1.0,yes,2026-01-01,x\n",
        encoding="utf-8",
    )
    with pytest.raises(InvalidPackError, match="mismatch"):
        load_pack(tmp_path)


def test_load_pack_allows_dev_mode_without_verification(tmp_path: Path) -> None:
    _write_minimal_pack(tmp_path)
    with pytest.raises(InvalidPackError, match="content_hash"):
        load_pack(tmp_path)
    pack = load_pack(tmp_path, verify_hash=False)
    assert pack.manifest.name == "minimal"


def test_load_sample_pack_verifies_hash() -> None:
    pack = load_sample_pack()
    assert pack.manifest.content_hash is not None
    assert pack.manifest.content_hash.startswith("sha256:")


def test_sample_pack_tamper_is_rejected(tmp_path: Path) -> None:
    pack = load_sample_pack()
    shutil.copytree(pack.root, tmp_path / "tampered")
    (tmp_path / "tampered" / "README.md").write_text("changed\n", encoding="utf-8")
    with pytest.raises(InvalidPackError, match="mismatch"):
        load_pack(tmp_path / "tampered")
