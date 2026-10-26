"""Build a deterministic SQLite pack from allowlist bytes (M6)."""

from __future__ import annotations

import contextlib
import hashlib
import sqlite3
import tempfile
from collections.abc import Mapping
from datetime import date, datetime
from pathlib import Path
from typing import Any

from agri_core import __version__
from agri_core.models.canonical import canonical_json
from agri_core.pack.errors import (
    InvalidPackError,
    PackError,
    PackFeatureUnsupportedError,
    PackHashMismatchError,
    PackTableInvalidError,
)
from agri_core.pack.manifest import PackManifest
from agri_core.pack.tables import TABLES, ColumnSpec, TableSpec, read_table
from agri_core.pack.toml_writer import dump_manifest
from agri_core.pack.verify import hash_pack_files

APPLICATION_ID: int = 0x61677269
SQLITE_SCHEMA_VERSION: int = 1
BUILT_BY_PREFIX: str = "agri-core"

_MIN_SQLITE_VERSION_FOR_VACUUM_INTO = (3, 27, 0)

# DDL is pinned by DDL_SHA256. Do not edit without bumping SQLITE_SCHEMA_VERSION
# and updating the pin in tests/contract/test_sqlite_build.py.
_TABLE_DDL = (
    "CREATE TABLE taxa ("
    "taxon_id TEXT PRIMARY KEY,"
    "rank TEXT NOT NULL,"
    "scientific_name TEXT NOT NULL,"
    "accepted_name TEXT,"
    "organism_group TEXT NOT NULL,"
    "archetype TEXT NOT NULL,"
    "uses TEXT NOT NULL,"
    "traits TEXT NOT NULL,"
    "parent_id TEXT,"
    "external_ids TEXT,"
    "src TEXT,"
    "dataset_id TEXT"
    ") WITHOUT ROWID;\n"
    "CREATE TABLE names ("
    "taxon_id TEXT NOT NULL,"
    "name TEXT NOT NULL,"
    "language TEXT NOT NULL,"
    "script TEXT NOT NULL,"
    "kind TEXT NOT NULL,"
    "preferred INTEGER NOT NULL,"
    "src TEXT,"
    "dataset_id TEXT,"
    "PRIMARY KEY (taxon_id,name,language,script,kind)"
    ") WITHOUT ROWID;\n"
    "CREATE TABLE facts ("
    "fact_id TEXT PRIMARY KEY,"
    "taxon_id TEXT NOT NULL,"
    "parameter TEXT NOT NULL,"
    "phase TEXT,"
    "value TEXT NOT NULL,"
    "scope TEXT NOT NULL,"
    "provenance_kind TEXT NOT NULL,"
    "src TEXT,"
    "dataset_id TEXT,"
    "locator TEXT,"
    "evidence TEXT NOT NULL,"
    "status TEXT NOT NULL,"
    "reviewed_by TEXT,"
    "reviewed_at TEXT,"
    "superseded_by TEXT"
    ") WITHOUT ROWID;\n"
    "CREATE TABLE hazards ("
    "taxon_id TEXT NOT NULL,"
    "hazard_code TEXT NOT NULL,"
    "severity TEXT NOT NULL,"
    "reason TEXT NOT NULL,"
    "as_of TEXT NOT NULL,"
    "authority TEXT NOT NULL,"
    "src TEXT,"
    "dataset_id TEXT,"
    "PRIMARY KEY (taxon_id,hazard_code)"
    ") WITHOUT ROWID;\n"
    "CREATE TABLE datasets ("
    "dataset_id TEXT PRIMARY KEY,"
    "name TEXT NOT NULL,"
    "version TEXT NOT NULL,"
    "license TEXT NOT NULL,"
    "checksum TEXT NOT NULL,"
    "url TEXT,"
    "locator TEXT,"
    "access_date TEXT NOT NULL"
    ") WITHOUT ROWID;\n"
    "CREATE TABLE sources ("
    "id TEXT PRIMARY KEY,"
    "url TEXT NOT NULL,"
    "license TEXT NOT NULL,"
    "commercial_use TEXT NOT NULL,"
    "access_date TEXT NOT NULL,"
    "citation TEXT NOT NULL"
    ") WITHOUT ROWID;\n"
    "CREATE TABLE metadata ("
    "key TEXT PRIMARY KEY,"
    "value TEXT NOT NULL"
    ") WITHOUT ROWID"
)

_INDEX_DDL = (
    "CREATE INDEX idx_facts_taxon_param ON facts(taxon_id,parameter)",
    "CREATE INDEX idx_facts_parameter ON facts(parameter)",
)

_DDL_FOR_HASH = _TABLE_DDL + "\n" + "\n".join(_INDEX_DDL) + "\n"
DDL_SHA256: str = hashlib.sha256(_DDL_FOR_HASH.encode("utf-8")).hexdigest()

_TABLE_INSERT_ORDER = ("taxa", "names", "hazards", "datasets", "sources")


def _sqlite_version() -> tuple[int, int, int]:
    return sqlite3.sqlite_version_info


def _parse_manifest(pack_toml: bytes) -> PackManifest:
    import tomllib

    try:
        data = tomllib.loads(pack_toml.decode("utf-8"))
    except (UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
        raise InvalidPackError(f"pack.toml: {exc}", file="pack.toml") from exc
    try:
        return PackManifest.model_validate(data)
    except ValueError as exc:
        raise InvalidPackError(f"pack.toml: {exc}", file="pack.toml") from exc


def _sql_value(value: Any, col: ColumnSpec) -> Any:
    if value is None:
        return None
    if col.type == "str":
        return value
    if col.type == "bool":
        return 1 if value else 0
    if col.type == "int":
        if isinstance(value, bool):
            return 1 if value else 0
        return value
    if col.type == "float":
        return float(value)
    if col.type == "date":
        if isinstance(value, datetime):
            return value.isoformat()
        if isinstance(value, date):
            return value.isoformat()
        return value
    if col.type == "list_str":
        items = list(value)
        for item in items:
            if "|" in item:
                raise PackTableInvalidError(
                    f"list item in column {col.name!r} contains '|'; pipe encoding is not lossless",
                    key=col.name,
                )
        return "|".join(sorted(items))
    if col.type == "dict_str_str":
        if not isinstance(value, dict):
            raise PackTableInvalidError(
                f"expected dict, got {type(value).__name__}",
                key=col.name,
            )
        return canonical_json(value).decode("utf-8")
    if col.type == "json":
        return canonical_json(value).decode("utf-8")
    raise PackTableInvalidError(f"unknown column type {col.type!r}", key=col.name)


def _parse_all_tables(files: Mapping[str, bytes]) -> dict[str, Any]:
    tables: dict[str, Any] = {}
    for name in ("taxa", "names", "hazards", "datasets", "sources"):
        spec = TABLES[name]
        assert spec.filename is not None
        tables[name] = read_table(spec, files[spec.filename], source_name=spec.filename)
    for relpath in sorted(files):
        if not relpath.startswith("facts/") or not relpath.endswith(".csv"):
            continue
        tables[relpath] = read_table(TABLES["facts"], files[relpath], source_name=relpath)
    return tables


def _insert_rows(
    conn: sqlite3.Connection,
    table_name: str,
    spec: TableSpec,
    rows: tuple[Mapping[str, Any], ...],
) -> None:
    col_names = [c.name for c in spec.columns]
    placeholders = ",".join("?" * len(col_names))
    insert_sql = f"INSERT INTO {table_name} ({','.join(col_names)}) VALUES ({placeholders})"
    sorted_rows = sorted(
        rows,
        key=lambda r: tuple(r[k] for k in spec.primary_key) if spec.primary_key else (),
    )
    encoded = [tuple(_sql_value(r[c.name], c) for c in spec.columns) for r in sorted_rows]
    try:
        conn.executemany(insert_sql, encoded)
    except sqlite3.IntegrityError as exc:
        raise PackTableInvalidError(
            f"integrity violation in {table_name}: {exc}",
            file=table_name,
        ) from exc


def _insert_metadata(
    conn: sqlite3.Connection,
    manifest: PackManifest,
    content_hash: str,
) -> None:
    rows = [
        ("name", manifest.name),
        ("version", manifest.version),
        ("schema_version", str(manifest.schema_version)),
        ("engine_min", manifest.engine_min),
        ("dictionary_min", manifest.dictionary_min),
        ("synthetic", "1" if manifest.synthetic else "0"),
        ("content_hash", content_hash),
        ("built_by", f"{BUILT_BY_PREFIX} {__version__}"),
    ]
    conn.executemany("INSERT INTO metadata (key,value) VALUES (?,?)", rows)


def _build_sqlite_and_hash(files: Mapping[str, bytes]) -> tuple[bytes, str]:
    source_manifest = _parse_manifest(files["pack.toml"])
    if (
        source_manifest.artifact_sha256 is not None
        or source_manifest.sqlite_schema_version is not None
        or source_manifest.built_by is not None
    ):
        raise PackError(
            "cannot build from a manifest that already declares build fields "
            "(artifact_sha256 / sqlite_schema_version / built_by)"
        )

    content_hash = hash_pack_files(files)
    if source_manifest.content_hash is not None and source_manifest.content_hash != content_hash:
        raise PackHashMismatchError(
            f"content_hash mismatch: manifest={source_manifest.content_hash} "
            f"computed={content_hash}. Run `agri-core pack lock` first.",
            file="pack.toml",
        )

    if files.get("advisories.csv", b"").strip():
        raise PackFeatureUnsupportedError(
            "advisories.csv has non-whitespace content; unsupported until M8",
            file="advisories.csv",
        )

    if _sqlite_version() < _MIN_SQLITE_VERSION_FOR_VACUUM_INTO:
        raise RuntimeError(
            f"sqlite {sqlite3.sqlite_version} < required "
            f"{'.'.join(map(str, _MIN_SQLITE_VERSION_FOR_VACUUM_INTO))} (VACUUM INTO)"
        )

    tables = _parse_all_tables(files)

    conn = sqlite3.connect(":memory:")
    try:
        conn.execute("PRAGMA page_size = 4096")
        conn.execute(f"PRAGMA application_id = {APPLICATION_ID}")
        conn.execute(f"PRAGMA user_version = {SQLITE_SCHEMA_VERSION}")
        conn.executescript(_TABLE_DDL)
        for table_name in _TABLE_INSERT_ORDER:
            spec = TABLES[table_name]
            _insert_rows(conn, table_name, spec, tables[table_name].rows)
        facts_spec = TABLES["facts"]
        for relpath in sorted(tables):
            if not relpath.startswith("facts/"):
                continue
            _insert_rows(conn, "facts", facts_spec, tables[relpath].rows)
        _insert_metadata(conn, source_manifest, content_hash)
        for stmt in _INDEX_DDL:
            conn.execute(stmt)
        conn.commit()

        with tempfile.TemporaryDirectory() as td:
            out_path = Path(td) / "pack.sqlite"
            safe_path = str(out_path).replace("'", "''")
            conn.execute(f"VACUUM INTO '{safe_path}'")
            conn.close()
            return out_path.read_bytes(), content_hash
    finally:
        with contextlib.suppress(sqlite3.ProgrammingError):
            conn.close()


def build_sqlite_bytes(files: Mapping[str, bytes]) -> bytes:
    """Build a SQLite file from allowlist bytes and return its bytes.

    Verifies content_hash (if present) against hash_pack_files(files);
    fail-closes on advisories content; requires sqlite >= 3.27 for
    VACUUM INTO. Does NOT run cross-row validation (callers are expected
    to validate with load_knowledge_set first).
    """
    sqlite_bytes, _ = _build_sqlite_and_hash(files)
    return sqlite_bytes


def write_built_pack(files: Mapping[str, bytes], *, out_dir: Path) -> None:
    """Write <out_dir>/pack.sqlite and <out_dir>/pack.toml (built manifest).

    Each file is written to <name>.tmp then os.replace()'d into place. If
    the second replace fails, pack.sqlite is already on disk and pack.toml
    is not; check consistency with load_knowledge_set. On any error the
    .tmp files are removed. Refuses to run if <out_dir> contains taxa.csv
    (a source pack) so it never overwrites source files.
    """
    out_dir = Path(out_dir)
    if (out_dir / "taxa.csv").exists():
        raise PackError(
            f"out_dir {out_dir} looks like a source pack (contains taxa.csv); "
            f"refusing to write built files here"
        )
    out_dir.mkdir(parents=True, exist_ok=True)

    sqlite_bytes, content_hash = _build_sqlite_and_hash(files)
    artifact_sha256 = "sha256:" + hashlib.sha256(sqlite_bytes).hexdigest()

    source_manifest = _parse_manifest(files["pack.toml"])
    built_manifest = PackManifest.model_validate(
        {
            **source_manifest.model_dump(),
            "content_hash": content_hash,
            "artifact_sha256": artifact_sha256,
            "sqlite_schema_version": SQLITE_SCHEMA_VERSION,
            "built_by": f"{BUILT_BY_PREFIX} {__version__}",
        }
    )

    sql_target = out_dir / "pack.sqlite"
    sql_tmp = out_dir / "pack.sqlite.tmp"
    toml_target = out_dir / "pack.toml"
    toml_tmp = out_dir / "pack.toml.tmp"
    try:
        sql_tmp.write_bytes(sqlite_bytes)
        import os as _os

        _os.replace(sql_tmp, sql_target)
        toml_tmp.write_bytes(dump_manifest(built_manifest))
        _os.replace(toml_tmp, toml_target)
    finally:
        for t in (sql_tmp, toml_tmp):
            with contextlib.suppress(OSError):
                t.unlink(missing_ok=True)


__all__ = [
    "APPLICATION_ID",
    "BUILT_BY_PREFIX",
    "DDL_SHA256",
    "SQLITE_SCHEMA_VERSION",
    "build_sqlite_bytes",
    "write_built_pack",
]
