//! Path-based pack reader (Phase E, feature `exp-diff`).
//!
//! Opens a built pack via `deserialize_read_exact`, verifies
//! `artifact_sha256` hash-while-read (no TOCTOU window per ADR-019 §11.8),
//! and materializes row structs for `diff_rows` consumption.
//!
//! Row materialization is O(n_rows) in memory (~190 MB for 320k facts).
//! Streaming merge-join for O(1) memory is deferred to M22/M23.

use std::io::{Cursor, Read};
use std::path::Path;
use std::sync::mpsc::{sync_channel, Receiver, SyncSender};
use std::sync::Arc;
use std::thread::{self, JoinHandle};

use rusqlite::Connection;
use sha2::{Digest, Sha256};

use crate::pack::build::ManifestFields;
use crate::pack::errors::PackError;
use crate::pack::row_types::{fact_from_json, taxon_from_json, FactRow, TaxonRow};

pub const MAX_PACK_BYTES: u64 = 100 * 1024 * 1024;
pub const MAX_DIFF_ROWS: usize = 10_000_000;
pub const MAX_FIELD_BYTES: usize = 16 * 1024;

#[derive(Debug)]
pub struct PackStream {
    bytes: Arc<Vec<u8>>,
    pub pack_hash: String,
    pub row_count: usize,
}

impl PackStream {
    pub fn open(path: &Path, manifest: &ManifestFields) -> Result<Self, PackError> {
        let declared = match manifest.artifact_sha256.as_deref() {
            Some(s) => s,
            None => {
                return Err(PackError::pack_invalid(
                    "manifest missing artifact_sha256; not a built pack",
                )
                .with_file("pack.toml"));
            }
        };
        let expected_hex = declared.strip_prefix("sha256:").unwrap_or(declared);

        let meta = std::fs::metadata(path).map_err(|e| {
            PackError::pack_invalid(format!("metadata {}: {e}", path.display()))
                .with_file("pack.sqlite")
        })?;
        if meta.len() > MAX_PACK_BYTES {
            return Err(PackError::too_large(format!(
                "pack.sqlite is {} bytes, exceeds MAX_PACK_BYTES {}",
                meta.len(),
                MAX_PACK_BYTES
            ))
            .with_file("pack.sqlite"));
        }

        let mut f = std::fs::File::open(path).map_err(|e| {
            PackError::pack_invalid(format!("open {}: {e}", path.display()))
                .with_file("pack.sqlite")
        })?;
        let mut buf: Vec<u8> = Vec::with_capacity(meta.len() as usize);
        let mut hasher = Sha256::new();
        let mut chunk = [0u8; 8192];
        loop {
            let n = f.read(&mut chunk).map_err(|e| {
                PackError::pack_invalid(format!("read {}: {e}", path.display()))
                    .with_file("pack.sqlite")
            })?;
            if n == 0 {
                break;
            }
            let slice = chunk.get(..n).ok_or_else(|| {
                PackError::pack_invalid(format!(
                    "read {}: byte count {} > chunk len {}",
                    path.display(),
                    n,
                    chunk.len()
                ))
            })?;
            hasher.update(slice);
            buf.extend_from_slice(slice);
        }
        let digest = hasher.finalize();
        let mut actual_hex = String::with_capacity(64);
        for b in digest.iter() {
            let part = format!("{:02x}", b);
            actual_hex.push_str(&part);
        }
        if actual_hex != expected_hex {
            return Err(PackError::hash_mismatch(format!(
                "artifact_sha256 mismatch: manifest={} actual={}",
                expected_hex, actual_hex
            ))
            .with_file("pack.sqlite"));
        }

        let conn = open_conn_from_bytes(&buf)?;
        let taxa_count: i64 = conn
            .query_row("SELECT count(*) FROM taxa", [], |r| r.get(0))
            .map_err(|e| PackError::pack_invalid(format!("count taxa: {e}")))?;
        let facts_count: i64 = conn
            .query_row("SELECT count(*) FROM facts", [], |r| r.get(0))
            .map_err(|e| PackError::pack_invalid(format!("count facts: {e}")))?;
        drop(conn);
        let row_count = (taxa_count as usize) + (facts_count as usize);
        if row_count > MAX_DIFF_ROWS {
            return Err(PackError::too_large(format!(
                "pack has {} rows, exceeds MAX_DIFF_ROWS {}",
                row_count, MAX_DIFF_ROWS
            ))
            .with_file("pack.sqlite"));
        }

        let pack_hash = manifest.content_hash.clone().unwrap_or_default();
        Ok(PackStream {
            bytes: Arc::new(buf),
            pack_hash,
            row_count,
        })
    }

    pub fn open_taxa_producer(&self) -> Result<ProducerIter<TaxonRow>, PackError> {
        let bytes = Arc::clone(&self.bytes);
        let (tx, rx) = sync_channel(PRODUCER_BUFFER);
        let handle = thread::spawn(move || {
            if let Err(e) = produce_taxa(&bytes, &tx) {
                let _ = tx.send(Err(e));
            }
        });
        Ok(ProducerIter {
            rx,
            handle: Some(handle),
        })
    }

    pub fn open_facts_producer(&self) -> Result<ProducerIter<FactRow>, PackError> {
        let bytes = Arc::clone(&self.bytes);
        let (tx, rx) = sync_channel(PRODUCER_BUFFER);
        let handle = thread::spawn(move || {
            if let Err(e) = produce_facts(&bytes, &tx) {
                let _ = tx.send(Err(e));
            }
        });
        Ok(ProducerIter {
            rx,
            handle: Some(handle),
        })
    }
}

fn fact_row_from_sql(row: &rusqlite::Row<'_>) -> Result<FactRow, PackError> {
    let fact_id: String = row.get(0).map_err(sql_col("fact_id"))?;
    let taxon_id: String = row.get(1).map_err(sql_col("taxon_id"))?;
    let parameter: String = row.get(2).map_err(sql_col("parameter"))?;
    let phase: Option<String> = row.get(3).map_err(sql_col("phase"))?;
    let value_str: String = row.get(4).map_err(sql_col("value"))?;
    let scope_str: String = row.get(5).map_err(sql_col("scope"))?;
    let provenance_kind: String = row.get(6).map_err(sql_col("provenance_kind"))?;
    let src_str: Option<String> = row.get(7).map_err(sql_col("src"))?;
    let dataset_id: Option<String> = row.get(8).map_err(sql_col("dataset_id"))?;
    let locator: Option<String> = row.get(9).map_err(sql_col("locator"))?;
    let evidence: String = row.get(10).map_err(sql_col("evidence"))?;
    let status: String = row.get(11).map_err(sql_col("status"))?;
    let reviewed_by_str: Option<String> = row.get(12).map_err(sql_col("reviewed_by"))?;
    let reviewed_at: Option<String> = row.get(13).map_err(sql_col("reviewed_at"))?;
    let superseded_by: Option<String> = row.get(14).map_err(sql_col("superseded_by"))?;

    check_field_len("fact_id", &fact_id)?;
    check_field_len("taxon_id", &taxon_id)?;
    check_field_len("parameter", &parameter)?;
    if let Some(ref v) = phase {
        check_field_len("phase", v)?;
    }
    check_field_len("value", &value_str)?;
    check_field_len("scope", &scope_str)?;
    check_field_len("provenance_kind", &provenance_kind)?;
    if let Some(ref v) = src_str {
        check_field_len("src", v)?;
    }
    if let Some(ref v) = dataset_id {
        check_field_len("dataset_id", v)?;
    }
    if let Some(ref v) = locator {
        check_field_len("locator", v)?;
    }
    check_field_len("evidence", &evidence)?;
    check_field_len("status", &status)?;
    if let Some(ref v) = reviewed_by_str {
        check_field_len("reviewed_by", v)?;
    }
    if let Some(ref v) = reviewed_at {
        check_field_len("reviewed_at", v)?;
    }
    if let Some(ref v) = superseded_by {
        check_field_len("superseded_by", v)?;
    }

    let value_json: serde_json::Value = serde_json::from_str(&value_str)
        .map_err(|e| PackError::pack_invalid(format!("value JSON: {e}")))?;
    let scope_json: serde_json::Value = serde_json::from_str(&scope_str)
        .map_err(|e| PackError::pack_invalid(format!("scope JSON: {e}")))?;
    let reviewed_by: Option<Vec<String>> = match reviewed_by_str {
        Some(s) if !s.is_empty() => Some(split_pipe(&s)),
        _ => None,
    };
    let src: Option<Vec<String>> = match src_str {
        Some(s) if !s.is_empty() => Some(split_pipe(&s)),
        _ => None,
    };

    let json_val = serde_json::json!({
        "fact_id": fact_id,
        "taxon_id": taxon_id,
        "parameter": parameter,
        "phase": phase,
        "value": value_json,
        "scope": scope_json,
        "provenance_kind": provenance_kind,
        "src": src,
        "dataset_id": dataset_id,
        "locator": locator,
        "evidence": evidence,
        "status": status,
        "reviewed_by": reviewed_by,
        "reviewed_at": reviewed_at,
        "superseded_by": superseded_by,
    });

    fact_from_json(&json_val).map_err(|e| PackError::pack_invalid(format!("fact parse: {e}")))
}

fn taxon_row_from_sql(row: &rusqlite::Row<'_>) -> Result<TaxonRow, PackError> {
    let uses_str: String = row.get(6).map_err(sql_col("uses"))?;
    let traits_str: String = row.get(7).map_err(sql_col("traits"))?;
    let external_ids_str: Option<String> = row.get(9).map_err(sql_col("external_ids"))?;
    let src_str: Option<String> = row.get(10).map_err(sql_col("src"))?;

    let uses: Vec<String> = split_pipe(&uses_str);
    let traits: Vec<String> = split_pipe(&traits_str);
    let external_ids: Option<serde_json::Value> = match &external_ids_str {
        Some(s) if !s.is_empty() => Some(
            serde_json::from_str(s)
                .map_err(|e| PackError::pack_invalid(format!("external_ids JSON: {e}")))?,
        ),
        _ => None,
    };
    let src: Option<Vec<String>> = match &src_str {
        Some(s) if !s.is_empty() => Some(split_pipe(s)),
        _ => None,
    };

    let tid: String = row.get(0).map_err(sql_col("taxon_id"))?;
    let rank: String = row.get(1).map_err(sql_col("rank"))?;
    let sci: String = row.get(2).map_err(sql_col("scientific_name"))?;
    let accepted: Option<String> = row.get(3).map_err(sql_col("accepted_name"))?;
    let og: String = row.get(4).map_err(sql_col("organism_group"))?;
    let arch: String = row.get(5).map_err(sql_col("archetype"))?;
    let parent: Option<String> = row.get(8).map_err(sql_col("parent_id"))?;
    let ds: Option<String> = row.get(11).map_err(sql_col("dataset_id"))?;

    check_field_len("taxon_id", &tid)?;
    check_field_len("rank", &rank)?;
    check_field_len("scientific_name", &sci)?;
    if let Some(ref v) = accepted {
        check_field_len("accepted_name", v)?;
    }
    check_field_len("organism_group", &og)?;
    check_field_len("archetype", &arch)?;
    if let Some(ref v) = parent {
        check_field_len("parent_id", v)?;
    }
    if let Some(ref v) = ds {
        check_field_len("dataset_id", v)?;
    }
    check_field_len("uses", &uses_str)?;
    check_field_len("traits", &traits_str)?;
    if let Some(ref v) = external_ids_str {
        check_field_len("external_ids", v)?;
    }
    if let Some(ref v) = src_str {
        check_field_len("src", v)?;
    }

    let json_val = serde_json::json!({
        "taxon_id": tid,
        "rank": rank,
        "scientific_name": sci,
        "accepted_name": accepted,
        "organism_group": og,
        "archetype": arch,
        "uses": uses,
        "traits": traits,
        "parent_id": parent,
        "external_ids": external_ids,
        "src": src,
        "dataset_id": ds,
    });

    taxon_from_json(&json_val).map_err(|e| PackError::pack_invalid(format!("taxon parse: {e}")))
}

fn split_pipe(s: &str) -> Vec<String> {
    if s.is_empty() {
        Vec::new()
    } else {
        s.split('|').map(|p| p.to_string()).collect()
    }
}

pub const PRODUCER_BUFFER: usize = 1000;

pub struct ProducerIter<T> {
    rx: Receiver<Result<T, PackError>>,
    handle: Option<JoinHandle<()>>,
}

impl<T> Iterator for ProducerIter<T> {
    type Item = Result<T, PackError>;
    fn next(&mut self) -> Option<Self::Item> {
        match self.rx.recv() {
            Ok(item) => Some(item),
            Err(_) => {
                let mut panicked: Option<PackError> = None;
                if let Some(h) = self.handle.take() {
                    if h.join().is_err() {
                        panicked = Some(PackError::pack_invalid("producer thread panicked"));
                    }
                }
                panicked.map(Result::<T, PackError>::Err)
            }
        }
    }
}

impl<T> Drop for ProducerIter<T> {
    fn drop(&mut self) {
        if let Some(h) = self.handle.take() {
            let _ = h.join();
        }
    }
}

fn open_conn_from_bytes(bytes: &[u8]) -> Result<Connection, PackError> {
    let mut conn = Connection::open_in_memory()
        .map_err(|e| PackError::pack_invalid(format!("open in-memory sqlite: {e}")))?;
    conn.deserialize_read_exact("main", &mut Cursor::new(bytes), bytes.len(), true)
        .map_err(|e| PackError::pack_invalid(format!("deserialize: {e}")))?;
    conn.pragma_update(None, "query_only", "ON")
        .map_err(|e| PackError::pack_invalid(format!("PRAGMA query_only: {e}")))?;
    conn.pragma_update(None, "trusted_schema", "OFF")
        .map_err(|e| PackError::pack_invalid(format!("PRAGMA trusted_schema: {e}")))?;
    Ok(conn)
}

fn produce_taxa(
    bytes: &Arc<Vec<u8>>,
    tx: &SyncSender<Result<TaxonRow, PackError>>,
) -> Result<(), PackError> {
    let conn = open_conn_from_bytes(bytes)?;
    let mut stmt = conn
        .prepare(
            "SELECT taxon_id, rank, scientific_name, accepted_name, organism_group, \
             archetype, uses, traits, parent_id, external_ids, src, dataset_id \
             FROM taxa ORDER BY taxon_id",
        )
        .map_err(|e| PackError::pack_invalid(format!("prepare taxa: {e}")))?;
    let mut rows = stmt
        .query([])
        .map_err(|e| PackError::pack_invalid(format!("query taxa: {e}")))?;
    while let Some(row) = rows
        .next()
        .map_err(|e| PackError::pack_invalid(format!("iterate taxa: {e}")))?
    {
        let item = taxon_row_from_sql(row);
        if tx.send(item).is_err() {
            return Ok(());
        }
    }
    Ok(())
}

fn produce_facts(
    bytes: &Arc<Vec<u8>>,
    tx: &SyncSender<Result<FactRow, PackError>>,
) -> Result<(), PackError> {
    let conn = open_conn_from_bytes(bytes)?;
    let mut stmt = conn
        .prepare(
            "SELECT fact_id, taxon_id, parameter, phase, value, scope, \
             provenance_kind, src, dataset_id, locator, evidence, status, \
             reviewed_by, reviewed_at, superseded_by \
             FROM facts ORDER BY fact_id",
        )
        .map_err(|e| PackError::pack_invalid(format!("prepare facts: {e}")))?;
    let mut rows = stmt
        .query([])
        .map_err(|e| PackError::pack_invalid(format!("query facts: {e}")))?;
    while let Some(row) = rows
        .next()
        .map_err(|e| PackError::pack_invalid(format!("iterate facts: {e}")))?
    {
        let item = fact_row_from_sql(row);
        if tx.send(item).is_err() {
            return Ok(());
        }
    }
    Ok(())
}

fn check_field_len(name: &'static str, value: &str) -> Result<(), PackError> {
    if value.len() > MAX_FIELD_BYTES {
        return Err(PackError::field_too_large(format!(
            "field {} is {} bytes, exceeds MAX_FIELD_BYTES {}",
            name,
            value.len(),
            MAX_FIELD_BYTES
        ))
        .with_key(name));
    }
    Ok(())
}

fn sql_col(name: &'static str) -> impl Fn(rusqlite::Error) -> PackError {
    move |e| PackError::pack_invalid(format!("column {name}: {e}"))
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
    use crate::pack::build::build_sqlite_bytes;
    use std::collections::HashMap;

    fn sample_files() -> HashMap<String, Vec<u8>> {
        let mut f: HashMap<String, Vec<u8>> = HashMap::new();
        f.insert(
            "pack.toml".to_string(),
            b"name = \"t\"\nversion = \"0.0.0\"\nschema_version = 1\n\
              engine_min = \"0.0.0\"\ndictionary_min = \"1.0.0\"\n"
                .to_vec(),
        );
        f.insert(
            "taxa.csv".to_string(),
            b"taxon_id,rank,scientific_name,accepted_name,organism_group,archetype,uses,traits,parent_id,external_ids,src,dataset_id\n\
T000000001,species,Test,,vascular_plant,annual,vegetable,,,,S001,\n"
                .to_vec(),
        );
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
        f.insert(
            "sources.csv".to_string(),
            b"id,url,license,commercial_use,access_date,citation\nS001,https://x,CC0-1.0,yes,2026-01-01,Test\n"
                .to_vec(),
        );
        f
    }

    fn write_temp(bytes: &[u8]) -> std::path::PathBuf {
        let nanos = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .map(|d| d.as_nanos())
            .unwrap_or(0);
        let pid = std::process::id();
        let dir = std::env::temp_dir().join(format!("agri_stream_{}_{}", pid, nanos));
        std::fs::create_dir_all(&dir).unwrap();
        let path = dir.join("pack.sqlite");
        std::fs::write(&path, bytes).unwrap();
        path
    }

    fn compute_sha(bytes: &[u8]) -> String {
        let mut h = Sha256::new();
        h.update(bytes);
        let d = h.finalize();
        let mut hex = String::new();
        for b in d.iter() {
            let part = format!("{:02x}", b);
            hex.push_str(&part);
        }
        hex
    }

    fn manifest_with_sha(sha: Option<String>) -> ManifestFields {
        ManifestFields {
            name: "t".to_string(),
            version: "0.0.0".to_string(),
            schema_version: 1,
            engine_min: "0.0.0".to_string(),
            dictionary_min: "1.0.0".to_string(),
            content_hash: None,
            synthetic: false,
            artifact_sha256: sha,
            sqlite_schema_version: Some(1),
            built_by: Some("agri-core 0.0.0".to_string()),
            hash_alg: None,
        }
    }

    #[test]
    fn open_succeeds_with_correct_hash() {
        let files = sample_files();
        let bytes = build_sqlite_bytes(&files, "0.0.0").unwrap();
        let path = write_temp(&bytes);
        let sha = format!("sha256:{}", compute_sha(&bytes));
        let m = manifest_with_sha(Some(sha));
        let stream = PackStream::open(&path, &m).unwrap();
        assert!(stream.row_count >= 1);
        let mut taxa = Vec::new();
        for item in stream.open_taxa_producer().unwrap() {
            taxa.push(item.unwrap());
        }
        assert_eq!(taxa.len(), 1);
        assert_eq!(taxa[0].taxon_id, "T000000001");
        assert_eq!(taxa[0].scientific_name, "Test");
        let _ = std::fs::remove_dir_all(path.parent().unwrap());
    }

    #[test]
    fn open_rejects_hash_mismatch() {
        let files = sample_files();
        let bytes = build_sqlite_bytes(&files, "0.0.0").unwrap();
        let path = write_temp(&bytes);
        let m = manifest_with_sha(Some(
            "sha256:0000000000000000000000000000000000000000000000000000000000000000".to_string(),
        ));
        let err = PackStream::open(&path, &m).unwrap_err();
        assert_eq!(err.code, "PACK_HASH_MISMATCH");
        let _ = std::fs::remove_dir_all(path.parent().unwrap());
    }

    #[test]
    fn open_rejects_missing_artifact_sha256() {
        let files = sample_files();
        let bytes = build_sqlite_bytes(&files, "0.0.0").unwrap();
        let path = write_temp(&bytes);
        let m = manifest_with_sha(None);
        let err = PackStream::open(&path, &m).unwrap_err();
        assert_eq!(err.code, "PACK_INVALID");
        let _ = std::fs::remove_dir_all(path.parent().unwrap());
    }

    #[test]
    fn open_taxa_producer_yields_rows() {
        let files = sample_files();
        let bytes = build_sqlite_bytes(&files, "0.0.0").unwrap();
        let path = write_temp(&bytes);
        let sha = format!("sha256:{}", compute_sha(&bytes));
        let m = manifest_with_sha(Some(sha));
        let stream = PackStream::open(&path, &m).unwrap();
        let mut got = Vec::new();
        for item in stream.open_taxa_producer().unwrap() {
            got.push(item.unwrap());
        }
        assert_eq!(got.len(), 1);
        assert_eq!(got[0].taxon_id, "T000000001");
        let _ = std::fs::remove_dir_all(path.parent().unwrap());
    }
}
