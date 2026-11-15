//! Unicode 16.0.0 pin: whitespace + unstable-at-pin codepoint lists.
//!
//! See ADR-019 §11.1 (version pin) and §11.4 (whitespace + strict mode).
//!
//! `WHITESPACE` was derived by sweeping `("a" + chr(cp) + "b").split()`
//! under Python 3.13.18 (Unicode 15.1.0) over U+0000..U+10FFFF. It
//! captures exactly the codepoints that Python's `str.split()` treats as
//! whitespace delimiters, including U+001C-U+001F (which are control
//! characters in Rust but whitespace to Python's splitter). Both
//! `normalize_name` and `normalize_scope_value` collapse runs of these
//! codepoints into a single ASCII space.
//!
//! `unstable_at_pin()` reports codepoints whose NFKC/casefold behavior
//! we do **not** vouch for at the pin. Structural cases (surrogates,
//! noncharacters, private-use, controls) are hardcoded. Unassigned-at-16.0
//! detection is deferred: G4-2 treats codepoints not in the structural
//! set as stable. A full UCD 16.0 table lands in G4-4 with the strict-mode
//! enforcement path; until then `unstable_at_pin()` under-reports, which
//! is safe (no false rejection).

/// Codepoints Python's `str.split()` collapses at Unicode 15.1.0.
///
/// Derived empirically: `("a" + chr(cp) + "b").split() == ["a", "b"]`.
pub const WHITESPACE: &[u32] = &[
    0x0009, 0x000A, 0x000B, 0x000C, 0x000D, 0x001C, 0x001D, 0x001E, 0x001F, 0x0020, 0x0085, 0x00A0,
    0x1680, 0x2000, 0x2001, 0x2002, 0x2003, 0x2004, 0x2005, 0x2006, 0x2007, 0x2008, 0x2009, 0x200A,
    0x2028, 0x2029, 0x202F, 0x205F, 0x3000,
];

pub fn is_whitespace_at_pin(cp: u32) -> bool {
    WHITESPACE.contains(&cp)
}

/// Structural reasons a codepoint is unstable at the pin, or `None`.
///
/// Covers surrogates, noncharacters, private-use, and controls. Does
/// **not** cover unassigned-at-16.0 (deferred to G4-4).
pub fn unstable_at_pin(cp: u32) -> Option<&'static str> {
    // Surrogates U+D800..=U+DFFF.
    if (0xD800..=0xDFFF).contains(&cp) {
        return Some("surrogate");
    }
    // Noncharacters: U+FDD0..=U+FDEF, U+FFFE, U+FFFF, U+1FFFE, ... U+10FFFE, U+10FFFF.
    if (0xFDD0..=0xFDEF).contains(&cp) || (cp & 0xFFFE) == 0xFFFE {
        return Some("noncharacter");
    }
    // Private use: BMP U+E000..=U+F8FF, plane 15-16 U+F0000..=U+10FFFD.
    if (0xE000..=0xF8FF).contains(&cp)
        || (0xF0000..=0xFFFFD).contains(&cp)
        || (0x100000..=0x10FFFD).contains(&cp)
    {
        return Some("private-use");
    }
    // C0 controls (U+0000..=U+001F), DEL (U+007F), C1 controls (U+0080..=U+009F).
    // Note: tab/LF/CR are also in `WHITESPACE`, but they are still structural
    // controls; strict mode rejects regardless of whitespace treatment.
    if cp < 0x20 || cp == 0x7F || (0x80..=0x9F).contains(&cp) {
        return Some("control");
    }
    None
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
    fn whitespace_count_matches_python_sweep() {
        assert_eq!(WHITESPACE.len(), 29);
    }

    #[test]
    fn whitespace_includes_control_separators() {
        // Python's str.split() treats U+001C-U+001F as separators.
        for cp in [0x001C, 0x001D, 0x001E, 0x001F] {
            assert!(
                is_whitespace_at_pin(cp),
                "U+{:04X} should be whitespace",
                cp
            );
        }
    }

    #[test]
    fn whitespace_includes_nbsp_and_common() {
        for cp in [0x0009, 0x000A, 0x0020, 0x00A0, 0x2000, 0x3000, 0x3000] {
            assert!(
                is_whitespace_at_pin(cp),
                "U+{:04X} should be whitespace",
                cp
            );
        }
    }

    #[test]
    fn whitespace_excludes_zwsp_and_mongolian() {
        // U+200B ZWSP and U+180E MVS are not split points.
        assert!(!is_whitespace_at_pin(0x200B));
        assert!(!is_whitespace_at_pin(0x180E));
    }

    #[test]
    fn unstable_structural() {
        assert_eq!(unstable_at_pin(0xD800), Some("surrogate"));
        assert_eq!(unstable_at_pin(0xFDD0), Some("noncharacter"));
        assert_eq!(unstable_at_pin(0xFFFE), Some("noncharacter"));
        assert_eq!(unstable_at_pin(0xE000), Some("private-use"));
        assert_eq!(unstable_at_pin(0x0000), Some("control"));
        assert_eq!(unstable_at_pin(0x007F), Some("control"));
        assert_eq!(unstable_at_pin(0x0085), Some("control"));
        assert_eq!(unstable_at_pin(0x0041), None); // 'A' is stable
        assert_eq!(unstable_at_pin(0x4E00), None); // CJK
    }
}
