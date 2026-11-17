//! Real corpus: sample pack + wishlist (D4, ADR-019 §11.14).
//!
//! Every name in `src/agri_core/_samples/sample_pack/names.csv` and every
//! cell in `docs/design/plant_wishlist_v4.csv` is normalized; the test
//! asserts no panic and idempotence. Not a parity test (which D2 covers
//! via the golden sweep); this is a "real data does not blow up the
//! normalizer" smoke test.
//!
//! If the wishlist file is absent (e.g. partial checkout), the test skips
//! the wishlist portion without failing.

use std::path::PathBuf;

use agri_kernel::pack::normalize::normalize_name;

fn repo_root() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("..")
        .join("..")
}

fn check_name(name: &str, source: &str) {
    let once = normalize_name(name);
    let twice = normalize_name(&once);
    assert_eq!(
        once, twice,
        "not idempotent for {source} name {name:?}: once={once:?}, twice={twice:?}"
    );
}

#[test]
fn sample_pack_names_idempotent() {
    let path = repo_root()
        .join("src")
        .join("agri_core")
        .join("_samples")
        .join("sample_pack")
        .join("names.csv");
    let content = std::fs::read_to_string(&path).expect("read sample pack names.csv");

    // Simple CSV parser: skip header, extract column 2 (name). Names may
    // contain commas and quotes; handle RFC 4180-style quoting minimally.
    for (i, line) in content.lines().enumerate() {
        if i == 0 {
            continue; // header
        }
        if line.trim().is_empty() {
            continue;
        }
        // Parse: split on ',' respecting quotes
        let mut cols: Vec<String> = Vec::new();
        let mut cur = String::new();
        let mut in_q = false;
        for ch in line.chars() {
            if in_q {
                if ch == '"' {
                    in_q = false;
                } else {
                    cur.push(ch);
                }
            } else if ch == '"' {
                in_q = true;
            } else if ch == ',' {
                cols.push(std::mem::take(&mut cur));
            } else {
                cur.push(ch);
            }
        }
        cols.push(cur);
        if cols.len() >= 2 && !cols[1].is_empty() {
            check_name(&cols[1], "sample_pack");
        }
    }
}

#[test]
fn wishlist_names_idempotent() {
    let path = repo_root()
        .join("docs")
        .join("design")
        .join("plant_wishlist_v4.csv");
    let content = match std::fs::read_to_string(&path) {
        Ok(c) => c,
        Err(_) => return, // wishlist optional in partial checkout
    };

    // Generic: normalize every non-empty string cell (any column).
    for (i, line) in content.lines().enumerate() {
        if i == 0 {
            continue;
        }
        if line.trim().is_empty() {
            continue;
        }
        // Same minimal CSV parser
        let mut cols: Vec<String> = Vec::new();
        let mut cur = String::new();
        let mut in_q = false;
        for ch in line.chars() {
            if in_q {
                if ch == '"' {
                    in_q = false;
                } else {
                    cur.push(ch);
                }
            } else if ch == '"' {
                in_q = true;
            } else if ch == ',' {
                cols.push(std::mem::take(&mut cur));
            } else {
                cur.push(ch);
            }
        }
        cols.push(cur);
        for cell in &cols {
            if cell.trim().is_empty() {
                continue;
            }
            check_name(cell, "wishlist");
        }
    }
}
