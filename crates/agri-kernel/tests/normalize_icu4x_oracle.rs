//! Third-oracle parity: ICU4X vs native normalize (ADR-019 §11.7, §11.13).
//!
//! `#[ignore]` — nightly only. ICU4X is dev-only, not shipped. The pipeline
//! must equal `agri_kernel::pack::normalize::normalize_name` on
//! representative inputs so the semantics have independent corroboration
//! (Unicode-3.0 license is in the deny.toml allowlist).
//!
//! Run locally: `cargo test --test normalize_icu4x_oracle -- --ignored`
//! Nightly CI:  `.github/workflows/rust.yml` job `icu4x-oracle`.

use agri_kernel::pack::normalize::normalize_name;
use agri_kernel::pack::unicode_pin::WHITESPACE;

fn ref_pipeline_icu4x(s: &str) -> String {
    // NFKC via ICU4X ComposingNormalizer; CaseMapper::new() uses the
    // compiled_data feature (default). Both constructors return borrowed
    // static types backed by baked data.
    let nfkc = icu_normalizer::ComposingNormalizer::new_nfkc();
    let nfkc_cow = nfkc.normalize(s);
    let case = icu_casemap::CaseMapper::new();
    let folded_cow = case.fold_string(nfkc_cow.as_ref());
    // Hybrid lift + whitespace collapse: identical shape to
    // `agri_kernel::pack::normalize::normalize_name`.
    let lifted = folded_cow.replace('\u{00D7}', "x");
    let mut out = String::with_capacity(lifted.len());
    let mut in_ws = false;
    for ch in lifted.chars() {
        if WHITESPACE.contains(&(ch as u32)) {
            if !out.is_empty() && !in_ws {
                out.push(' ');
            }
            in_ws = true;
        } else {
            out.push(ch);
            in_ws = false;
        }
    }
    while out.ends_with(' ') {
        out.pop();
    }
    out
}

#[test]
#[ignore = "D3: ICU4X third-oracle parity, nightly only"]
fn icu4x_pipeline_matches_native_on_representative_cases() {
    let cases: &[(&str, &str)] = &[
        ("A", "a"),
        ("\u{00C5}", "\u{00E5}"),                          // A-ring
        ("\u{00DF}", "ss"),                                // sharp s
        ("\u{0132}", "ij"),                                // IJ ligature
        ("\u{FB03}", "ffi"),                               // ffi ligature
        ("\u{0130}", "i\u{0307}"),                         // dotted capital I
        ("\u{01C6}", "d\u{017E}"),                         // dz with caron
        ("\u{00D7} hybridus", "x hybridus"),               // hybrid lift
        ("  Testus\u{00A0}annualis  ", "testus annualis"), // collapse
        ("Stra\u{00DF}e", "strasse"),
        ("\u{1E9E}", "ss"), // capital sharp s
    ];
    for (input, expected) in cases {
        let native = normalize_name(input);
        let icu4x = ref_pipeline_icu4x(input);
        assert_eq!(
            native, *expected,
            "native mismatch on {input:?}: got {native:?}, expected {expected:?}"
        );
        assert_eq!(
            icu4x, native,
            "ICU4X vs native mismatch on {input:?}: icu4x={icu4x:?}, native={native:?}"
        );
    }
}
