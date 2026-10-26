"""Orchestrate a source-pack build (M6-4).

``build_pack`` owns the full lifecycle: read, validate, optionally
sync the source pack.toml, write the built artifact. SQLite primitives
(``build_sqlite_bytes``, ``write_built_pack``) remain in
``sqlite_schema.py``; validation lives in ``validate.py``.
"""

from __future__ import annotations

import contextlib
import json
import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from agri_core.pack.errors import InvalidPackError
from agri_core.pack.files import read_pack_bytes
from agri_core.pack.loader import parse_manifest_bytes
from agri_core.pack.manifest import PackManifest
from agri_core.pack.sqlite_schema import write_built_pack
from agri_core.pack.validate import validate_pack
from agri_core.pack.verify import hash_pack_files

__all__ = [
    "BuildResult",
    "build_pack",
    "render_source_manifest",
    "strip_content_hash",
    "sync_source_hash",
]


@dataclass(frozen=True)
class BuildResult:
    """Outcome of a ``build_pack`` call."""

    source: Path
    out_dir: Path
    source_hash_status: str | None
    content_hash: str
    artifact_sha256: str


def render_source_manifest(manifest: PackManifest, content_hash: str) -> bytes:
    """Render source pack.toml bytes with fixed key order (comments not preserved).

    Mirrors the shape used by ``agri-core pack lock``. Kept separate from
    ``toml_writer.dump_manifest`` (which renders *built* manifests with the
    build-only fields) so lock and build write byte-identical source TOML.
    """
    lines = [
        f"name = {json.dumps(manifest.name)}",
        f"version = {json.dumps(manifest.version)}",
        f"schema_version = {manifest.schema_version}",
        f"engine_min = {json.dumps(manifest.engine_min)}",
        f"dictionary_min = {json.dumps(manifest.dictionary_min)}",
        f"synthetic = {'true' if manifest.synthetic else 'false'}",
        f"content_hash = {json.dumps(content_hash)}",
    ]
    return ("\n".join(lines) + "\n").encode("utf-8")


def strip_content_hash(toml_bytes: bytes) -> bytes:
    """Remove the ``content_hash`` line so structural validation skips the hash check."""
    text = toml_bytes.decode("utf-8")
    lines = [ln for ln in text.splitlines() if not ln.lstrip().startswith("content_hash")]
    return ("\n".join(lines) + "\n").encode("utf-8")


def sync_source_hash(
    source: Path,
    files: Mapping[str, bytes],
    manifest: PackManifest,
) -> tuple[str, dict[str, bytes]]:
    """Rewrite source pack.toml canonically.

    Returns ``(status, files_with_fresh_toml)`` where status is one of
    ``"unchanged"``, ``"updated"``, or ``"normalized"``. Raises
    ``OSError`` if the atomic write fails (``.tmp`` is cleaned up).
    """
    computed = hash_pack_files(files)
    fresh_bytes = render_source_manifest(manifest, computed)
    if manifest.content_hash == computed and files["pack.toml"] == fresh_bytes:
        return "unchanged", dict(files)
    status = "updated" if manifest.content_hash != computed else "normalized"
    target = source / "pack.toml"
    tmp = source / "pack.toml.tmp"
    try:
        tmp.write_bytes(fresh_bytes)
        os.replace(tmp, target)
    except OSError:
        with contextlib.suppress(OSError):
            tmp.unlink(missing_ok=True)
        raise
    return status, {**files, "pack.toml": fresh_bytes}


def build_pack(
    source: Path,
    out_dir: Path,
    *,
    update_source_hash: bool = False,
) -> BuildResult:
    """Validate a source pack and write a built SQLite artifact.

    Rejects a directory that already contains ``pack.sqlite`` (not a
    source pack). Always permits synthetic packs — only calculation
    commands (M8+) require explicit opt-in.

    Raises ``PackError`` subclasses for validation errors and
    ``OSError`` for filesystem errors during source ``pack.toml`` sync.
    """
    if (source / "pack.sqlite").is_file():
        raise InvalidPackError(
            f"{source} contains pack.sqlite; build requires a source pack",
            file="pack.sqlite",
        )

    files = read_pack_bytes(source)
    manifest = parse_manifest_bytes(files["pack.toml"])

    source_hash_status: str | None = None
    if update_source_hash:
        stripped = {
            **files,
            "pack.toml": strip_content_hash(files["pack.toml"]),
        }
        validate_pack(stripped, allow_synthetic=True)
        source_hash_status, files = sync_source_hash(source, files, manifest)
    else:
        validate_pack(files, allow_synthetic=True)

    write_built_pack(files, out_dir=out_dir)
    built = parse_manifest_bytes((out_dir / "pack.toml").read_bytes())

    content_hash = built.content_hash
    artifact_sha256 = built.artifact_sha256
    if content_hash is None or artifact_sha256 is None:
        raise InvalidPackError(
            "built pack.toml missing content_hash or artifact_sha256",
            file="pack.toml",
        )

    return BuildResult(
        source=source,
        out_dir=out_dir,
        source_hash_status=source_hash_status,
        content_hash=content_hash,
        artifact_sha256=artifact_sha256,
    )
