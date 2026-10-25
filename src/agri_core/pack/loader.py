"""Load a pack directory or the bundled sample pack."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from importlib.resources import files as _resource_files
from pathlib import Path
from typing import Literal

from packaging.version import Version

from agri_core import __version__
from agri_core.pack.errors import (
    EngineTooOldError,
    InvalidPackError,
    PackNotFoundError,
    UnsupportedSchemaVersionError,
)
from agri_core.pack.manifest import SUPPORTED_SCHEMA_VERSIONS, PackManifest
from agri_core.pack.verify import verify_pack_hash

PackKind = Literal["sample", "directory"]


@dataclass(frozen=True)
class Pack:
    """A loaded pack: manifest plus paths to its files."""

    root: Path
    kind: PackKind
    manifest: PackManifest
    sources_csv: Path


def _read_manifest(pack_dir: Path) -> PackManifest:
    manifest_path = pack_dir / "pack.toml"
    if not manifest_path.is_file():
        raise InvalidPackError(f"pack.toml not found in {pack_dir}")
    try:
        with manifest_path.open("rb") as f:
            raw = tomllib.load(f)
    except tomllib.TOMLDecodeError as exc:
        raise InvalidPackError(f"pack.toml is not valid TOML: {exc}") from exc
    try:
        return PackManifest.model_validate(raw)
    except ValueError as exc:
        raise InvalidPackError(f"pack.toml is invalid: {exc}") from exc


def _check_compat(manifest: PackManifest) -> None:
    if manifest.schema_version not in SUPPORTED_SCHEMA_VERSIONS:
        raise UnsupportedSchemaVersionError(
            f"schema_version {manifest.schema_version} not in {sorted(SUPPORTED_SCHEMA_VERSIONS)}"
        )
    engine = Version(__version__).base_version
    required = Version(manifest.engine_min).base_version
    if Version(engine) < Version(required):
        raise EngineTooOldError(f"engine {engine} < required {required} (pack needs newer engine)")


def _finish(root: Path, kind: PackKind, *, verify_hash: bool = True) -> Pack:
    manifest = _read_manifest(root)
    _check_compat(manifest)
    if verify_hash:
        verify_pack_hash(root, manifest)
    sources_csv = root / "sources.csv"
    if not sources_csv.is_file():
        raise InvalidPackError(f"sources.csv not found in {root}")
    return Pack(root=root, kind=kind, manifest=manifest, sources_csv=sources_csv)


def load_pack(path: str | Path, *, verify_hash: bool = True) -> Pack:
    """Load a pack from an explicit directory. The directory must contain pack.toml."""
    root = Path(path)
    if not root.is_dir():
        raise PackNotFoundError(f"pack directory not found: {root}")
    return _finish(root, kind="directory", verify_hash=verify_hash)


def load_sample_pack(*, verify_hash: bool = True) -> Pack:
    """Load the sample pack shipped inside the installed package."""
    root = Path(str(_resource_files("agri_core") / "_samples" / "sample_pack"))
    if not root.is_dir():
        raise PackNotFoundError("sample pack missing from installed package (broken installation)")
    return _finish(root, kind="sample", verify_hash=verify_hash)
