"""Content-hash computation and verification for packs."""

from __future__ import annotations

import hashlib
from pathlib import Path

from agri_core.pack.errors import InvalidPackError
from agri_core.pack.manifest import PackManifest

_SKIP_DIR_PARTS = frozenset(
    {"__pycache__", ".git", ".hg", ".svn", ".pytest_cache", ".mypy_cache", ".ruff_cache"}
)
_SKIP_NAMES = frozenset({".DS_Store", "Thumbs.db"})
_SKIP_SUFFIXES = frozenset({".pyc", ".pyo", ".swp", ".swx"})


def _should_skip(path: Path, root: Path) -> bool:
    parts = path.relative_to(root).parts
    if any(part in _SKIP_DIR_PARTS for part in parts[:-1]):
        return True
    if any(part.endswith(".egg-info") for part in parts):
        return True
    if path.name in _SKIP_NAMES:
        return True
    return path.suffix in _SKIP_SUFFIXES


def _strip_content_hash_line(text: str) -> str:
    normalised = text.replace("\r\n", "\n").replace("\r", "\n")
    kept: list[str] = []
    for line in normalised.split("\n"):
        key, sep, _rest = line.partition("=")
        if sep and key.strip() == "content_hash":
            continue
        kept.append(line)
    return "\n".join(kept)


def compute_pack_hash(root: Path) -> str:
    """Return ``sha256:<hex>`` over every tracked file under *root*."""
    root = Path(root)
    if not root.is_dir():
        raise InvalidPackError(f"pack directory not found: {root}")
    digest = hashlib.sha256()
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        if _should_skip(path, root):
            continue
        rel = path.relative_to(root).as_posix().encode("utf-8")
        raw = path.read_bytes()
        if path.name == "pack.toml":
            try:
                text = raw.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise InvalidPackError(f"pack.toml is not valid UTF-8: {exc}") from exc
            raw = _strip_content_hash_line(text).encode("utf-8")
        digest.update(rel)
        digest.update(b"\0")
        digest.update(raw)
        digest.update(b"\0")
    return "sha256:" + digest.hexdigest()


def verify_pack_hash(root: Path, manifest: PackManifest) -> None:
    """Raise ``InvalidPackError`` if ``content_hash`` is missing or mismatched."""
    expected = manifest.content_hash
    if expected is None:
        raise InvalidPackError("pack.toml is missing content_hash; refusing to load")
    actual = compute_pack_hash(Path(root))
    if actual != expected:
        raise InvalidPackError(f"content_hash mismatch: manifest={expected} computed={actual}")
