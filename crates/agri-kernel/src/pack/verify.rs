//! `hash_pack_files`: SHA-256 over canonical pack content (P1).
//!
//! Algorithm (mirrors Python):
//!
//!   h = sha256(b"agri-pack-hash-v1\n")
//!   for relpath in sorted(files):
//!       content = content_bytes(relpath, files[relpath])
//!       h.update(sha256(content).hexdigest() + "  " + relpath + "\n")
//!   return "sha256:" + h.hexdigest()
//!
//! `content_bytes` normalizes `pack.toml` (parse TOML, strip `content_hash`
//! and `hash_alg`, canonicalize) and LF-normalizes every other file.
//!
//! Datetime values in `pack.toml` are rejected: the pack manifest schema
//! forbids them, and Python's `json.dumps(datetime)` would raise TypeError;
//! we surface a clear ValueError instead of producing divergent bytes.

use std::collections::HashMap;

use sha2::{Digest, Sha256};

use crate::canonical::{canonical_json, canonical_json_rfc8785};
use crate::hash::sha256_hex;

const DOMAIN: &[u8] = b"agri-pack-hash-v1\n";

/// Return `"sha256:<hex>"` over *files* in canonical form.
///
/// *hash_alg* is `"pre-rfc8785"` or `"rfc8785"`; anything else is an error.
pub fn hash_pack_files(files: &HashMap<String, Vec<u8>>, hash_alg: &str) -> Result<String, String> {
    if hash_alg != "pre-rfc8785" && hash_alg != "rfc8785" {
        return Err(format!(
            "hash_alg must be 'pre-rfc8785' or 'rfc8785', got {hash_alg:?}"
        ));
    }
    let pack_toml = files
        .get("pack.toml")
        .ok_or_else(|| "pack.toml missing from files mapping".to_string())?;

    let mut sorted_keys: Vec<&String> = files.keys().collect();
    sorted_keys.sort();

    let mut hasher = Sha256::new();
    hasher.update(DOMAIN);

    for relpath in sorted_keys {
        let data = &files[relpath];
        let content: Vec<u8> = if relpath == "pack.toml" {
            pack_toml_content(data, hash_alg)?
        } else {
            normalize_lf(data)
        };
        let content_hex = sha256_hex(&content);
        hasher.update(format!("{content_hex}  {relpath}\n").as_bytes());
    }

    let digest = hasher.finalize();
    let mut out = String::with_capacity(7 + digest.len() * 2);
    out.push_str("sha256:");
    for b in digest.iter() {
        use std::fmt::Write;
        let _ = write!(out, "{b:02x}");
    }
    // Silence unused warning if `pack_toml` binding no longer referenced.
    let _ = pack_toml;
    Ok(out)
}

fn normalize_lf(data: &[u8]) -> Vec<u8> {
    // Python oracle: data.replace(b"\r\n", b"\n").replace(b"\r", b"\n").
    // Handles \r\n -> \n, lone \r -> \n. Iterator-based (no indexing;
    // clippy::indexing_slicing is denied).
    let mut out = Vec::with_capacity(data.len());
    let mut prev_was_cr = false;
    for &b in data {
        if b == b'\n' && prev_was_cr {
            prev_was_cr = false;
            continue;
        }
        prev_was_cr = b == b'\r';
        out.push(if b == b'\r' { b'\n' } else { b });
    }
    out
}

fn pack_toml_content(data: &[u8], hash_alg: &str) -> Result<Vec<u8>, String> {
    let text =
        std::str::from_utf8(data).map_err(|e| format!("pack.toml is not valid UTF-8: {e}"))?;
    let parsed: toml::Value =
        toml::from_str(text).map_err(|e| format!("pack.toml is not valid TOML: {e}"))?;
    let table = match &parsed {
        toml::Value::Table(t) => t,
        _ => return Err("pack.toml root must be a table".to_string()),
    };
    let mut tbl = table.clone();
    tbl.remove("content_hash");
    tbl.remove("hash_alg");
    let json = toml_to_json(&toml::Value::Table(tbl))?;

    match hash_alg {
        "pre-rfc8785" => canonical_json(&json).map_err(|e| format!("{e}")),
        "rfc8785" => canonical_json_rfc8785(&json).map_err(|e| format!("{e}")),
        _ => Err(format!("unknown hash_alg: {hash_alg:?}")),
    }
}

fn toml_to_json(v: &toml::Value) -> Result<serde_json::Value, String> {
    match v {
        toml::Value::String(s) => Ok(serde_json::Value::String(s.clone())),
        toml::Value::Integer(i) => Ok(serde_json::Value::Number((*i).into())),
        toml::Value::Float(f) => {
            let n = serde_json::Number::from_f64(*f)
                .ok_or_else(|| "non-finite float in pack.toml".to_string())?;
            Ok(serde_json::Value::Number(n))
        }
        toml::Value::Boolean(b) => Ok(serde_json::Value::Bool(*b)),
        toml::Value::Datetime(_) => Err("datetime values are not supported in pack.toml; \
             mirrors Python TypeError on json.dumps(datetime)"
            .to_string()),
        toml::Value::Array(arr) => {
            let items: Result<Vec<_>, _> = arr.iter().map(toml_to_json).collect();
            Ok(serde_json::Value::Array(items?))
        }
        toml::Value::Table(tbl) => {
            let mut map = serde_json::Map::new();
            for (k, v) in tbl {
                map.insert(k.clone(), toml_to_json(v)?);
            }
            Ok(serde_json::Value::Object(map))
        }
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

    fn mk(pairs: &[(&str, &[u8])]) -> HashMap<String, Vec<u8>> {
        let mut m = HashMap::new();
        for (k, v) in pairs {
            m.insert((*k).to_string(), v.to_vec());
        }
        m
    }

    #[test]
    fn minimal_pack_produces_hash() {
        let files = mk(&[
            ("pack.toml", b"name = \"t\"\nversion = \"1.0.0\"\nschema_version = 1\nengine_min = \"0.0.0\"\ndictionary_min = \"1.0.0\"\n"),
            ("sources.csv", b"id,url,license,commercial_use,access_date,citation\n"),
        ]);
        let h = hash_pack_files(&files, "pre-rfc8785").expect("hash");
        assert!(h.starts_with("sha256:"));
        assert_eq!(h.len(), "sha256:".len() + 64);
    }

    #[test]
    fn hash_alg_is_stripped() {
        let base = b"name = \"t\"\nversion = \"1.0.0\"\nschema_version = 1\nengine_min = \"0.0.0\"\ndictionary_min = \"1.0.0\"\n";
        let with_alg = b"name = \"t\"\nversion = \"1.0.0\"\nschema_version = 1\nengine_min = \"0.0.0\"\ndictionary_min = \"1.0.0\"\nhash_alg = \"rfc8785\"\n";
        let f1 = mk(&[("pack.toml", base), ("sources.csv", b"")]);
        let f2 = mk(&[("pack.toml", with_alg), ("sources.csv", b"")]);
        let h1 = hash_pack_files(&f1, "pre-rfc8785").unwrap();
        let h2 = hash_pack_files(&f2, "pre-rfc8785").unwrap();
        assert_eq!(h1, h2);
    }

    #[test]
    fn unknown_hash_alg_rejected() {
        let f = mk(&[("pack.toml", b"name = \"t\"\n")]);
        assert!(hash_pack_files(&f, "bogus").is_err());
    }

    #[test]
    fn missing_pack_toml_rejected() {
        let f = mk(&[("sources.csv", b"x")]);
        let err = hash_pack_files(&f, "pre-rfc8785").unwrap_err();
        assert!(err.starts_with("pack.toml missing"));
    }

    #[test]
    fn datetime_rejected() {
        let f = mk(&[("pack.toml", b"name = 2026-01-01T00:00:00Z\n")]);
        let err = hash_pack_files(&f, "pre-rfc8785").unwrap_err();
        assert!(err.contains("datetime"));
    }

    #[test]
    fn crlf_and_bare_cr_normalized() {
        let base = b"name = \"t\"\nversion = \"1.0.0\"\n";
        let f1 = mk(&[("pack.toml", base), ("sources.csv", b"a\nb\n")]);
        let f2 = mk(&[("pack.toml", base), ("sources.csv", b"a\r\nb\r\n")]);
        let f3 = mk(&[("pack.toml", base), ("sources.csv", b"a\rb\r")]);
        let h1 = hash_pack_files(&f1, "pre-rfc8785").unwrap();
        let h2 = hash_pack_files(&f2, "pre-rfc8785").unwrap();
        let h3 = hash_pack_files(&f3, "pre-rfc8785").unwrap();
        assert_eq!(h1, h2);
        assert_eq!(h1, h3);
    }
}
