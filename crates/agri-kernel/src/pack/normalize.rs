//! Name and scope-value normalization (mirror of pack/normalize.py).
//!
//! Pipeline per ADR-019 §11.3:
//!   1. NFKC (Unicode 16.0 tables, via unicode-normalization)
//!   2. Full case folding (Unicode 16.0 tables, via caseless)
//!   3. Hybrid lift (normalize_name only): U+00D7 -> ASCII x
//!   4. NFC re-canonicalization (Unicode 16.0 tables, via unicode-normalization)
//!      Composes combining sequences the fold/lift produced so the output
//!      is idempotent under a second pass.
//!   5. Whitespace collapse against pack::unicode_pin::WHITESPACE
//!
//! Byte-identical to Python's `normalize_name` / `normalize_scope_value`
//! for codepoints <= Unicode 15.1.0 (ADR §11.2 version-minimum contract).

use caseless::default_case_fold_str;
use unicode_normalization::UnicodeNormalization;

use crate::pack::unicode_pin::WHITESPACE;

const HYBRID_SIGN: char = '\u{00D7}';
const HYBRID_LIFT: &str = "x";

/// Normalize a taxon name for matching (mirror of `normalize_name`).
pub fn normalize_name(s: &str) -> String {
    if s.is_empty() {
        return String::new();
    }
    let nfkc: String = s.nfkc().collect();
    let folded = default_case_fold_str(&nfkc);
    let lifted = folded.replace(HYBRID_SIGN, HYBRID_LIFT);
    let canonical: String = lifted.nfc().collect();
    collapse_whitespace(&canonical)
}

/// Normalize a scope value for matching (mirror of `normalize_scope_value`).
///
/// Same as `normalize_name` without the hybrid lift.
pub fn normalize_scope_value(s: &str) -> String {
    if s.is_empty() {
        return String::new();
    }
    let nfkc: String = s.nfkc().collect();
    let folded = default_case_fold_str(&nfkc);
    let canonical: String = folded.nfc().collect();
    collapse_whitespace(&canonical)
}

/// Collapse runs of `WHITESPACE` codepoints to single ASCII space.
///
/// Matches Python's `" ".join(s.split())`:
/// - leading/trailing whitespace stripped
/// - runs collapsed to single space
fn collapse_whitespace(s: &str) -> String {
    let mut out = String::with_capacity(s.len());
    let mut in_ws_run = false;
    let mut first = true;
    for ch in s.chars() {
        if WHITESPACE.contains(&(ch as u32)) {
            if !first {
                in_ws_run = true;
            }
            // skip leading whitespace entirely
        } else {
            if in_ws_run {
                out.push(' ');
                in_ws_run = false;
            }
            out.push(ch);
            first = false;
        }
    }
    // trailing in_ws_run is dropped (no push)
    out
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
    fn empty_input() {
        assert_eq!(normalize_name(""), "");
        assert_eq!(normalize_scope_value(""), "");
    }

    #[test]
    fn nfkc_ligatures() {
        assert_eq!(normalize_name("\u{FB01}"), "fi"); // ﬁ
        assert_eq!(normalize_name("\u{FB03}"), "ffi"); // ﬃ
    }

    #[test]
    fn casefold_ss() {
        assert_eq!(normalize_name("\u{00DF}"), "ss"); // ß
        assert_eq!(normalize_name("\u{1E9E}"), "ss"); // ẞ
    }

    #[test]
    fn hybrid_lift_name_only() {
        assert_eq!(normalize_name("a\u{00D7}b"), "axb");
        assert_eq!(normalize_scope_value("a\u{00D7}b"), "a\u{00D7}b");
    }

    #[test]
    fn whitespace_collapse_ascii() {
        assert_eq!(normalize_name("  a  b  "), "a b");
        assert_eq!(normalize_name("a\tb"), "a b");
        assert_eq!(normalize_name("a\nb"), "a b");
        assert_eq!(normalize_name("a\r\nb"), "a b");
    }

    #[test]
    fn whitespace_collapse_unicode() {
        assert_eq!(normalize_name("a\u{00A0}b"), "a b"); // NBSP
        assert_eq!(normalize_name("a\u{2000}b"), "a b");
        assert_eq!(normalize_name("a\u{3000}b"), "a b");
    }

    #[test]
    fn whitespace_control_separators() {
        // Python's split treats U+001C-U+001F as separators
        assert_eq!(normalize_name("a\u{001C}b"), "a b");
        assert_eq!(normalize_name("a\u{001F}b"), "a b");
    }

    #[test]
    fn idempotent() {
        for s in [
            "Testus × hybridus",
            "  a  b  ",
            "ﬁx",
            "Test",
            "\u{00D7}\u{0307}",
            "\u{00D7}\u{0308}",
            "\u{01F0}",
            "j\u{030C}",
        ] {
            let once = normalize_name(s);
            let twice = normalize_name(&once);
            assert_eq!(once, twice, "not idempotent: {s:?}");
        }
    }

    #[test]
    fn output_is_nfc_canonical() {
        // ADR-019 §11.3 step 4: NFC re-canonicalization
        assert_eq!(normalize_name("\u{00D7}\u{0307}"), "\u{1E8B}");
        assert_eq!(normalize_name("\u{00D7}\u{0308}"), "\u{1E8D}");
        assert_eq!(normalize_name("\u{01F0}"), "\u{01F0}");
        assert_eq!(normalize_name("j\u{030C}"), "\u{01F0}");
    }

    #[test]
    fn scope_no_hybrid() {
        assert_eq!(
            normalize_scope_value("Testus × Hybridus"),
            "testus × hybridus"
        );
        assert_eq!(normalize_name("Testus × Hybridus"), "testus x hybridus");
    }
}
