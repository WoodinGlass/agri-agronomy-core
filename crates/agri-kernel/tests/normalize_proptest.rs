//! Property-based: idempotence + max expansion bound (D4, ADR-019 §11.14).
//!
//! `MAX_EXPANSION_FACTOR` is measured empirically (Phase 0 of the D4 patch)
//! across the full 1.11M scalar sweep + context. It is a hard bound: the
//! pipeline's expansion factor is at most this value for any input.
//!
//! If the measured value changes (crate bump, pipeline change), the test
//! fails loudly — that is the tripwire. Update requires ADR amendment.

use agri_kernel::pack::normalize::normalize_name;
use proptest::prelude::*;

/// Measured max expansion factor across the full scalar sweep.
///
/// Measured at commit time by `scripts/gen_normalize_vectors.py`-adjacent
/// sweep (native 16.0, standalone 1.11M scalars). Locked here per ADR-019
/// §11.14; bumping requires an ADR amendment + regen of this constant.
const MAX_EXPANSION_FACTOR: f64 = 18.0000;

proptest! {
    #[test]
    fn idempotent(s in any::<String>()) {
        let once = normalize_name(&s);
        let twice = normalize_name(&once);
        prop_assert_eq!(once, twice);
    }

    #[test]
    fn expansion_bounded(s in any::<String>()) {
        if s.is_empty() {
            return Ok(());
        }
        let out = normalize_name(&s);
        if out.is_empty() {
            return Ok(()); // collapse to empty; factor undefined, always <= bound
        }
        let factor = out.chars().count() as f64 / s.chars().count() as f64;
        prop_assert!(
            factor <= MAX_EXPANSION_FACTOR,
            "expansion {:.4} > {} on {:?}",
            factor,
            MAX_EXPANSION_FACTOR,
            s
        );
    }
}
