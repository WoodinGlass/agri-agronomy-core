//! `compute_request_id` matching `src/agri_core/models/envelope.py`.

use crate::canonical::canonical_json;
use crate::hash::sha256_hex;
use serde_json::{json, Value};

pub fn compute_request_id(
    subject: Option<&Value>,
    inputs: &Value,
    engine_version: &str,
    pack_hash: Option<&str>,
) -> Result<String, String> {
    let payload = json!({
        "subject": subject.cloned().unwrap_or(Value::Null),
        "inputs": inputs,
        "engine_version": engine_version,
        "pack_hash": pack_hash,
    });
    let bytes = canonical_json(&payload).map_err(|e| format!("{e}"))?;
    let hex = sha256_hex(&bytes);
    Ok(format!("req_{}", &hex[..32]))
}
