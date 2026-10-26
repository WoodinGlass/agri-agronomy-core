"""Content-hash computation and verification for packs (P1, K3, P8)."""

from __future__ import annotations

import hashlib
import tomllib
from collections.abc import Mapping
from pathlib import Path

from agri_core.models.canonical import canonical_json
from agri_core.pack.errors import (
    InvalidPackError,
    PackHashMismatchError,
    PackTableInvalidError,
)
from agri_core.pack.files import DEFAULT_MAX_BYTES, read_pack_bytes
from agri_core.pack.manifest import PackManifest

_HASH_DOMAIN = b"agri-pack-hash-v1\n"
"""Domain-separation prefix. Changing this value is a hash-algorithm change."""

__all__ = [
    "compute_pack_hash",
    "hash_pack_files",
    "verify_pack_hash",
    "verify_pack_hash_full",
]


def _normalize_lf(data: bytes) -> bytes:
    return data.replace(b"\r\n", b"\n").replace(b"\r", b"\n")


def _pack_toml_content(data: bytes) -> bytes:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise PackTableInvalidError(
            f"pack.toml is not valid UTF-8: {exc}", file="pack.toml"
        ) from exc
    try:
        parsed = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise PackTableInvalidError(
            f"pack.toml is not valid TOML: {exc}", file="pack.toml"
        ) from exc
    parsed.pop("content_hash", None)
    return canonical_json(parsed)


def _content_bytes(relpath: str, data: bytes) -> bytes:
    if relpath == "pack.toml":
        return _pack_toml_content(data)
    return _normalize_lf(data)


def hash_pack_files(files: Mapping[str, bytes]) -> str:
    """Return ``sha256:<hex>`` over *files* in canonical form (P1).

    Algorithm::

        h = sha256(b"agri-pack-hash-v1\n")
        for relpath in sorted(files):
            content = _content_bytes(relpath, files[relpath])
            h.update(sha256(content).hexdigest() + "  " + relpath + "\n")
        return "sha256:" + h.hexdigest()

    Content normalization:
      - ``pack.toml``: parse TOML, remove ``content_hash``, encode via
        ``canonical_json`` (sorted keys, compact separators, UTF-8).
      - everything else: LF-normalized (``\r\n`` and bare ``\r`` -> ``\n``).

    Raises ``PackTableInvalidError(file="pack.toml")`` if *files* lacks
    ``pack.toml`` or if its content is not valid TOML.
    """
    if "pack.toml" not in files:
        raise PackTableInvalidError("pack.toml missing from files mapping", file="pack.toml")
    digest = hashlib.sha256()
    digest.update(_HASH_DOMAIN)
    for relpath in sorted(files):
        content = _content_bytes(relpath, files[relpath])
        content_hex = hashlib.sha256(content).hexdigest()
        digest.update(f"{content_hex}  {relpath}\n".encode())
    return "sha256:" + digest.hexdigest()


def compute_pack_hash(root: Path, *, max_bytes: int = DEFAULT_MAX_BYTES) -> str:
    """Read allowlisted files under *root* and return ``hash_pack_files(files)``."""
    files = read_pack_bytes(Path(root), max_bytes=max_bytes)
    return hash_pack_files(files)


def verify_pack_hash(root: Path, manifest: PackManifest) -> None:
    """Legacy strict verifier: raise on missing or mismatched ``content_hash``.

    Kept for ``loader.py`` and downstream callers. On mismatch the message
    suggests ``agri-core pack lock`` because the pack manifest's own hash is
    the file under the maintainer's control.
    """
    if manifest.content_hash is None:
        raise InvalidPackError(
            "pack.toml is missing content_hash; refusing to load",
            file="pack.toml",
        )
    actual = compute_pack_hash(Path(root))
    if actual != manifest.content_hash:
        raise PackHashMismatchError(
            f"content_hash mismatch: manifest={manifest.content_hash} "
            f"computed={actual}. If you changed this pack, run "
            f"`agri-core pack lock`. Otherwise treat the pack as corrupt "
            f"or tampered.",
            file="pack.toml",
        )


def verify_pack_hash_full(
    root: Path,
    manifest: PackManifest,
    *,
    expected_hash: str | None = None,
    max_bytes: int = DEFAULT_MAX_BYTES,
) -> tuple[bool, str]:
    """Return ``(verified, actual_hash)`` (K3 step 3-4).

    - Both ``manifest.content_hash`` and *expected_hash* absent: no
      integrity source was declared, so return ``(False, actual)``
      without raising (caller is expected to emit a warning).
    - ``manifest.content_hash`` present and mismatched: raise
      ``PackHashMismatchError`` with the pack-lock hint.
    - *expected_hash* present and mismatched: raise
      ``PackHashMismatchError`` **without** the pack-lock hint, because
      the caller's pin is the authority, not the pack.
    """
    actual = compute_pack_hash(Path(root), max_bytes=max_bytes)

    if manifest.content_hash is not None and manifest.content_hash != actual:
        raise PackHashMismatchError(
            f"content_hash mismatch: manifest={manifest.content_hash} "
            f"computed={actual}. If you changed this pack, run "
            f"`agri-core pack lock`. Otherwise treat the pack as corrupt "
            f"or tampered.",
            file="pack.toml",
        )

    if expected_hash is not None and expected_hash != actual:
        raise PackHashMismatchError(
            f"expected_hash mismatch: caller={expected_hash} "
            f"computed={actual}. The pack does not match the caller's pin.",
            file="pack.toml",
        )

    verified = manifest.content_hash is not None or expected_hash is not None
    return (verified, actual)
