"""read_pack_bytes behavior and safety invariants."""

from __future__ import annotations

import csv
import io
import os
import threading
from pathlib import Path

import pytest

import agri_core.pack.files as files_module
from agri_core.models.ids import TAXON_ID_PATTERN
from agri_core.pack.errors import (
    InvalidPackError,
    PackNotFoundError,
    PackTableInvalidError,
    PackTooLargeError,
)
from agri_core.pack.files import REQUIRED_TABLES, read_pack_bytes
from agri_core.pack.tables import TABLES

pytestmark = pytest.mark.contract


# ---- helpers ------------------------------------------------------------


def _header_bytes(table: str) -> bytes:
    cols = [c.name for c in TABLES[table].columns]
    buf = io.StringIO()
    csv.writer(buf, lineterminator="\n").writerow(cols)
    return buf.getvalue().encode("utf-8")


def _make_pack(root: Path, *, overrides: dict[str, bytes] | None = None) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "pack.toml").write_text(
        'name = "p"\nversion = "1.0.0"\nschema_version = 1\nengine_min = "0.0.0"\n',
        encoding="utf-8",
    )
    for table in REQUIRED_TABLES:
        spec = TABLES[table]
        assert spec.filename is not None
        (root / spec.filename).write_bytes(_header_bytes(table))
    for relpath, data in (overrides or {}).items():
        p = root / relpath
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)


def _fs_case_sensitive(tmp: Path) -> bool:
    probe = tmp / "Probe_Case"
    probe.write_text("x", encoding="utf-8")
    return not (tmp / "probe_case").exists()


# ---- basic -------------------------------------------------------------


def test_read_returns_all_required(tmp_path: Path) -> None:
    _make_pack(tmp_path)
    files = read_pack_bytes(tmp_path)
    assert set(files) == {
        "pack.toml",
        "taxa.csv",
        "names.csv",
        "hazards.csv",
        "datasets.csv",
        "sources.csv",
    }
    assert all(isinstance(v, bytes) for v in files.values())


def test_read_ignores_other_root_files(tmp_path: Path) -> None:
    _make_pack(tmp_path)
    (tmp_path / "README.md").write_text("ignored\n", encoding="utf-8")
    (tmp_path / ".DS_Store").write_bytes(b"\x00\x01")
    files = read_pack_bytes(tmp_path)
    assert "README.md" not in files
    assert ".DS_Store" not in files


def test_read_not_found(tmp_path: Path) -> None:
    with pytest.raises(PackNotFoundError):
        read_pack_bytes(tmp_path / "nope")


def test_read_root_is_regular_file_raises(tmp_path: Path) -> None:
    f = tmp_path / "not_a_dir"
    f.write_text("x", encoding="utf-8")
    with pytest.raises(InvalidPackError, match="not a directory"):
        read_pack_bytes(f)


def test_read_requires_pack_toml(tmp_path: Path) -> None:
    _make_pack(tmp_path)
    (tmp_path / "pack.toml").unlink()
    with pytest.raises(InvalidPackError, match=r"pack\.toml"):
        read_pack_bytes(tmp_path)


@pytest.mark.parametrize("table", REQUIRED_TABLES)
def test_read_requires_each_table(tmp_path: Path, table: str) -> None:
    _make_pack(tmp_path)
    spec = TABLES[table]
    assert spec.filename is not None
    (tmp_path / spec.filename).unlink()
    with pytest.raises(InvalidPackError, match=spec.filename):
        read_pack_bytes(tmp_path)


def test_read_includes_facts(tmp_path: Path) -> None:
    facts_header = _header_bytes("facts")
    _make_pack(tmp_path, overrides={"facts/T000000001.csv": facts_header})
    files = read_pack_bytes(tmp_path)
    assert "facts/T000000001.csv" in files
    assert files["facts/T000000001.csv"] == facts_header


def test_read_rejects_non_csv_in_facts(tmp_path: Path) -> None:
    _make_pack(tmp_path, overrides={"facts/notes.txt": b"x\n"})
    with pytest.raises(PackTableInvalidError, match="unexpected file"):
        read_pack_bytes(tmp_path)


def test_read_rejects_bad_facts_stem(tmp_path: Path) -> None:
    _make_pack(tmp_path, overrides={"facts/foo.csv": b"x\n"})
    with pytest.raises(PackTableInvalidError, match="taxon_id"):
        read_pack_bytes(tmp_path)


def test_read_advisories_returned_asis(tmp_path: Path) -> None:
    content = b"any,arbitrary,bytes,we,do,not,interpret\n"
    _make_pack(tmp_path, overrides={"advisories.csv": content})
    files = read_pack_bytes(tmp_path)
    assert files["advisories.csv"] == content


def test_read_max_bytes_nonpositive_raises_valueerror(tmp_path: Path) -> None:
    _make_pack(tmp_path)
    with pytest.raises(ValueError, match="max_bytes must be positive"):
        read_pack_bytes(tmp_path, max_bytes=0)
    with pytest.raises(ValueError, match="max_bytes must be positive"):
        read_pack_bytes(tmp_path, max_bytes=-1)


def test_read_taxon_pattern_matches_models() -> None:
    # F6 safety net: the pattern exported from models/ids.py is the source of
    # truth for facts/ filename validation.
    import re

    assert isinstance(TAXON_ID_PATTERN, str)
    compiled = re.compile(TAXON_ID_PATTERN)
    assert compiled.match("T000000001")
    assert not compiled.match("t000000001")
    assert not compiled.match("T00000001")
    assert not compiled.match("T0000000001")


# ---- T1: symlinks ------------------------------------------------------


def test_read_accepts_root_symlink(tmp_path: Path) -> None:
    real = tmp_path / "realpack"
    _make_pack(real)
    link = tmp_path / "linkpack"
    link.symlink_to(real)
    files = read_pack_bytes(link)
    assert "pack.toml" in files


def test_read_rejects_symlink_pack_toml(tmp_path: Path) -> None:
    _make_pack(tmp_path)
    real = tmp_path / "_real_pack.toml"
    (tmp_path / "pack.toml").rename(real)
    (tmp_path / "pack.toml").symlink_to(real)
    with pytest.raises(InvalidPackError, match="symlink"):
        read_pack_bytes(tmp_path)


def test_read_rejects_symlink_facts_file(tmp_path: Path) -> None:
    _make_pack(tmp_path)
    (tmp_path / "facts").mkdir()
    real = tmp_path / "_real_facts.csv"
    real.write_bytes(_header_bytes("facts"))
    (tmp_path / "facts" / "T000000001.csv").symlink_to(real)
    with pytest.raises(InvalidPackError, match="symlink"):
        read_pack_bytes(tmp_path)


def test_read_rejects_symlink_facts_dir(tmp_path: Path) -> None:
    _make_pack(tmp_path)
    real = tmp_path / "_real_facts"
    real.mkdir()
    (tmp_path / "facts").symlink_to(real)
    with pytest.raises(InvalidPackError, match="symlink"):
        read_pack_bytes(tmp_path)


# ---- T2: facts/ structure ----------------------------------------------


def test_read_no_facts_dir_ok(tmp_path: Path) -> None:
    _make_pack(tmp_path)
    files = read_pack_bytes(tmp_path)
    assert not any(k.startswith("facts/") for k in files)


def test_read_facts_empty_ok(tmp_path: Path) -> None:
    _make_pack(tmp_path)
    (tmp_path / "facts").mkdir()
    files = read_pack_bytes(tmp_path)
    assert not any(k.startswith("facts/") for k in files)


def test_read_facts_subdir_raises(tmp_path: Path) -> None:
    _make_pack(tmp_path)
    (tmp_path / "facts").mkdir()
    (tmp_path / "facts" / "sub").mkdir()
    with pytest.raises(PackTableInvalidError, match="unexpected entry"):
        read_pack_bytes(tmp_path)


@pytest.mark.parametrize("ignored", [".gitkeep", ".DS_Store", "Thumbs.db", "desktop.ini"])
def test_read_facts_metadata_files_ignored(tmp_path: Path, ignored: str) -> None:
    _make_pack(tmp_path)
    (tmp_path / "facts").mkdir()
    (tmp_path / "facts" / ignored).write_bytes(b"x")
    files = read_pack_bytes(tmp_path)
    assert f"facts/{ignored}" not in files


# ---- T3: case mismatch -------------------------------------------------


@pytest.mark.parametrize(
    "wrong_name",
    ["Taxa.csv", "Advisories.csv", "PACK.toml"],
)
def test_read_rejects_wrong_case(tmp_path: Path, wrong_name: str) -> None:
    if not _fs_case_sensitive(tmp_path):
        pytest.skip("filesystem is case-insensitive")
    _make_pack(tmp_path)
    if wrong_name == "Advisories.csv":
        (tmp_path / "advisories.csv").write_bytes(b"")
        (tmp_path / "advisories.csv").rename(tmp_path / "Advisories.csv")
    elif wrong_name == "PACK.toml":
        (tmp_path / "pack.toml").rename(tmp_path / "PACK.toml")
    else:
        (tmp_path / "taxa.csv").rename(tmp_path / wrong_name)
    with pytest.raises(InvalidPackError, match="case mismatch"):
        read_pack_bytes(tmp_path)


# ---- T4: quota ---------------------------------------------------------


def test_read_ignores_non_allowlist_size(tmp_path: Path) -> None:
    _make_pack(tmp_path)
    # 5 MiB non-allowlist file at root
    (tmp_path / "bigfile.bin").write_bytes(b"X" * (5 * 1024 * 1024))
    allowlist_size = sum(
        len((tmp_path / f).read_bytes())
        for f in (
            "pack.toml",
            "taxa.csv",
            "names.csv",
            "hazards.csv",
            "datasets.csv",
            "sources.csv",
        )
    )
    files = read_pack_bytes(tmp_path, max_bytes=allowlist_size + 10)
    assert "bigfile.bin" not in files


def test_read_quota_across_files(tmp_path: Path) -> None:
    _make_pack(tmp_path)
    allowlist_size = sum(
        len((tmp_path / f).read_bytes())
        for f in (
            "pack.toml",
            "taxa.csv",
            "names.csv",
            "hazards.csv",
            "datasets.csv",
            "sources.csv",
        )
    )
    with pytest.raises(PackTooLargeError, match="max_bytes"):
        read_pack_bytes(tmp_path, max_bytes=allowlist_size - 1)


def test_read_quota_exact_boundary_ok(tmp_path: Path) -> None:
    _make_pack(tmp_path)
    allowlist_size = sum(
        len((tmp_path / f).read_bytes())
        for f in (
            "pack.toml",
            "taxa.csv",
            "names.csv",
            "hazards.csv",
            "datasets.csv",
            "sources.csv",
        )
    )
    files = read_pack_bytes(tmp_path, max_bytes=allowlist_size)
    assert len(files) == 6


def test_read_quota_exact_boundary_fail(tmp_path: Path) -> None:
    _make_pack(tmp_path)
    allowlist_size = sum(
        len((tmp_path / f).read_bytes())
        for f in (
            "pack.toml",
            "taxa.csv",
            "names.csv",
            "hazards.csv",
            "datasets.csv",
            "sources.csv",
        )
    )
    with pytest.raises(PackTooLargeError, match="max_bytes"):
        read_pack_bytes(tmp_path, max_bytes=allowlist_size - 1)


def test_read_rejects_growth_during_read(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _make_pack(tmp_path)
    original = files_module._os_read
    state = {"triggered": False}

    def fake_read(fd: int, n: int) -> bytes:
        if not state["triggered"]:
            state["triggered"] = True
            return original(fd, n) + b"X" * 500
        return original(fd, n)

    monkeypatch.setattr(files_module, "_os_read", fake_read)
    # Budget big enough for pack.toml fstat, too small for pack.toml + 500.
    pack_toml_size = (tmp_path / "pack.toml").stat().st_size
    with pytest.raises(PackTooLargeError, match="max_bytes"):
        read_pack_bytes(tmp_path, max_bytes=pack_toml_size + 100)


# ---- T5: byte-exact ----------------------------------------------------


def test_read_returns_crlf_unmodified(tmp_path: Path) -> None:
    _make_pack(tmp_path)
    crlf_content = b"a\r\nb\r\nc\r\n"
    (tmp_path / "sources.csv").write_bytes(crlf_content)
    files = read_pack_bytes(tmp_path)
    assert files["sources.csv"] == crlf_content


def test_read_returns_non_utf8_bytes(tmp_path: Path) -> None:
    _make_pack(tmp_path)
    raw = b"\xff\xfe\x00\x01"
    (tmp_path / "sources.csv").write_bytes(raw)
    files = read_pack_bytes(tmp_path)
    assert files["sources.csv"] == raw


def test_read_returns_zero_byte_file(tmp_path: Path) -> None:
    _make_pack(tmp_path)
    (tmp_path / "taxa.csv").write_bytes(b"")
    files = read_pack_bytes(tmp_path)
    assert files["taxa.csv"] == b""


# ---- T6: determinism ---------------------------------------------------


def test_read_key_order_deterministic(tmp_path: Path) -> None:
    _make_pack(tmp_path)
    a = list(read_pack_bytes(tmp_path).keys())
    b = list(read_pack_bytes(tmp_path).keys())
    assert a == b


def test_read_file_creation_order_irrelevant(tmp_path: Path) -> None:
    def _create_in_order(order: list[str], name: str) -> Path:
        d = tmp_path / name
        d.mkdir()
        (d / "pack.toml").write_text(
            'name = "p"\nversion = "1.0.0"\nschema_version = 1\nengine_min = "0.0.0"\n',
            encoding="utf-8",
        )
        for table in order:
            spec = TABLES[table]
            assert spec.filename is not None
            (d / spec.filename).write_bytes(_header_bytes(table))
        return d

    a = _create_in_order(list(REQUIRED_TABLES), "pack_forward")
    b = _create_in_order(list(reversed(REQUIRED_TABLES)), "pack_reverse")
    assert list(read_pack_bytes(a).keys()) == list(read_pack_bytes(b).keys())


# ---- T7: key format ----------------------------------------------------


def test_read_facts_key_uses_forward_slash(tmp_path: Path) -> None:
    _make_pack(tmp_path, overrides={"facts/T000000001.csv": _header_bytes("facts")})
    files = read_pack_bytes(tmp_path)
    assert "facts/T000000001.csv" in files
    assert "\\" not in "".join(files.keys())


# ---- T8: name sanitization ---------------------------------------------


@pytest.mark.skipif(
    os.name == "nt",
    reason="NTFS rejects control characters in filenames",
)
def test_read_error_message_sanitizes_control_char(tmp_path: Path) -> None:
    _make_pack(tmp_path)
    (tmp_path / "facts").mkdir()
    weird = "facts/bad\x07name.csv"
    (tmp_path / weird).write_bytes(b"x")
    with pytest.raises(PackTableInvalidError) as exc_info:
        read_pack_bytes(tmp_path)
    msg = str(exc_info.value)
    assert "\x07" not in msg, f"raw control char in message: {msg!r}"
    assert "\\x07" in msg or "x07" in msg


@pytest.mark.skipif(
    os.name == "nt",
    reason="NTFS rejects control characters in filenames",
)
def test_read_error_preserves_raw_name(tmp_path: Path) -> None:
    _make_pack(tmp_path)
    (tmp_path / "facts").mkdir()
    weird = "facts/bad\x07name.csv"
    (tmp_path / weird).write_bytes(b"x")
    with pytest.raises(PackTableInvalidError) as exc_info:
        read_pack_bytes(tmp_path)
    # The raw name (with control char) must be preserved in .file
    assert exc_info.value.file is not None
    assert "\x07" in exc_info.value.file


# ---- T9: unreadable file -----------------------------------------------


@pytest.mark.skipif(
    os.name == "nt",
    reason="chmod on Windows only toggles the read-only bit; file stays readable",
)
@pytest.mark.skipif(
    hasattr(os, "getuid") and os.getuid() == 0,
    reason="running as root; chmod bypassed",
)
def test_read_unreadable_file(tmp_path: Path) -> None:
    _make_pack(tmp_path)
    target = tmp_path / "sources.csv"
    target.chmod(0o000)
    try:
        with pytest.raises(InvalidPackError, match="cannot open"):
            read_pack_bytes(tmp_path)
    finally:
        target.chmod(0o600)


# ---- T10: FIFO ---------------------------------------------------------


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="os.mkfifo unavailable")
def test_read_fifo_does_not_block(tmp_path: Path) -> None:
    _make_pack(tmp_path)
    fifo_path = tmp_path / "taxa.csv"
    fifo_path.unlink()
    os.mkfifo(fifo_path)

    result: dict[str, object] = {"done": False, "error": None}

    def worker() -> None:
        try:
            read_pack_bytes(tmp_path, max_bytes=1024 * 1024)
        except BaseException as exc:
            result["error"] = exc
        finally:
            result["done"] = True

    t = threading.Thread(target=worker, daemon=True)
    t.start()
    t.join(timeout=5.0)
    if not result["done"]:
        pytest.fail("read_pack_bytes blocked on FIFO")
    # We expect a PackError because FIFO is not S_ISREG after fstat.
    expected = (InvalidPackError, PackTableInvalidError, PackTooLargeError)
    assert isinstance(result["error"], expected), f"unexpected outcome: error={result['error']!r}"
