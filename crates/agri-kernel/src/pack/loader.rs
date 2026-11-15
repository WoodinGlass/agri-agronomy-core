//! Load a built pack (pack.sqlite + pack.toml) into a RustKnowledgeSet.
//!
//! Mirrors `_load_built_pack` from `pack/loader.py` for the built-pack path.
//!
//! Security: hash-while-read. Bytes hashed == bytes deserialized. No TOCTOU
//! window between hash verification and query. See ADR-019 §11.8.

use std::collections::{BTreeMap, BTreeSet};
use std::io::Read;
use std::path::Path;

use rusqlite::types::Value as SqlVal;
use rusqlite::Connection;
use sha2::{Digest, Sha256};

use crate::pack::build::ManifestFields;
use crate::pack::errors::PackError;
use crate::pack::knowledge_set::{KnowledgeSetError, RustKnowledgeSet};
use crate::pack::row_types::{
    dataset_from_json, fact_from_json, hazard_from_json, name_from_json, source_from_json,
    taxon_from_json, DatasetRow, FactRow, HazardRow, NameRow, SourceRow, TaxonRow,
};
use crate::pack::validate::SQLITE_SCHEMA_VERSION;

// ---- Hashing reader ----

/// `Read` adapter that updates a SHA-256 as bytes flow through.
///
/// Bytes the caller consumes are exactly the bytes hashed. Used with
/// `Connection::deserialize_read_exact` so the hash we verify is over
/// the byte stream that was opened. See ADR-019 §11.8.
struct HashingRead<R: Read> {
    inner: R,
    hasher: Sha256,
}

impl<R: Read> HashingRead<R> {
    fn new(inner: R) -> Self {
        Self {
            inner,
            hasher: Sha256::new(),
        }
    }

    fn finalize_hex(self) -> String {
        let digest = self.hasher.finalize();
        let mut out = String::with_capacity(64);
        for b in digest.iter() {
            use std::fmt::Write as _;
            let _ = write!(out, "{b:02x}");
        }
        out
    }
}

impl<R: Read> Read for HashingRead<R> {
    fn read(&mut self, buf: &mut [u8]) -> std::io::Result<usize> {
        let n = self.inner.read(buf)?;
        if let Some(slice) = buf.get(..n) {
            self.hasher.update(slice);
        }
        Ok(n)
    }
}

// ---- Loader ----

/// Load a built pack from disk into a `RustKnowledgeSet`.
///
/// Caller (PyO3 wrapper) parses `pack.toml` first and passes
/// `manifest` + `expected_content_hash` (caller pin, if any). This
/// function reads the SQLite file, hashes while reading, deserializes,
/// verifies metadata, extracts all rows, and returns the eager set.
pub fn load_built_pack(
    path: &Path,
    manifest: ManifestFields,
    expected_content_hash: Option<&str>,
    dictionary_version: String,
    max_bytes: u64,
) -> Result<RustKnowledgeSet, PackError> {
    // 1. Size check.
    let meta = std::fs::metadata(path).map_err(|e| {
        PackError::pack_invalid(format!("stat pack.sqlite: {e}")).with_file("pack.sqlite")
    })?;
    let total_size = meta.len();
    if total_size > max_bytes {
        return Err(PackError::too_large(format!(
            "built pack size {total_size} > max_bytes {max_bytes}"
        ))
        .with_file("pack.sqlite"));
    }

    // 2. Validate manifest has build fields.
    let artifact_sha256 = manifest.artifact_sha256.clone().ok_or_else(|| {
        PackError::pack_invalid("built pack.toml missing artifact_sha256").with_file("pack.toml")
    })?;
    let content_hash = manifest.content_hash.clone().ok_or_else(|| {
        PackError::pack_invalid("built pack.toml missing content_hash").with_file("pack.toml")
    })?;
    let sqlite_schema_version = manifest.sqlite_schema_version.ok_or_else(|| {
        PackError::pack_invalid("built pack.toml missing sqlite_schema_version")
            .with_file("pack.toml")
    })?;
    let built_by = manifest.built_by.clone().ok_or_else(|| {
        PackError::pack_invalid("built pack.toml missing built_by").with_file("pack.toml")
    })?;

    // 3. Check schema version.
    if sqlite_schema_version != SQLITE_SCHEMA_VERSION {
        return Err(PackError::schema_unsupported(format!(
            "built pack sqlite_schema_version {sqlite_schema_version} != engine SQLITE_SCHEMA_VERSION {SQLITE_SCHEMA_VERSION}"
        )));
    }

    // 4. Open file, wrap in HashingRead, deserialize.
    let file = std::fs::File::open(path).map_err(|e| {
        PackError::pack_invalid(format!("open pack.sqlite: {e}")).with_file("pack.sqlite")
    })?;
    let mut reader = HashingRead::new(file);
    let mut conn = Connection::open_in_memory()
        .map_err(|e| PackError::pack_invalid(format!("open in-memory sqlite: {e}")))?;
    let total_size_usize = usize::try_from(total_size).map_err(|_| {
        PackError::too_large(format!("pack.sqlite size {total_size} exceeds usize::MAX"))
            .with_file("pack.sqlite")
    })?;
    conn.deserialize_read_exact("main", &mut reader, total_size_usize, false)
        .map_err(|e| {
            PackError::pack_invalid(format!("deserialize pack.sqlite: {e}"))
                .with_file("pack.sqlite")
        })?;
    let actual_artifact = format!("sha256:{}", reader.finalize_hex());

    // 5. Compare artifact hash.
    if artifact_sha256 != actual_artifact {
        return Err(PackError::hash_mismatch(format!(
            "artifact_sha256 mismatch: manifest={artifact_sha256} computed={actual_artifact}"
        ))
        .with_file("pack.sqlite"));
    }
    if let Some(expected) = expected_content_hash {
        if expected != actual_artifact {
            return Err(PackError::hash_mismatch(format!(
                "expected_hash mismatch: caller={expected} computed={actual_artifact}"
            ))
            .with_file("pack.sqlite"));
        }
    }

    // 6. Configure connection: read-only, no schema trust.
    conn.execute_batch("PRAGMA query_only = ON; PRAGMA trusted_schema = OFF;")
        .map_err(|e| PackError::pack_invalid(format!("configure connection: {e}")))?;

    // 7. Check user_version.
    let uv: i64 = conn
        .query_row("PRAGMA user_version", [], |r| r.get(0))
        .map_err(|e| PackError::pack_invalid(format!("read user_version: {e}")))?;
    if uv != sqlite_schema_version {
        return Err(PackError::pack_invalid(format!(
            "sqlite user_version {uv} != manifest sqlite_schema_version {sqlite_schema_version}"
        ))
        .with_file("pack.sqlite"));
    }

    // 8. Read metadata table + compare with manifest fields.
    let metadata = read_metadata(&conn)?;
    check_metadata(&metadata, &manifest, &content_hash, &built_by)?;

    // 9. Read all tables.
    let taxa = read_table_as::<TaxonRow, _>(&conn, "taxa", taxon_from_json)?;
    let names = read_table_as::<NameRow, _>(&conn, "names", name_from_json)?;
    let facts = read_table_as::<FactRow, _>(&conn, "facts", fact_from_json)?;
    let hazards = read_table_as::<HazardRow, _>(&conn, "hazards", hazard_from_json)?;
    let sources = read_table_as::<SourceRow, _>(&conn, "sources", source_from_json)?;
    let datasets = read_table_as::<DatasetRow, _>(&conn, "datasets", dataset_from_json)?;

    // Built packs do not preserve ids.lock; content_hash covers the source.
    let ids_lock: Option<BTreeSet<String>> = None;

    drop(conn);

    // 10. Construct eager set.
    RustKnowledgeSet::from_rows(
        manifest,
        content_hash,
        artifact_sha256,
        dictionary_version,
        true,
        ids_lock,
        taxa,
        names,
        facts,
        hazards,
        sources,
        datasets,
    )
    .map_err(|e: KnowledgeSetError| PackError::pack_invalid(format!("{e}")))
}

// ---- Helpers ----

fn read_metadata(conn: &Connection) -> Result<BTreeMap<String, String>, PackError> {
    let mut stmt = conn
        .prepare("SELECT key, value FROM metadata")
        .map_err(|e| PackError::pack_invalid(format!("prepare metadata: {e}")))?;
    let rows = stmt
        .query_map([], |r| {
            let k: String = r.get(0)?;
            let v: String = r.get(1)?;
            Ok((k, v))
        })
        .map_err(|e| PackError::pack_invalid(format!("query metadata: {e}")))?;
    let mut out = BTreeMap::new();
    for r in rows {
        let (k, v) = r.map_err(|e| PackError::pack_invalid(format!("metadata row: {e}")))?;
        out.insert(k, v);
    }
    Ok(out)
}

fn check_metadata(
    actual: &BTreeMap<String, String>,
    manifest: &ManifestFields,
    content_hash: &str,
    built_by: &str,
) -> Result<(), PackError> {
    let expected: [(&str, String); 8] = [
        ("name", manifest.name.clone()),
        ("version", manifest.version.clone()),
        ("schema_version", manifest.schema_version.to_string()),
        ("engine_min", manifest.engine_min.clone()),
        ("dictionary_min", manifest.dictionary_min.clone()),
        (
            "synthetic",
            if manifest.synthetic {
                "1".to_string()
            } else {
                "0".to_string()
            },
        ),
        ("content_hash", content_hash.to_string()),
        ("built_by", built_by.to_string()),
    ];
    for (key, expected_val) in expected.iter() {
        match actual.get(*key) {
            None => {
                return Err(
                    PackError::pack_invalid(format!("metadata missing key {key:?}"))
                        .with_file("pack.sqlite"),
                )
            }
            Some(got) if got != expected_val => {
                return Err(PackError::pack_invalid(format!(
                    "metadata mismatch for {key:?}: sqlite={got:?} manifest={expected_val:?}"
                ))
                .with_file("pack.sqlite"))
            }
            Some(_) => {}
        }
    }
    Ok(())
}

fn read_table_as<T, F>(conn: &Connection, table: &str, convert: F) -> Result<Vec<T>, PackError>
where
    F: Fn(&serde_json::Value) -> Result<T, crate::pack::row_types::ConvertError>,
{
    let spec = crate::pack::tables::table_spec(table)
        .ok_or_else(|| PackError::pack_invalid(format!("unknown table {table:?}")))?;

    // Build ordered list of column names from spec.
    let col_names: Vec<&'static str> = spec.columns.iter().map(|c| c.name).collect();

    let sql = format!("SELECT {} FROM {}", col_names.join(", "), table);
    let mut stmt = conn
        .prepare(&sql)
        .map_err(|e| PackError::pack_invalid(format!("prepare {table}: {e}")))?;

    let col_count = col_names.len();
    let mut rows = stmt
        .query([])
        .map_err(|e| PackError::pack_invalid(format!("query {table}: {e}")))?;

    let mut out = Vec::new();
    while let Some(sql_row) = rows
        .next()
        .map_err(|e| PackError::pack_invalid(format!("row {table}: {e}")))?
    {
        // Build a BTreeMap<String, CellValue>-equivalent json object.
        let mut obj: serde_json::Map<String, serde_json::Value> =
            serde_json::Map::with_capacity(col_count);
        for (i, name) in col_names.iter().enumerate() {
            let v: SqlVal = sql_row
                .get(i)
                .map_err(|e| PackError::pack_invalid(format!("get col {name} in {table}: {e}")))?;
            let jv = sql_to_json(&v, name, spec);
            obj.insert((*name).to_string(), jv);
        }
        let j = serde_json::Value::Object(obj);
        let converted =
            convert(&j).map_err(|e| PackError::pack_invalid(format!("convert {table}: {e}")))?;
        out.push(converted);
    }
    Ok(out)
}

/// Convert a SQLite value to JSON using the column type from spec to
/// pick the right shape (list_str -> array, json/dict_str_str -> object).
fn sql_to_json(
    v: &SqlVal,
    col_name: &str,
    spec: &crate::pack::tables::TableSpec,
) -> serde_json::Value {
    use crate::pack::tables::ColumnType;
    use serde_json::Value;
    let col = spec.columns.iter().find(|c| c.name == col_name);
    match v {
        SqlVal::Null => Value::Null,
        SqlVal::Integer(i) => Value::Number((*i).into()),
        SqlVal::Real(f) => serde_json::Number::from_f64(*f)
            .map(Value::Number)
            .unwrap_or(Value::Null),
        SqlVal::Text(s) => {
            let col_type = col.map(|c| c.ty);
            match col_type {
                Some(ColumnType::ListStr) => {
                    // Pipe-encoded; split.
                    if s.is_empty() {
                        Value::Array(vec![])
                    } else {
                        Value::Array(s.split('|').map(|x| Value::String(x.to_string())).collect())
                    }
                }
                Some(ColumnType::DictStrStr) | Some(ColumnType::Json) => {
                    // Canonical JSON in the column; parse to structured value.
                    serde_json::from_str(s).unwrap_or(Value::String(s.clone()))
                }
                _ => Value::String(s.clone()),
            }
        }
        SqlVal::Blob(_) => Value::Null, // unexpected in pack format
    }
}

#[cfg(test)]
#[allow(
    clippy::unwrap_used,
    clippy::expect_used,
    clippy::panic,
    clippy::indexing_slicing
)]
mod tests {
    use super::*;

    #[test]
    fn hashing_read_passes_bytes() {
        let data = b"hello world";
        let mut reader = HashingRead::new(std::io::Cursor::new(data));
        let mut buf = Vec::new();
        std::io::Read::read_to_end(&mut reader, &mut buf).unwrap();
        assert_eq!(buf, data);
        let hex = reader.finalize_hex();
        // SHA-256("hello world") = b94d27b9934d3e08a52e52d7da7dabfa... (verify prefix)
        assert!(hex.starts_with("b94d27b9934d3e08a52e52d7da7dabfa"));
    }

    #[test]
    fn hashing_read_empty() {
        let data: &[u8] = b"";
        let mut reader = HashingRead::new(std::io::Cursor::new(data));
        let mut buf = Vec::new();
        std::io::Read::read_to_end(&mut reader, &mut buf).unwrap();
        assert!(buf.is_empty());
        // SHA-256("") = e3b0c44298fc1c149afbf4c8996fb924
        let hex = reader.finalize_hex();
        assert_eq!(
            hex,
            "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
        );
    }
}
