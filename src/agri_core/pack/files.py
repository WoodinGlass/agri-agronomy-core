"""Read allowlisted pack files from disk."""

from __future__ import annotations

import contextlib
import os
import re
import stat
import sys
from collections.abc import Mapping
from pathlib import Path

from agri_core.models.ids import TAXON_ID_PATTERN
from agri_core.pack.errors import (
    InvalidPackError,
    PackNotFoundError,
    PackTableInvalidError,
    PackTooLargeError,
)
from agri_core.pack.tables import TABLES

DEFAULT_MAX_BYTES: int = 100 * 1024 * 1024
"""Default pack size budget: 100 MiB, summed over allowlist files only (P3)."""

REQUIRED_TABLES: tuple[str, ...] = (
    "taxa",
    "names",
    "hazards",
    "datasets",
    "sources",
)
"""Tables every pack must contain, at minimum as a header-only CSV (P2)."""

_CHUNK_SIZE: int = 64 * 1024
"""Read granularity; each os.read() is capped at remaining + 1 to detect overshoot."""

_FACTS_IGNORED: frozenset[str] = frozenset({".gitkeep", ".DS_Store", "Thumbs.db", "desktop.ini"})
"""Metadata-only files inside facts/ that are neither read nor hashed (F5)."""

_ADVISORIES_FILENAME: str = "advisories.csv"
"""Optional at pack root. Returned byte-exact; content validation is in the loader (F1)."""

_TAXON_STEM_RE: re.Pattern[str] = re.compile(TAXON_ID_PATTERN)
"""Compiled from models/ids.py (F6). Do not redefine the pattern here."""

_os_read = os.read
"""Module-level alias; tests replace this to simulate concurrent file growth (T4)."""

__all__ = ["DEFAULT_MAX_BYTES", "REQUIRED_TABLES", "read_pack_bytes"]


def _safe_name(name: str, *, max_len: int = 80) -> str:
    """Return a bounded, control-char-escaped form of an untrusted name (F8)."""
    out: list[str] = []
    for ch in name:
        cp = ord(ch)
        if cp < 0x20 or cp == 0x7F:
            out.append(f"\\x{cp:02x}")
        else:
            out.append(ch)
    s = "".join(out)
    if len(s) > max_len:
        s = s[: max_len - 3] + "..."
    return s


def _scan_dir(path: Path, *, relpath: str) -> dict[str, os.DirEntry[str]]:
    """os.scandir once; wrap OSError as InvalidPackError."""
    try:
        out: dict[str, os.DirEntry[str]] = {}
        for entry in os.scandir(path):
            out[entry.name] = entry
        return out
    except OSError as exc:
        raise InvalidPackError(
            f"cannot scan {_safe_name(relpath)}: {exc.strerror or exc}",
            file=relpath,
        ) from exc


def _check_case_collision(
    entries: Mapping[str, os.DirEntry[str]],
    *,
    canonical_names: tuple[str, ...],
    relpath: str,
) -> None:
    """Fail closed on case-only mismatches of allowlist names (F2)."""
    lower_to_canonical = {name.lower(): name for name in canonical_names}
    for name in entries:
        canonical = lower_to_canonical.get(name.lower())
        if canonical is not None and name != canonical:
            raise InvalidPackError(
                f"case mismatch: expected {_safe_name(canonical)!r}, found {_safe_name(name)!r}",
                file=relpath,
                key=name,
            )


def _reject_if_symlink(entry: os.DirEntry[str], *, relpath: str) -> None:
    """Reject symlinks inside the pack (F4)."""
    if entry.is_symlink():
        raise InvalidPackError(
            f"symlink not allowed inside pack: {_safe_name(relpath)}",
            file=relpath,
        )


def _open_and_read_regular(
    path: str,
    *,
    remaining: int,
    relpath: str,
) -> bytes:
    """Read a regular file with the F3 protocol.

    The file must be a regular file (fstat -> S_ISREG); symlinks are
    rejected by O_NOFOLLOW on POSIX and by lstat on Windows. The size
    check runs both at fstat time (st_size > remaining) and during the
    read loop, so a file that grows after fstat is caught as
    PackTooLargeError.
    """
    if sys.platform == "win32":  # pragma: no cover
        try:
            st_l = os.lstat(path)
        except OSError as exc:
            raise InvalidPackError(
                f"cannot stat {_safe_name(relpath)}: {exc.strerror or exc}",
                file=relpath,
            ) from exc
        if stat.S_ISLNK(st_l.st_mode):
            raise InvalidPackError(
                f"symlink not allowed inside pack: {_safe_name(relpath)}",
                file=relpath,
            )
        if not stat.S_ISREG(st_l.st_mode):
            raise InvalidPackError(
                f"not a regular file: {_safe_name(relpath)}",
                file=relpath,
            )

    flags = (
        os.O_RDONLY
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_BINARY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_NONBLOCK", 0)
    )
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        raise InvalidPackError(
            f"cannot open {_safe_name(relpath)}: {exc.strerror or exc}",
            file=relpath,
        ) from exc

    try:
        try:
            st = os.fstat(fd)
        except OSError as exc:
            raise InvalidPackError(
                f"cannot fstat {_safe_name(relpath)}: {exc.strerror or exc}",
                file=relpath,
            ) from exc
        if not stat.S_ISREG(st.st_mode):
            raise InvalidPackError(
                f"not a regular file: {_safe_name(relpath)}",
                file=relpath,
            )
        if st.st_size > remaining:
            raise PackTooLargeError(
                f"pack exceeds max_bytes budget while reading {_safe_name(relpath)}",
                file=relpath,
            )

        chunks: list[bytes] = []
        read_total = 0
        try:
            while True:
                cap = min(_CHUNK_SIZE, remaining - read_total + 1)
                if cap <= 0:
                    raise PackTooLargeError(
                        f"pack exceeds max_bytes budget while reading {_safe_name(relpath)}",
                        file=relpath,
                    )
                chunk = _os_read(fd, cap)
                if not chunk:
                    break
                read_total += len(chunk)
                if read_total > remaining:
                    raise PackTooLargeError(
                        f"pack exceeds max_bytes budget while reading {_safe_name(relpath)}",
                        file=relpath,
                    )
                chunks.append(chunk)
        except OSError as exc:
            raise InvalidPackError(
                f"cannot read {_safe_name(relpath)}: {exc.strerror or exc}",
                file=relpath,
            ) from exc
        return b"".join(chunks)
    finally:
        with contextlib.suppress(OSError):  # pragma: no cover
            os.close(fd)


def read_pack_bytes(
    root: Path,
    *,
    max_bytes: int = DEFAULT_MAX_BYTES,
) -> Mapping[str, bytes]:
    """Read every allowlisted file under *root* exactly once.

    Returns a dict mapping POSIX relpath (``"pack.toml"``, ``"taxa.csv"``,
    ``"facts/T000000001.csv"``) to raw bytes. Content is byte-exact:
    line endings and non-UTF-8 bytes are preserved.

    Raises:
        ValueError:            *max_bytes* is not positive (caller error).
        PackNotFoundError:    *root* does not exist.
        InvalidPackError:     *root* is not a directory, a required file is
                              missing, a case-only mismatch of an allowlist
                              name appears on a case-sensitive filesystem, a
                              symlink or non-regular file appears inside the
                              pack, or the OS denies access.
        PackTooLargeError:    allowlist total exceeds *max_bytes*, including
                              growth during read.
        PackTableInvalidError: an unexpected entry appears in ``facts/``, or
                              a facts filename does not match ``<taxon_id>.csv``.

    Files at the pack root that are not on the allowlist are ignored: they
    are neither read, hashed, nor size-accounted (F9). A ``read_pack_bytes``
    call does not parse CSV, hash, or validate manifest fields.
    """
    if max_bytes <= 0:
        raise ValueError(f"max_bytes must be positive, got {max_bytes!r}")

    root = Path(root)
    if not root.exists():
        raise PackNotFoundError(f"pack directory not found: {root}")
    if not root.is_dir():
        raise InvalidPackError(
            f"not a directory: {_safe_name(str(root))}",
            file=str(root),
        )

    required_filenames: list[str] = []
    for table in REQUIRED_TABLES:
        spec = TABLES[table]
        assert spec.filename is not None, f"{table} has no filename"
        required_filenames.append(spec.filename)

    canonical_names: tuple[str, ...] = (
        "pack.toml",
        *required_filenames,
        _ADVISORIES_FILENAME,
        "facts",
    )

    files: dict[str, bytes] = {}
    total = 0

    root_entries = _scan_dir(root, relpath=".")
    _check_case_collision(root_entries, canonical_names=canonical_names, relpath=".")

    # 1. pack.toml
    if "pack.toml" not in root_entries:
        raise InvalidPackError("required file missing: pack.toml", file="pack.toml")
    _reject_if_symlink(root_entries["pack.toml"], relpath="pack.toml")
    data = _open_and_read_regular(
        root_entries["pack.toml"].path,
        remaining=max_bytes - total,
        relpath="pack.toml",
    )
    total += len(data)
    files["pack.toml"] = data

    # 2. required tables in fixed order
    for filename in required_filenames:
        if filename not in root_entries:
            raise InvalidPackError(
                f"required file missing: {_safe_name(filename)}",
                file=filename,
            )
        _reject_if_symlink(root_entries[filename], relpath=filename)
        data = _open_and_read_regular(
            root_entries[filename].path,
            remaining=max_bytes - total,
            relpath=filename,
        )
        total += len(data)
        files[filename] = data

    # 3. advisories.csv — optional, byte-exact (F1)
    if _ADVISORIES_FILENAME in root_entries:
        _reject_if_symlink(root_entries[_ADVISORIES_FILENAME], relpath=_ADVISORIES_FILENAME)
        data = _open_and_read_regular(
            root_entries[_ADVISORIES_FILENAME].path,
            remaining=max_bytes - total,
            relpath=_ADVISORIES_FILENAME,
        )
        total += len(data)
        files[_ADVISORIES_FILENAME] = data

    # 4. facts/ — optional
    if "facts" in root_entries:
        facts_entry = root_entries["facts"]
        _reject_if_symlink(facts_entry, relpath="facts")
        if not facts_entry.is_dir(follow_symlinks=False):
            raise InvalidPackError(
                "expected directory at facts/, found non-directory",
                file="facts",
            )
        try:
            facts_entries = sorted(os.scandir(facts_entry.path), key=lambda e: e.name)
        except OSError as exc:
            raise InvalidPackError(
                f"cannot scan facts/: {exc.strerror or exc}",
                file="facts",
            ) from exc
        for entry in facts_entries:
            name = entry.name
            if name in _FACTS_IGNORED:
                continue
            relpath = f"facts/{name}"
            if entry.is_symlink():
                raise InvalidPackError(
                    f"symlink not allowed inside pack: {_safe_name(relpath)}",
                    file=relpath,
                )
            if not entry.is_file(follow_symlinks=False):
                raise PackTableInvalidError(
                    f"unexpected entry in facts/: {_safe_name(name)}",
                    file=relpath,
                )
            if not name.endswith(".csv"):
                raise PackTableInvalidError(
                    f"unexpected file in facts/: {_safe_name(name)}",
                    file=relpath,
                )
            stem = name[:-4]
            if not _TAXON_STEM_RE.match(stem):
                raise PackTableInvalidError(
                    "facts/ filename must be <taxon_id>.csv (T + 9 Crockford), "
                    f"got {_safe_name(name)!r}",
                    file=relpath,
                )
            data = _open_and_read_regular(
                entry.path,
                remaining=max_bytes - total,
                relpath=relpath,
            )
            total += len(data)
            files[relpath] = data

    return dict(sorted(files.items()))
