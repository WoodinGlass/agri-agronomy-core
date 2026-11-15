//! Pack build: SQLite generation (mirror of `sqlite_schema.py`).
//!
//! Hybrid scope (A1b): Rust owns CSV parse -> SQLite write; Python owns
//! `PackManifest` Pydantic validation. This module extracts the manifest
//! fields the build path needs (name, version, schema_version, engine_min,
//! dictionary_min, synthetic, content_hash, hash_alg, build-field sentinels)
//! but does NOT validate them (callers validated via `validate_pack` first;
//! direct callers get field-presence errors only).
//!
//! Byte-identical goal: `content_hash` must match Python (proven in Phase B).
//! `artifact_sha256` may differ from Python (SQLite writer version in header).

use std::collections::HashMap;

use rusqlite::types::Value as SqlVal;
use rusqlite::Connection;
use sha2::{Digest, Sha256};

use crate::canonical::canonical_json_rfc8785;
use crate::pack::errors::PackError;
use crate::pack::tables::{read_table, table_spec, CellValue, ColumnSpec, Table};
use crate::pack::verify::hash_pack_files;

// ---- Public constants (mirror sqlite_schema.py) ----

pub const APPLICATION_ID: i64 = 0x61677269;
pub const SQLITE_SCHEMA_VERSION: i64 = 1;
pub const BUILT_BY_PREFIX: &str = "agri-core";

/// SQLite version minimum for `VACUUM INTO` (3.27.0 as number 3027000).
const MIN_SQLITE_VERSION_NUMBER: i32 = 3027000;

// ---- DDL (byte-identical to Python `_TABLE_DDL`) ----

const _TABLE_DDL: &str = "CREATE TABLE taxa (\
taxon_id TEXT PRIMARY KEY,\
rank TEXT NOT NULL,\
scientific_name TEXT NOT NULL,\
accepted_name TEXT,\
organism_group TEXT NOT NULL,\
archetype TEXT NOT NULL,\
uses TEXT NOT NULL,\
traits TEXT NOT NULL,\
parent_id TEXT,\
external_ids TEXT,\
src TEXT,\
dataset_id TEXT\
) WITHOUT ROWID;\n\
CREATE TABLE names (\
taxon_id TEXT NOT NULL,\
name TEXT NOT NULL,\
language TEXT NOT NULL,\
script TEXT NOT NULL,\
kind TEXT NOT NULL,\
preferred INTEGER NOT NULL,\
src TEXT,\
dataset_id TEXT,\
PRIMARY KEY (taxon_id,name,language,script,kind)\
) WITHOUT ROWID;\n\
CREATE TABLE facts (\
fact_id TEXT PRIMARY KEY,\
taxon_id TEXT NOT NULL,\
parameter TEXT NOT NULL,\
phase TEXT,\
value TEXT NOT NULL,\
scope TEXT NOT NULL,\
provenance_kind TEXT NOT NULL,\
src TEXT,\
dataset_id TEXT,\
locator TEXT,\
evidence TEXT NOT NULL,\
status TEXT NOT NULL,\
reviewed_by TEXT,\
reviewed_at TEXT,\
superseded_by TEXT\
) WITHOUT ROWID;\n\
CREATE TABLE hazards (\
taxon_id TEXT NOT NULL,\
hazard_code TEXT NOT NULL,\
severity TEXT NOT NULL,\
reason TEXT NOT NULL,\
as_of TEXT NOT NULL,\
authority TEXT NOT NULL,\
src TEXT,\
dataset_id TEXT,\
PRIMARY KEY (taxon_id,hazard_code)\
) WITHOUT ROWID;\n\
CREATE TABLE datasets (\
dataset_id TEXT PRIMARY KEY,\
name TEXT NOT NULL,\
version TEXT NOT NULL,\
license TEXT NOT NULL,\
checksum TEXT NOT NULL,\
url TEXT,\
locator TEXT,\
access_date TEXT NOT NULL\
) WITHOUT ROWID;\n\
CREATE TABLE sources (\
id TEXT PRIMARY KEY,\
url TEXT NOT NULL,\
license TEXT NOT NULL,\
commercial_use TEXT NOT NULL,\
access_date TEXT NOT NULL,\
citation TEXT NOT NULL\
) WITHOUT ROWID;\n\
CREATE TABLE metadata (\
key TEXT PRIMARY KEY,\
value TEXT NOT NULL\
) WITHOUT ROWID";

const _INDEX_DDL: [&str; 2] = [
    "CREATE INDEX idx_facts_taxon_param ON facts(taxon_id,parameter)",
    "CREATE INDEX idx_facts_parameter ON facts(parameter)",
];

/// SHA-256 of `_TABLE_DDL + "\n" + _INDEX_DDL.join("\n") + "\n"` (hex).
///
/// Must match Python `sqlite_schema.DDL_SHA256` = `468260bdf1a7f0d1...`.
pub fn ddl_sha256() -> String {
    let mut buf = String::with_capacity(_TABLE_DDL.len() + 256);
    buf.push_str(_TABLE_DDL);
    buf.push('\n');
    buf.push_str(&_INDEX_DDL.join("\n"));
    buf.push('\n');
    let mut h = Sha256::new();
    h.update(buf.as_bytes());
    let digest = h.finalize();
    let mut out = String::with_capacity(64);
    for b in digest.iter() {
        use std::fmt::Write as _;
        let _ = write!(out, "{b:02x}");
    }
    out
}

/// Table insert order (mirror Python `_TABLE_INSERT_ORDER`). `facts` is
/// inserted last from per-taxon files.
const TABLE_INSERT_ORDER: [&str; 5] = ["taxa", "names", "hazards", "datasets", "sources"];

// ---- Manifest field extraction ----

/// Subset of `PackManifest` fields needed by the build path.
#[derive(Debug, Clone)]
pub struct ManifestFields {
    pub name: String,
    pub version: String,
    pub schema_version: i64,
    pub engine_min: String,
    pub dictionary_min: String,
    pub content_hash: Option<String>,
    pub synthetic: bool,
    pub artifact_sha256: Option<String>,
    pub sqlite_schema_version: Option<i64>,
    pub built_by: Option<String>,
    pub hash_alg: Option<String>,
}

pub fn parse_manifest_fields(toml_bytes: &[u8]) -> Result<ManifestFields, PackError> {
    let text = std::str::from_utf8(toml_bytes).map_err(|e| {
        PackError::pack_invalid(format!("pack.toml not UTF-8: {e}")).with_file("pack.toml")
    })?;
    let parsed: toml::Value = toml::from_str(text)
        .map_err(|e| PackError::pack_invalid(format!("pack.toml: {e}")).with_file("pack.toml"))?;
    let table = parsed.as_table().ok_or_else(|| {
        PackError::pack_invalid("pack.toml: root not a table").with_file("pack.toml")
    })?;

    let get_str = |k: &str| -> Result<String, PackError> {
        table
            .get(k)
            .and_then(|v| v.as_str())
            .map(|s| s.to_string())
            .ok_or_else(|| {
                PackError::pack_invalid(format!("pack.toml: missing or non-string {k:?}"))
                    .with_file("pack.toml")
            })
    };
    let get_opt_str = |k: &str| -> Option<String> {
        table.get(k).and_then(|v| v.as_str()).map(|s| s.to_string())
    };
    let get_int = |k: &str| -> Result<i64, PackError> {
        table.get(k).and_then(|v| v.as_integer()).ok_or_else(|| {
            PackError::pack_invalid(format!("pack.toml: missing or non-int {k:?}"))
                .with_file("pack.toml")
        })
    };
    let get_opt_int = |k: &str| -> Option<i64> { table.get(k).and_then(|v| v.as_integer()) };
    let get_bool = |k: &str, default: bool| -> bool {
        table.get(k).and_then(|v| v.as_bool()).unwrap_or(default)
    };

    Ok(ManifestFields {
        name: get_str("name")?,
        version: get_str("version")?,
        schema_version: get_int("schema_version")?,
        engine_min: get_str("engine_min")?,
        dictionary_min: get_str("dictionary_min")?,
        content_hash: get_opt_str("content_hash"),
        synthetic: get_bool("synthetic", false),
        artifact_sha256: get_opt_str("artifact_sha256"),
        sqlite_schema_version: get_opt_int("sqlite_schema_version"),
        built_by: get_opt_str("built_by"),
        hash_alg: get_opt_str("hash_alg"),
    })
}

// ---- SQL value encoding (mirror _sql_value) ----

fn cell_to_sql(v: &CellValue, col: &ColumnSpec) -> Result<SqlVal, PackError> {
    let err = |msg: String| PackError::table_invalid(msg).with_key(col.name);
    match v {
        CellValue::Null => Ok(SqlVal::Null),
        CellValue::Bool(b) => Ok(SqlVal::Integer(if *b { 1 } else { 0 })),
        CellValue::Int(i) => Ok(SqlVal::Integer(*i)),
        CellValue::Float(f) => Ok(SqlVal::Real(*f)),
        CellValue::Str(s) => Ok(SqlVal::Text(s.clone())),
        CellValue::ListStr(items) => {
            for item in items {
                if item.contains('|') {
                    return Err(err(format!(
                        "list item in column {:?} contains '|'; pipe encoding is not lossless",
                        col.name
                    )));
                }
            }
            let mut sorted: Vec<&str> = items.iter().map(|s| s.as_str()).collect();
            sorted.sort();
            Ok(SqlVal::Text(sorted.join("|")))
        }
        CellValue::DictStrStr(m) => {
            let mut obj = serde_json::Map::with_capacity(m.len());
            for (k, v) in m {
                obj.insert(k.clone(), serde_json::Value::String(v.clone()));
            }
            let j = serde_json::Value::Object(obj);
            let bytes = canonical_json_rfc8785(&j).map_err(|e| err(format!("canonical: {e}")))?;
            let s = String::from_utf8(bytes).map_err(|e| err(format!("utf8: {e}")))?;
            Ok(SqlVal::Text(s))
        }
        CellValue::Json(j) => {
            let bytes = canonical_json_rfc8785(j).map_err(|e| err(format!("canonical: {e}")))?;
            let s = String::from_utf8(bytes).map_err(|e| err(format!("utf8: {e}")))?;
            Ok(SqlVal::Text(s))
        }
    }
}

// ---- Insert helpers ----

/// Sort key: primary-key columns as `Vec<String>` (lexicographic comparison).
/// All pack PK columns are `Str` in practice; `Int`/`Bool` fallbacks keep
/// the sort total if a future PK adds them.
fn sort_key(row: &std::collections::BTreeMap<String, CellValue>, pk: &[&str]) -> Vec<String> {
    pk.iter()
        .map(|k| {
            row.get(*k)
                .map(|v| match v {
                    CellValue::Str(s) => s.clone(),
                    CellValue::Int(i) => i.to_string(),
                    CellValue::Bool(b) => (if *b { "1" } else { "0" }).to_string(),
                    _ => String::new(),
                })
                .unwrap_or_default()
        })
        .collect()
}

fn insert_rows(
    conn: &Connection,
    table_name: &str,
    spec: &crate::pack::tables::TableSpec,
    rows: &[std::collections::BTreeMap<String, CellValue>],
) -> Result<(), PackError> {
    let col_names: Vec<&str> = spec.columns.iter().map(|c| c.name).collect();
    let placeholders: Vec<&str> = spec.columns.iter().map(|_| "?").collect();
    let insert_sql = format!(
        "INSERT INTO {} ({}) VALUES ({})",
        table_name,
        col_names.join(","),
        placeholders.join(",")
    );

    let mut sorted_rows: Vec<&std::collections::BTreeMap<String, CellValue>> =
        rows.iter().collect();
    if !spec.primary_key.is_empty() {
        sorted_rows.sort_by_cached_key(|r| sort_key(r, spec.primary_key));
    }

    let mut stmt = conn.prepare(&insert_sql).map_err(|e| {
        PackError::table_invalid(format!("prepare insert for {table_name}: {e}"))
            .with_file(table_name)
    })?;

    for row in sorted_rows {
        let mut values: Vec<SqlVal> = Vec::with_capacity(spec.columns.len());
        for col in spec.columns.iter() {
            let v = row.get(col.name).ok_or_else(|| {
                PackError::table_invalid(format!("missing column {:?} in row", col.name))
                    .with_file(table_name)
                    .with_key(col.name)
            })?;
            values.push(cell_to_sql(v, col)?);
        }
        stmt.execute(rusqlite::params_from_iter(values.iter()))
            .map_err(|e| {
                PackError::table_invalid(format!("integrity violation in {table_name}: {e}"))
                    .with_file(table_name)
            })?;
    }
    Ok(())
}

fn insert_metadata(
    conn: &Connection,
    m: &ManifestFields,
    content_hash: &str,
    engine_version: &str,
) -> Result<(), PackError> {
    let synthetic_str = if m.synthetic { "1" } else { "0" };
    let built_by = format!("{} {}", BUILT_BY_PREFIX, engine_version);
    let schema_version_str = m.schema_version.to_string();
    let rows: [(&str, &str); 8] = [
        ("name", &m.name),
        ("version", &m.version),
        ("schema_version", &schema_version_str),
        ("engine_min", &m.engine_min),
        ("dictionary_min", &m.dictionary_min),
        ("synthetic", synthetic_str),
        ("content_hash", content_hash),
        ("built_by", &built_by),
    ];
    let mut stmt = conn
        .prepare("INSERT INTO metadata (key,value) VALUES (?,?)")
        .map_err(|e| PackError::pack_invalid(format!("prepare metadata insert: {e}")))?;
    for (k, v) in rows.iter() {
        stmt.execute(rusqlite::params![*k, *v])
            .map_err(|e| PackError::pack_invalid(format!("metadata insert: {e}")))?;
    }
    Ok(())
}

// ---- Parse all tables ----

pub fn parse_all_tables(
    files: &HashMap<String, Vec<u8>>,
) -> Result<std::collections::BTreeMap<String, Table>, PackError> {
    let mut tables: std::collections::BTreeMap<String, Table> = std::collections::BTreeMap::new();
    for name in ["taxa", "names", "hazards", "datasets", "sources"].iter() {
        let spec = table_spec(name)
            .ok_or_else(|| PackError::pack_invalid(format!("unknown table spec {name:?}")))?;
        let filename = spec
            .filename
            .ok_or_else(|| PackError::pack_invalid(format!("table {name:?} has no filename")))?;
        let data = files.get(filename).ok_or_else(|| {
            PackError::pack_invalid(format!("missing required file {filename:?}"))
                .with_file(filename)
        })?;
        tables.insert(name.to_string(), read_table(spec, data, filename)?);
    }
    let mut fact_keys: Vec<&String> = files
        .keys()
        .filter(|k| k.starts_with("facts/") && k.ends_with(".csv"))
        .collect();
    fact_keys.sort();
    let facts_spec =
        table_spec("facts").ok_or_else(|| PackError::pack_invalid("facts table spec missing"))?;
    for key in fact_keys {
        let data = files.get(key).ok_or_else(|| {
            PackError::pack_invalid(format!("missing facts file {key:?}")).with_file(key)
        })?;
        tables.insert(key.clone(), read_table(facts_spec, data, key)?);
    }
    Ok(tables)
}

// ---- Vacuum to temp file ----

fn vacuum_into_temp(conn: &Connection) -> Result<Vec<u8>, PackError> {
    let dir = std::env::temp_dir();
    let nanos = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.as_nanos())
        .unwrap_or(0);
    let path = dir.join(format!(
        "agri_build_{}_{}.sqlite",
        std::process::id(),
        nanos
    ));
    let safe = path.to_string_lossy().replace('\'', "''");
    let sql = format!("VACUUM INTO '{safe}'");
    conn.execute(&sql, [])
        .map_err(|e| PackError::pack_invalid(format!("VACUUM INTO failed: {e}")))?;
    let bytes = std::fs::read(&path)
        .map_err(|e| PackError::pack_invalid(format!("read temp sqlite: {e}")))?;
    let _ = std::fs::remove_file(&path);
    Ok(bytes)
}

// ---- Main build entry ----

/// Build SQLite bytes from a source pack.
///
/// Mirrors Python `_build_sqlite_and_hash` for the SQLite bytes step.
/// Returns the serialized SQLite file. `content_hash` is verified against
/// the source manifest (if present) but is NOT returned (caller re-derives
/// it, or uses `hash_pack_files` directly).
pub fn build_sqlite_bytes(
    files: &HashMap<String, Vec<u8>>,
    engine_version: &str,
) -> Result<Vec<u8>, PackError> {
    let pack_toml_bytes = files.get("pack.toml").ok_or_else(|| {
        PackError::pack_invalid("pack.toml missing from files mapping").with_file("pack.toml")
    })?;
    let manifest = parse_manifest_fields(pack_toml_bytes)?;

    if manifest.artifact_sha256.is_some()
        || manifest.sqlite_schema_version.is_some()
        || manifest.built_by.is_some()
    {
        return Err(PackError::pack_invalid(
            "cannot build from a manifest that already declares build fields \
             (artifact_sha256 / sqlite_schema_version / built_by)",
        )
        .with_file("pack.toml"));
    }

    let hash_alg = manifest.hash_alg.as_deref().unwrap_or("pre-rfc8785");
    let content_hash = hash_pack_files(files, hash_alg).map_err(PackError::pack_invalid)?;
    if let Some(ref expected) = manifest.content_hash {
        if expected != &content_hash {
            return Err(PackError::hash_mismatch(format!(
                "content_hash mismatch: manifest={expected} computed={content_hash}. \
                 Run `agri-core pack lock` first."
            ))
            .with_file("pack.toml"));
        }
    }

    if let Some(adv) = files.get("advisories.csv") {
        if !adv.iter().all(|b| b.is_ascii_whitespace()) {
            return Err(PackError::feature_unsupported(
                "advisories.csv has non-whitespace content; unsupported until \
                 advisory loading ships (ADR-004 §G3)",
            )
            .with_file("advisories.csv"));
        }
    }

    if (rusqlite::version_number() as i32) < MIN_SQLITE_VERSION_NUMBER {
        return Err(PackError::pack_invalid(format!(
            "sqlite {} < required 3.27.0 (VACUUM INTO)",
            rusqlite::version()
        )));
    }

    let tables = parse_all_tables(files)?;

    let conn = Connection::open_in_memory()
        .map_err(|e| PackError::pack_invalid(format!("open in-memory sqlite: {e}")))?;
    conn.execute("PRAGMA page_size = 4096", [])
        .map_err(|e| PackError::pack_invalid(format!("PRAGMA page_size: {e}")))?;
    conn.execute(&format!("PRAGMA application_id = {}", APPLICATION_ID), [])
        .map_err(|e| PackError::pack_invalid(format!("PRAGMA application_id: {e}")))?;
    conn.execute(
        &format!("PRAGMA user_version = {}", SQLITE_SCHEMA_VERSION),
        [],
    )
    .map_err(|e| PackError::pack_invalid(format!("PRAGMA user_version: {e}")))?;
    conn.execute_batch(_TABLE_DDL)
        .map_err(|e| PackError::pack_invalid(format!("DDL: {e}")))?;

    for name in TABLE_INSERT_ORDER.iter() {
        let spec = table_spec(name).ok_or_else(|| {
            PackError::pack_invalid(format!("unknown table spec {name:?} (internal)"))
        })?;
        let table = tables.get(*name).ok_or_else(|| {
            PackError::pack_invalid(format!("table {name:?} missing after parse"))
        })?;
        insert_rows(&conn, name, spec, &table.rows)?;
    }
    let facts_spec = table_spec("facts")
        .ok_or_else(|| PackError::pack_invalid("facts table spec missing (internal)"))?;
    for (key, table) in tables.iter() {
        if !key.starts_with("facts/") {
            continue;
        }
        insert_rows(&conn, "facts", facts_spec, &table.rows)?;
    }

    insert_metadata(&conn, &manifest, &content_hash, engine_version)?;

    for stmt in _INDEX_DDL.iter() {
        conn.execute(stmt, [])
            .map_err(|e| PackError::pack_invalid(format!("index DDL: {e}")))?;
    }

    let bytes = vacuum_into_temp(&conn)?;
    Ok(bytes)
}

// ---- Tests ----

#[cfg(test)]
#[allow(
    clippy::unwrap_used,
    clippy::expect_used,
    clippy::panic,
    clippy::indexing_slicing
)]
mod tests {
    use super::*;

    const SAMPLE_PACK_TOML: &[u8] = b"name = \"sample\"\n\
version = \"0.1.0\"\n\
schema_version = 1\n\
engine_min = \"0.0.0\"\n\
dictionary_min = \"1.2.0\"\n\
synthetic = true\n\
hash_alg = \"rfc8785\"\n\
content_hash = \"sha256:4ca67c008ae0abbc1218b16f570770bdc00069a686d5dee2c0154e03b08204f1\"\n";

    #[test]
    fn ddl_sha256_matches_python_kat() {
        assert_eq!(
            ddl_sha256(),
            "468260bdf1a7f0d1fbbb9e11b70f9453ee7fe8fe0dbe011bb5803d584fbc9b9d"
        );
    }

    #[test]
    fn parse_manifest_sample() {
        let m = parse_manifest_fields(SAMPLE_PACK_TOML).unwrap();
        assert_eq!(m.name, "sample");
        assert_eq!(m.version, "0.1.0");
        assert_eq!(m.schema_version, 1);
        assert_eq!(m.engine_min, "0.0.0");
        assert_eq!(m.dictionary_min, "1.2.0");
        assert!(m.synthetic);
        assert_eq!(m.hash_alg.as_deref(), Some("rfc8785"));
        assert_eq!(
            m.content_hash.as_deref(),
            Some("sha256:4ca67c008ae0abbc1218b16f570770bdc00069a686d5dee2c0154e03b08204f1")
        );
        assert!(m.artifact_sha256.is_none());
        assert!(m.sqlite_schema_version.is_none());
        assert!(m.built_by.is_none());
    }

    #[test]
    fn parse_manifest_missing_name_errors() {
        let e = parse_manifest_fields(b"version = \"0.1.0\"\n").unwrap_err();
        assert_eq!(e.code, "PACK_INVALID");
        assert!(e.message.contains("name"), "got: {}", e.message);
    }

    #[test]
    fn parse_manifest_not_utf8_errors() {
        let e = parse_manifest_fields(b"\xff\xfe").unwrap_err();
        assert_eq!(e.code, "PACK_INVALID");
        assert!(e.message.contains("UTF-8"), "got: {}", e.message);
    }

    fn minimal_files() -> HashMap<String, Vec<u8>> {
        let mut f: HashMap<String, Vec<u8>> = HashMap::new();
        f.insert("pack.toml".to_string(),
            b"name = \"t\"\nversion = \"0.0.0\"\nschema_version = 1\nengine_min = \"0.0.0\"\ndictionary_min = \"1.0.0\"\n".to_vec());
        f.insert("taxa.csv".to_string(),
            b"taxon_id,rank,scientific_name,accepted_name,organism_group,archetype,uses,traits,parent_id,external_ids,src,dataset_id\n\
T000000001,species,Test,,vascular_plant,annual,vegetable,,,,S001,\n".to_vec());
        f.insert(
            "names.csv".to_string(),
            b"taxon_id,name,language,script,kind,preferred,src,dataset_id\n".to_vec(),
        );
        f.insert(
            "hazards.csv".to_string(),
            b"taxon_id,hazard_code,severity,reason,as_of,authority,src,dataset_id\n".to_vec(),
        );
        f.insert(
            "datasets.csv".to_string(),
            b"dataset_id,name,version,license,checksum,url,locator,access_date\n".to_vec(),
        );
        f.insert("sources.csv".to_string(),
            b"id,url,license,commercial_use,access_date,citation\nS001,https://x,CC0-1.0,yes,2026-01-01,Test\n".to_vec());
        f
    }

    #[test]
    fn build_minimal_returns_sqlite_magic() {
        let files = minimal_files();
        let bytes = build_sqlite_bytes(&files, "0.1.6").unwrap();
        assert!(
            bytes.starts_with(b"SQLite format 3\x00"),
            "not a SQLite file"
        );
        assert!(bytes.len() > 4096);
    }

    #[test]
    fn build_missing_pack_toml_errors() {
        let mut files = minimal_files();
        files.remove("pack.toml");
        let e = build_sqlite_bytes(&files, "0.1.6").unwrap_err();
        assert_eq!(e.code, "PACK_INVALID");
        assert!(e.message.contains("pack.toml"));
    }

    #[test]
    fn build_rejects_manifest_with_artifact_sha256() {
        let mut files = minimal_files();
        files.insert("pack.toml".to_string(),
            b"name = \"t\"\nversion = \"0.0.0\"\nschema_version = 1\nengine_min = \"0.0.0\"\ndictionary_min = \"1.0.0\"\nartifact_sha256 = \"sha256:0000000000000000000000000000000000000000000000000000000000000000\"\nsqlite_schema_version = 1\nbuilt_by = \"agri-core 0.0.0\"\n".to_vec());
        let e = build_sqlite_bytes(&files, "0.1.6").unwrap_err();
        assert_eq!(e.code, "PACK_INVALID");
        assert!(e.message.contains("build fields"));
    }

    #[test]
    fn build_rejects_hash_mismatch() {
        let mut files = minimal_files();
        files.insert("pack.toml".to_string(),
            b"name = \"t\"\nversion = \"0.0.0\"\nschema_version = 1\nengine_min = \"0.0.0\"\ndictionary_min = \"1.0.0\"\ncontent_hash = \"sha256:0000000000000000000000000000000000000000000000000000000000000000\"\n".to_vec());
        let e = build_sqlite_bytes(&files, "0.1.6").unwrap_err();
        assert_eq!(e.code, "PACK_HASH_MISMATCH");
    }

    #[test]
    fn build_rejects_advisories_with_data() {
        let mut files = minimal_files();
        files.insert("advisories.csv".to_string(), b"fact_id,x\nF1,x\n".to_vec());
        let e = build_sqlite_bytes(&files, "0.1.6").unwrap_err();
        assert_eq!(e.code, "PACK_FEATURE_UNSUPPORTED");
    }

    #[test]
    fn build_allows_advisories_whitespace() {
        let mut files = minimal_files();
        files.insert("advisories.csv".to_string(), b"\n\n".to_vec());
        let _bytes = build_sqlite_bytes(&files, "0.1.6").unwrap();
    }
}
