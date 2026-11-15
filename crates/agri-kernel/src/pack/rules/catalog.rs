//! Rule: `check_catalog_excluded_extension` (ADR-012).
//!
//! # Port status
//!
//! Dormant until excluded param IDs are ported from generated Python
//! (`catalog/_excluded_generated.py`). Current Phase D inputs (sample pack,
//! 10k synthetic pack) contain zero extension parameters, so Python's rule
//! also returns empty on those inputs. Cell 6 parity tests verify match.

use super::{Finding, RuleContext};

#[allow(dead_code)]
pub const CODE: &str = "PACK_CATALOG_EXCLUDED_PARAMETER";

pub fn check(ctx: &RuleContext<'_>) -> Vec<Finding> {
    // Dormant. See module docs.
    let _ = ctx;
    Vec::new()
}

#[cfg(test)]
#[allow(clippy::unwrap_used, clippy::expect_used, clippy::panic)]
mod tests {
    use super::*;
    use crate::pack::dict_info::DictionaryInfo;
    use crate::pack::rules::EMPTY_FILES;

    #[test]
    fn empty_dictionary_no_findings() {
        let d = DictionaryInfo::empty();
        let ctx = RuleContext {
            taxa: &[],
            names: &[],
            facts: &[],
            hazards: &[],
            sources: &[],
            datasets: &[],
            files: &EMPTY_FILES,
            dictionary: &d,
        };
        assert!(check(&ctx).is_empty());
    }
}
