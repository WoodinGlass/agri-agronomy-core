//! Golden vectors: normalize_name / normalize_scope_value parity.
//!
//! Vectors generated under Python 3.13.18 (Unicode 15.1.0). The
//! `assigned_py313` flag allows version-aware skip in the Python
//! parity test (tests/contract/test_native_parity_normalize.py):
//! codepoints assigned after a given Python's Unicode version are
//! skipped there. Rust always runs the full vector set — the pin is
//! Unicode 16.0, and every codepoint in the file has a fixed
//! normalization at 15.1.
//!
//! See ADR-019 §11.1 (pin), §11.2 (version-minimum contract).

use std::path::PathBuf;

use agri_kernel::pack::normalize::{normalize_name, normalize_scope_value};
use serde_json::Value;

fn vector_path(name: &str) -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("..")
        .join("..")
        .join("tests")
        .join("vectors")
        .join(name)
}

fn load_entries(path: &std::path::Path) -> Vec<Value> {
    let data = std::fs::read_to_string(path).expect("read vector file");
    let parsed: Value = serde_json::from_str(&data).expect("parse json");
    parsed["entries"].as_array().expect("entries array").clone()
}

#[test]
fn normalize_name_parity() {
    let path = vector_path("normalize_name_15_1.json");
    let entries = load_entries(&path);
    let mut failures = Vec::new();
    for e in entries.iter() {
        let cp = e["cp"].as_str().expect("cp");
        let input = e["input"].as_str().expect("input");
        let expected = e["expected"].as_str().expect("expected");
        let got = normalize_name(input);
        if got != expected {
            failures.push(format!("{cp}: expected {expected:?}, got {got:?}"));
        }
    }
    assert!(
        failures.is_empty(),
        "normalize_name parity failures ({}):\n{}",
        failures.len(),
        failures
            .iter()
            .take(20)
            .cloned()
            .collect::<Vec<_>>()
            .join("\n")
    );
}

#[test]
fn normalize_scope_value_parity() {
    let path = vector_path("normalize_scope_value_15_1.json");
    let entries = load_entries(&path);
    let mut failures = Vec::new();
    for e in entries.iter() {
        let cp = e["cp"].as_str().expect("cp");
        let input = e["input"].as_str().expect("input");
        let expected = e["expected"].as_str().expect("expected");
        let got = normalize_scope_value(input);
        if got != expected {
            failures.push(format!("{cp}: expected {expected:?}, got {got:?}"));
        }
    }
    assert!(
        failures.is_empty(),
        "normalize_scope_value parity failures ({}):\n{}",
        failures.len(),
        failures
            .iter()
            .take(20)
            .cloned()
            .collect::<Vec<_>>()
            .join("\n")
    );
}
