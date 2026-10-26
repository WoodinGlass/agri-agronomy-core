"""Deterministic SQLite build: schema, hash, reproducibility."""

from __future__ import annotations

import contextlib
import hashlib
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path

import pytest

from agri_core.pack import (
    TABLES,
    PackError,
    PackFeatureUnsupportedError,
    PackHashMismatchError,
    PackManifest,
    PackTableInvalidError,
    compute_pack_hash,
    read_pack_bytes,
    sqlite_schema,
)
from agri_core.pack.sqlite_schema import (
    APPLICATION_ID,
    BUILT_BY_PREFIX,
    DDL_SHA256,
    SQLITE_SCHEMA_VERSION,
    build_sqlite_bytes,
    write_built_pack,
)

pytestmark = pytest.mark.contract


_PINNED_DDL_SHA256 = "468260bdf1a7f0d1fbbb9e11b70f9453ee7fe8fe0dbe011bb5803d584fbc9b9d"

_SAMPLE = Path(__file__).resolve().parents[2] / "src" / "agri_core" / "_samples" / "sample_pack"


# ---- fixtures ----------------------------------------------------------


def _source_pack() -> dict[str, bytes]:
    return dict(read_pack_bytes(_SAMPLE))


def _source_pack_without_hash() -> dict[str, bytes]:
    """Sample pack with content_hash stripped from pack.toml.

    Tests that mutate files (add advisories, inject duplicate rows) would
    otherwise fail at the build-time content_hash check before reaching
    the error they are testing for.
    """
    files = _source_pack()
    toml = files["pack.toml"].decode("utf-8")
    kept = [ln for ln in toml.splitlines() if not ln.startswith("content_hash")]
    files["pack.toml"] = ("\n".join(kept) + "\n").encode("utf-8")
    return files


# ---- 1. SQLite header / pragmas ---------------------------------------


def test_application_id_bytes_are_agri() -> None:
    assert APPLICATION_ID == 0x61677269
    assert APPLICATION_ID.to_bytes(4, "big") == b"agri"


def test_ddl_sha256_pinned() -> None:
    assert DDL_SHA256 == _PINNED_DDL_SHA256, (
        "DDL changed without bumping SQLITE_SCHEMA_VERSION and updating the pin."
    )


def test_build_returns_bytes_with_sqlite_magic() -> None:
    out = build_sqlite_bytes(_source_pack())
    assert isinstance(out, bytes)
    assert out.startswith(b"SQLite format 3\x00")
    assert len(out) > 4096


def test_user_version_matches_schema_version() -> None:
    conn = _open_bytes(build_sqlite_bytes(_source_pack()))
    try:
        uv = conn.execute("PRAGMA user_version").fetchone()[0]
        ai = conn.execute("PRAGMA application_id").fetchone()[0]
        ps = conn.execute("PRAGMA page_size").fetchone()[0]
    finally:
        conn.close()
    assert uv == SQLITE_SCHEMA_VERSION == 1
    assert ai == APPLICATION_ID
    assert ps == 4096


# ---- 2. Schema shape ---------------------------------------------------


def _open_bytes(data: bytes) -> sqlite3.Connection:
    fd, path = tempfile.mkstemp(suffix=".sqlite")
    with os.fdopen(fd, "wb") as f:
        f.write(data)
    _open_bytes._paths.append(path)  # type: ignore[attr-defined]
    return sqlite3.connect(path)


_open_bytes._paths = []  # type: ignore[attr-defined]


@pytest.fixture(autouse=True)
def _cleanup_db_files():
    yield
    for p in _open_bytes._paths:  # type: ignore[attr-defined]
        with contextlib.suppress(OSError):
            os.unlink(p)
    _open_bytes._paths.clear()  # type: ignore[attr-defined]


def test_has_all_seven_tables() -> None:
    conn = _open_bytes(build_sqlite_bytes(_source_pack()))
    try:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
    finally:
        conn.close()
    names = [r[0] for r in rows]
    assert names == [
        "datasets",
        "facts",
        "hazards",
        "metadata",
        "names",
        "sources",
        "taxa",
    ]


def test_has_two_facts_indexes() -> None:
    conn = _open_bytes(build_sqlite_bytes(_source_pack()))
    try:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='facts' "
            "AND name NOT LIKE 'sqlite_%' ORDER BY name"
        ).fetchall()
    finally:
        conn.close()
    assert [r[0] for r in rows] == ["idx_facts_parameter", "idx_facts_taxon_param"]


@pytest.mark.parametrize("table_name", ["taxa", "names", "facts", "hazards", "datasets", "sources"])
def test_ddl_columns_match_row_model(table_name: str) -> None:
    spec = TABLES[table_name]
    conn = _open_bytes(build_sqlite_bytes(_source_pack()))
    try:
        cols = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    finally:
        conn.close()
    ddl_cols = [c[1] for c in cols]
    spec_cols = [c.name for c in spec.columns]
    assert ddl_cols == spec_cols


# ---- 3. Row counts + metadata -----------------------------------------


def test_row_counts_match_source_tables() -> None:
    conn = _open_bytes(build_sqlite_bytes(_source_pack()))
    try:
        counts = {}
        for table_name in ("taxa", "names", "hazards", "datasets", "sources", "facts"):
            counts[table_name] = conn.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0]
    finally:
        conn.close()
    # Sample pack has 8 taxa, 19 names, 2 hazards, 1 dataset, 3 sources, 20 facts
    assert counts == {
        "taxa": 8,
        "names": 19,
        "hazards": 2,
        "datasets": 1,
        "sources": 3,
        "facts": 20,
    }


def test_metadata_has_eight_keys() -> None:
    conn = _open_bytes(build_sqlite_bytes(_source_pack()))
    try:
        rows = dict(conn.execute("SELECT key, value FROM metadata").fetchall())
    finally:
        conn.close()
    assert set(rows.keys()) == {
        "name",
        "version",
        "schema_version",
        "engine_min",
        "dictionary_min",
        "synthetic",
        "content_hash",
        "built_by",
    }
    assert rows["name"] == "sample"
    assert rows["version"] == "0.1.0"
    assert rows["synthetic"] == "1"
    assert rows["built_by"].startswith(BUILT_BY_PREFIX + " ")


# ---- 4. Determinism ---------------------------------------------------


def test_determinism_same_input() -> None:
    files = _source_pack()
    a = build_sqlite_bytes(files)
    b = build_sqlite_bytes(files)
    assert a == b


def test_determinism_across_subprocesses(tmp_path: Path) -> None:
    """Build twice in separate processes with different env; compare bytes."""
    src = _SAMPLE
    a_src = tmp_path / "a_src"
    b_src = tmp_path / "b_src"
    shutil.copytree(src, a_src)
    shutil.copytree(src, b_src)

    script = textwrap.dedent(
        """
        import sys
        from pathlib import Path
        from agri_core.pack.files import read_pack_bytes
        from agri_core.pack.sqlite_schema import build_sqlite_bytes
        src = Path(sys.argv[1])
        out = Path(sys.argv[2])
        out.write_bytes(build_sqlite_bytes(read_pack_bytes(src)))
        """
    ).strip()

    a_out = tmp_path / "a.sqlite"
    b_out = tmp_path / "b.sqlite"

    env_a = {**os.environ, "PYTHONHASHSEED": "1", "TZ": "UTC", "LANG": "C.UTF-8"}
    env_b = {**os.environ, "PYTHONHASHSEED": "2", "TZ": "Asia/Tokyo", "LANG": "en_US.UTF-8"}

    r1 = subprocess.run(
        [sys.executable, "-c", script, str(a_src), str(a_out)],
        capture_output=True,
        text=True,
        cwd=Path(__file__).resolve().parents[2],
        env=env_a,
        timeout=120,
    )
    if r1.returncode != 0:
        raise AssertionError(f"subprocess A failed: {r1.stdout}\n{r1.stderr}")

    r2 = subprocess.run(
        [sys.executable, "-c", script, str(b_src), str(b_out)],
        capture_output=True,
        text=True,
        cwd=Path(__file__).resolve().parents[2],
        env=env_b,
        timeout=120,
    )
    if r2.returncode != 0:
        raise AssertionError(f"subprocess B failed: {r2.stdout}\n{r2.stderr}")

    a = a_out.read_bytes()
    b = b_out.read_bytes()
    assert a == b, f"bytes differ: {len(a)} vs {len(b)}"


# ---- 5. Content fidelity ---------------------------------------------


def test_list_cells_sorted_using_real_vocab() -> None:
    conn = _open_bytes(build_sqlite_bytes(_source_pack()))
    try:
        # T000000001 in the sample pack has uses=["vegetable"]
        uses = conn.execute("SELECT uses FROM taxa WHERE taxon_id='T000000001'").fetchone()[0]
    finally:
        conn.close()
    assert uses == "vegetable"


def test_json_cells_canonical() -> None:
    import json as _json

    from agri_core.models.canonical import canonical_json

    conn = _open_bytes(build_sqlite_bytes(_source_pack()))
    try:
        scopes = [r[0] for r in conn.execute("SELECT scope FROM facts LIMIT 10").fetchall()]
        values = [r[0] for r in conn.execute("SELECT value FROM facts LIMIT 10").fetchall()]
    finally:
        conn.close()

    for cell in scopes + values:
        parsed = _json.loads(cell)
        assert canonical_json(parsed).decode("utf-8") == cell, (
            f"cell not canonical: stored={cell!r} "
            f"recomputed={canonical_json(parsed).decode('utf-8')!r}"
        )

    zero_cell = canonical_json({"x": -0.0}).decode("utf-8")
    assert "-0" not in zero_cell, f"negative zero not normalized: {zero_cell!r}"


def test_non_ascii_preserved() -> None:
    conn = _open_bytes(build_sqlite_bytes(_source_pack()))
    try:
        names = [r[0] for r in conn.execute("SELECT name FROM names").fetchall()]
    finally:
        conn.close()
    assert "\u30c6\u30b9\u30c8\u4e00\u5e74\u8349" in names


# ---- 6. Fail-closed paths ---------------------------------------------


def test_advisories_with_data_fails_closed() -> None:
    files = _source_pack_without_hash()
    files["advisories.csv"] = (
        b"fact_id,reason,replacement_fact_id,issued_at,issued_by\nF00000000001,x,,2026-01-01,r\n"
    )
    with pytest.raises(PackFeatureUnsupportedError):
        build_sqlite_bytes(files)


def test_advisories_whitespace_only_ok() -> None:
    files = _source_pack_without_hash()
    files["advisories.csv"] = b"\n\n"
    out = build_sqlite_bytes(files)
    assert out.startswith(b"SQLite format 3\x00")


def test_content_hash_mismatch_fails_closed() -> None:
    files = _source_pack()
    # Build manifest declares a stale content_hash by mutating sources.csv
    # while keeping pack.toml as-is; the manifest content_hash then does
    # not match the recomputed hash.
    files["sources.csv"] = files["sources.csv"] + (
        b"S999,https://example.org/x,CC0-1.0,yes,2026-01-01,x\n"
    )
    with pytest.raises(PackHashMismatchError):
        build_sqlite_bytes(files)


def test_duplicate_pk_wrapped_as_table_invalid() -> None:
    # Inject a duplicate taxon row. read_table does not enforce PK
    # uniqueness (that is the loader's job), so we expect IntegrityError
    # from sqlite to be wrapped as PackTableInvalidError.
    files = _source_pack_without_hash()
    taxa = TABLES["taxa"]
    assert taxa.filename is not None
    first_line, rest = files[taxa.filename].split(b"\n", 1)
    first_row = rest.split(b"\n", 1)[0]
    files[taxa.filename] = first_line + b"\n" + first_row + b"\n" + first_row + b"\n"
    with pytest.raises(PackTableInvalidError):
        build_sqlite_bytes(files)


def test_pipe_in_list_item_rejected() -> None:
    from agri_core.pack.sqlite_schema import _sql_value
    from agri_core.pack.tables import ColumnSpec

    col = ColumnSpec(name="uses", type="list_str", nullable=False)
    with pytest.raises(PackTableInvalidError, match="pipe encoding"):
        _sql_value(["a|b"], col)


def test_sqlite_version_guard(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sqlite_schema, "_sqlite_version", lambda: (3, 26, 0))
    with pytest.raises(RuntimeError, match=r"3\.27"):
        build_sqlite_bytes(_source_pack())


# ---- 7. write_built_pack (filesystem) --------------------------------


def test_write_built_pack_creates_two_files(tmp_path: Path) -> None:
    files = _source_pack()
    out = tmp_path / "built"
    write_built_pack(files, out_dir=out)
    assert (out / "pack.sqlite").is_file()
    assert (out / "pack.toml").is_file()
    assert not (out / "pack.sqlite.tmp").exists()
    assert not (out / "pack.toml.tmp").exists()


def test_write_built_pack_toml_roundtrips_via_pydantic(tmp_path: Path) -> None:
    import tomllib

    files = _source_pack()
    out = tmp_path / "built"
    write_built_pack(files, out_dir=out)
    parsed = tomllib.loads((out / "pack.toml").read_text(encoding="utf-8"))
    restored = PackManifest.model_validate(parsed)
    assert restored.artifact_sha256 is not None
    assert restored.sqlite_schema_version == SQLITE_SCHEMA_VERSION
    assert restored.built_by.startswith(BUILT_BY_PREFIX + " ")


def test_write_built_pack_artifact_and_content_hash_match(tmp_path: Path) -> None:
    import tomllib

    files = _source_pack()
    out = tmp_path / "built"
    write_built_pack(files, out_dir=out)
    parsed = tomllib.loads((out / "pack.toml").read_text(encoding="utf-8"))
    sqlite_bytes = (out / "pack.sqlite").read_bytes()
    expected_artifact = "sha256:" + hashlib.sha256(sqlite_bytes).hexdigest()
    assert parsed["artifact_sha256"] == expected_artifact
    assert parsed["content_hash"] == compute_pack_hash(_SAMPLE)


def test_write_built_pack_rejects_out_dir_with_taxa_csv(tmp_path: Path) -> None:
    files = _source_pack()
    out = tmp_path / "source"
    out.mkdir()
    (out / "taxa.csv").write_bytes(files["taxa.csv"])
    with pytest.raises(PackError, match="source pack"):
        write_built_pack(files, out_dir=out)


def test_write_built_pack_two_outputs_identical(tmp_path: Path) -> None:
    files = _source_pack()
    a = tmp_path / "a"
    b = tmp_path / "b"
    write_built_pack(files, out_dir=a)
    write_built_pack(files, out_dir=b)
    assert (a / "pack.sqlite").read_bytes() == (b / "pack.sqlite").read_bytes()
    assert (a / "pack.toml").read_bytes() == (b / "pack.toml").read_bytes()


def test_write_built_pack_cleans_tmp_on_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    files = _source_pack()
    out = tmp_path / "built"
    call_count = {"n": 0}
    real_replace = os.replace

    def boom(src, dst):
        call_count["n"] += 1
        if call_count["n"] == 2:  # fail on the pack.toml replace, not the sqlite one
            raise OSError("simulated second replace failure")
        return real_replace(src, dst)

    monkeypatch.setattr(os, "replace", boom)
    with pytest.raises(OSError, match="simulated second replace failure"):
        write_built_pack(files, out_dir=out)
    # sqlite was written successfully, pack.toml was not; both tmp files
    # must be cleaned up.
    assert (out / "pack.sqlite").is_file()
    assert not (out / "pack.toml").is_file()
    assert not (out / "pack.sqlite.tmp").exists()
    assert not (out / "pack.toml.tmp").exists()
