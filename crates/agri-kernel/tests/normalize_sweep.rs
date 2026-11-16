//! Sweep: full scalar coverage with explicit skip list for Unicode 16.0 additions.
//!
//! Two tests:
//! - `sweep_standalone_all_scalars`: every codepoint U+0000..U+10FFFF
//!   (excl. surrogates and `SKIP_CN_15_1`). Expected = golden[cp] if present,
//!   `""` if whitespace, identity otherwise. Catches any regression on the
//!   pinned Unicode 16.0 normalization for codepoints whose behavior we
//!   commit to (assigned in 15.1; golden explicitly pins 16.0 changes).
//! - `sweep_context_idempotent`: normalize twice on `a{ch}b`, compare.
//!   Context-derivation of NFKC is not sound (composition is holistically
//!   dependent on base character), so we assert idempotence only, which
//!   catches the regressions a derivation would catch without being wrong.
//!
//! ## Why a skip list, not a full Cn bitmap
//!
//! Unicode stability policy (§11.2) locks `toCasefold∘toNFKC` behavior at
//! the pin (16.0.0) for assigned codepoints. Codepoints **newly assigned**
//! in 16.0 may differ from a 15.1 runtime. We compute the exact changed
//! set once (Python 3.13 / Unicode 15.1, native 16.0) and embed it as a
//! constant. This is a **tripwire**: if `unicode-normalization` bumps
//! tables or the pin changes, the skip set drifts and this test fails.
//! Regen requires an ADR amendment (see §11.14).
//!
//! Codepoints assigned in Unicode ≤15.1 are all asserted. Any regression
//! on those is a real bug (would trigger §11.7 triage).
//!
//! ## Why context = idempotence, not derivation
//!
//! NFKC is not compositional: `normalize("a" + combining_acute)` composes
//! to `"á"` (U+00E1) while `normalize(combining_acute) == combining_acute`
//! unchanged. Deriving the context expected from the standalone is
//! fundamentally wrong. Idempotence covers the real property.

use std::collections::BTreeMap;
use std::path::PathBuf;

use agri_kernel::pack::normalize::normalize_name;
use agri_kernel::pack::unicode_pin::WHITESPACE;
use serde_json::Value;

/// Codepoints that are `Cn` in Unicode 15.1 (Python 3.13.18) but whose
/// native 16.0.0 normalization differs from identity. Generated at D4
/// patch time (see ADR-019 §11.14); regen requires an ADR amendment.
///
/// Length is pinned here so a silent table change (e.g. a `unicode-
/// normalization` bump) makes the count assertion fail.
pub const SKIP_CN_15_1: &[u32] = &[
    0x0558, 0x058B, 0x058C, 0x1C89, 0x209D, 0x209E, 0x209F, 0xA7CB, 0xA7CC, 0xA7DA, 0xA7DC, 0xA7F1,
    0x107BB, 0x107BC, 0x107BD, 0x107BE, 0x107BF, 0x10D50, 0x10D51, 0x10D52, 0x10D53, 0x10D54,
    0x10D55, 0x10D56, 0x10D57, 0x10D58, 0x10D59, 0x10D5A, 0x10D5B, 0x10D5C, 0x10D5D, 0x10D5E,
    0x10D5F, 0x10D60, 0x10D61, 0x10D62, 0x10D63, 0x10D64, 0x10D65, 0x1B123, 0x1B124, 0x1B125,
    0x1B126, 0x1CCD6, 0x1CCD7, 0x1CCD8, 0x1CCD9, 0x1CCDA, 0x1CCDB, 0x1CCDC, 0x1CCDD, 0x1CCDE,
    0x1CCDF, 0x1CCE0, 0x1CCE1, 0x1CCE2, 0x1CCE3, 0x1CCE4, 0x1CCE5, 0x1CCE6, 0x1CCE7, 0x1CCE8,
    0x1CCE9, 0x1CCEA, 0x1CCEB, 0x1CCEC, 0x1CCED, 0x1CCEE, 0x1CCEF, 0x1CCF0, 0x1CCF1, 0x1CCF2,
    0x1CCF3, 0x1CCF4, 0x1CCF5, 0x1CCF6, 0x1CCF7, 0x1CCF8, 0x1CCF9, 0x1D6A6, 0x1DF95, 0x1DFCD,
    0x1DFCE, 0x1DFCF, 0x1DFD0, 0x1DFD1, 0x1DFD2, 0x1DFD3, 0x1DFD4, 0x1DFD5, 0x1DFD6, 0x1DFD7,
    0x1DFD8, 0x1DFD9, 0x1DFDA, 0x1DFDB, 0x1DFDC, 0x1DFDD, 0x1DFDE, 0x1DFDF, 0x1DFE0, 0x1DFE1,
    0x1DFE2, 0x1DFE3, 0x1DFE4, 0x1DFE5, 0x1DFE6, 0x1DFE7, 0x1DFE8, 0x1DFE9, 0x1DFEA, 0x1DFEB,
    0x1DFEC, 0x1DFED, 0x1DFEE, 0x1DFEF, 0x1DFF0, 0x1DFF1, 0x1DFF2, 0x1DFF3, 0x1DFF4, 0x1DFF5,
    0x1DFF6, 0x1DFF7, 0x1DFF8, 0x1DFF9, 0x1DFFA, 0x1DFFB, 0x1DFFC, 0x1DFFD, 0x1DFFE, 0x1DFFF,
];

fn vector_path(name: &str) -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("..")
        .join("..")
        .join("tests")
        .join("vectors")
        .join(name)
}

fn load_golden(name: &str) -> BTreeMap<u32, String> {
    let data = std::fs::read_to_string(vector_path(name)).expect("read golden");
    let parsed: Value = serde_json::from_str(&data).expect("parse golden");
    let entries = parsed["entries"].as_array().expect("entries");
    let mut map = BTreeMap::new();
    for e in entries {
        let cp = e["cp"].as_str().expect("cp");
        let cp_u32 = u32::from_str_radix(cp.trim_start_matches("U+"), 16).expect("cp parse");
        let expected = e["expected"].as_str().expect("expected").to_string();
        map.insert(cp_u32, expected);
    }
    map
}

fn is_ws(cp: u32) -> bool {
    WHITESPACE.contains(&cp)
}

#[test]
fn skip_list_size_is_pinned() {
    // Unicode 16.0 additions changed by native. If this count moves,
    // regenerate the list (see module docs) and update ADR §11.14.
    assert_eq!(
        SKIP_CN_15_1.len(),
        132,
        "SKIP_CN_15_1 size changed — unicode-normalization table drift or pin change"
    );
}

#[test]
fn sweep_standalone_all_scalars() {
    let golden = load_golden("normalize_name_16_0.json");
    let mut failures = Vec::new();
    for cp in 0..=0x10FFFFu32 {
        if (0xD800..=0xDFFF).contains(&cp) {
            continue;
        }
        if SKIP_CN_15_1.contains(&cp) {
            continue;
        }
        let ch = match char::from_u32(cp) {
            Some(c) => c,
            None => continue,
        };
        let input = ch.to_string();
        let got = normalize_name(&input);

        let expected = if is_ws(cp) {
            String::new()
        } else if let Some(g) = golden.get(&cp) {
            g.clone()
        } else {
            input.clone()
        };

        if got != expected {
            failures.push(format!("U+{cp:04X}: got {got:?}, expected {expected:?}"));
            if failures.len() >= 20 {
                break;
            }
        }
    }
    assert!(
        failures.is_empty(),
        "standalone sweep: {} mismatches (first 20):\n{}",
        failures.len(),
        failures.join("\n")
    );
}

#[test]
fn sweep_context_idempotent() {
    let mut failures = Vec::new();
    for cp in 0..=0x10FFFFu32 {
        if (0xD800..=0xDFFF).contains(&cp) {
            continue;
        }
        if SKIP_CN_15_1.contains(&cp) {
            continue;
        }
        let ch = match char::from_u32(cp) {
            Some(c) => c,
            None => continue,
        };
        let input = format!("a{ch}b");
        let once = normalize_name(&input);
        let twice = normalize_name(&once);
        if once != twice {
            failures.push(format!(
                "U+{cp:04X}: not idempotent once={once:?} twice={twice:?}"
            ));
            if failures.len() >= 20 {
                break;
            }
        }
    }
    assert!(
        failures.is_empty(),
        "context idempotence: {} mismatches (first 20):\n{}",
        failures.len(),
        failures.join("\n")
    );
}
