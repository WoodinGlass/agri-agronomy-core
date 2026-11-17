//! Tripwire: `Cargo.lock` single-version invariant (ADR-019 §11.1, §11.13).
//!
//! Multiple `unicode-normalization` / `caseless` versions in the dependency
//! tree produce table drift: NFKC and casefold could use different Unicode
//! tables. Fail loud on duplicates. ICU4X must be present exactly at 2.4.0
//! (dev-only, third oracle; ADR-019 §11.13).

use std::path::PathBuf;

fn read_cargo_lock() -> String {
    let dir = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
    let path = dir.join("..").join("..").join("Cargo.lock");
    let path = path.canonicalize().expect("Cargo.lock canonicalize");
    std::fs::read_to_string(&path).expect("Cargo.lock read")
}

fn count_package_versions(lock: &str, name: &str) -> Vec<String> {
    let needle = format!("name = \"{name}\"");
    let mut versions = Vec::new();
    let mut lines = lock.lines();
    while let Some(line) = lines.next() {
        if line.trim() == needle {
            if let Some(next) = lines.next() {
                if let Some(v) = next.strip_prefix("version = \"") {
                    if let Some(v) = v.strip_suffix('"') {
                        versions.push(v.to_string());
                    }
                }
            }
        }
    }
    versions
}

#[test]
fn single_unicode_normalization_version() {
    let lock = read_cargo_lock();
    let v = count_package_versions(&lock, "unicode-normalization");
    assert_eq!(
        v.len(),
        1,
        "expected exactly 1 unicode-normalization in Cargo.lock, found {v:?}. \
         Duplicate versions break ADR-019 §11.1 pipeline coherence."
    );
}

#[test]
fn single_caseless_version() {
    let lock = read_cargo_lock();
    let v = count_package_versions(&lock, "caseless");
    assert_eq!(v.len(), 1, "expected exactly 1 caseless, found {v:?}");
}

#[test]
fn icu4x_pinned_dev_only() {
    let lock = read_cargo_lock();
    for name in ["icu_casemap", "icu_normalizer"] {
        let v = count_package_versions(&lock, name);
        assert!(
            !v.is_empty(),
            "{name} missing from Cargo.lock — run `cargo fetch` first"
        );
        assert_eq!(
            v[0], "2.4.0",
            "{name} = {} in Cargo.lock, expected 2.4.0",
            v[0]
        );
        assert_eq!(v.len(), 1, "duplicate {name} versions in Cargo.lock: {v:?}");
    }
}
