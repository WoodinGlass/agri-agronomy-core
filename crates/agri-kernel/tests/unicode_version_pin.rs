//! Tripwire: Unicode version pin (ADR-019 §11.1, §11.13).
//!
//! Asserts `caseless::UNICODE_VERSION == (16, 0, 0)` and
//! `unicode_normalization::UNICODE_VERSION >= (16, 0)`; the crate ships
//! 18.0 tables at 0.1.26 which are dead for the input we accept (strict
//! mode rejects codepoints unassigned at 16.0, stability policy locks
//! NFKC output for assigned codepoints). The contract string lives at
//! `unicode_pin::UNICODE_VERSION`.

use agri_kernel::pack::unicode_pin::UNICODE_VERSION;

#[test]
fn caseless_unicode_version_is_16_0_0_exact() {
    let (major, minor, patch) = caseless::UNICODE_VERSION;
    assert_eq!(
        (major, minor, patch),
        (16, 0, 0),
        "caseless::UNICODE_VERSION = ({major}, {minor}, {patch}), expected (16, 0, 0). \
         Bumping caseless requires ADR amendment + golden regen (ADR-019 §11.1)."
    );
}

#[test]
fn unicode_normalization_at_least_16_0() {
    let (major, minor, _patch) = unicode_normalization::UNICODE_VERSION;
    assert!(
        (u16::from(major), u16::from(minor)) >= (16u16, 0u16),
        "unicode_normalization::UNICODE_VERSION = ({major}.{minor}) < (16.0). \
         Downgrading the crate below the pin requires ADR amendment (ADR-019 §11.1)."
    );
}

#[test]
fn pinned_string_constant_matches() {
    assert_eq!(
        UNICODE_VERSION, "16.0.0",
        "unicode_pin::UNICODE_VERSION drift"
    );
}
