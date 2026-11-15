//! 16-rule orchestration + sort by `_sort_key`.
//!
//! Called from `agri-py` binding after `load_knowledge_set_from_files`
//! (Python) has already run `_validate_structure` — so rules operate on
//! valid rows only. Structure findings come via the Python exception path
//! (see `validate_pack_report` docstring).

use std::collections::HashMap;

use super::rules;
use super::rules::Finding;
use crate::pack::dict_info::DictionaryInfo;
use crate::pack::row_types::{DatasetRow, FactRow, HazardRow, NameRow, SourceRow, TaxonRow};

/// Python `_sort_key` parity: `(file, line, key, taxon_id, code)`.
fn sort_key(f: &Finding) -> (String, usize, String, String, String) {
    (
        f.location.file.clone().unwrap_or_default(),
        f.location.line.unwrap_or(0),
        f.location.key.clone().unwrap_or_default(),
        f.location.taxon_id.clone().unwrap_or_default(),
        f.code.to_string(),
    )
}

/// Run all 16 registered rules + return findings sorted by `_sort_key`.
#[allow(clippy::too_many_arguments)]
pub fn run_rules(
    taxa: &[TaxonRow],
    names: &[NameRow],
    facts: &[FactRow],
    hazards: &[HazardRow],
    sources: &[SourceRow],
    datasets: &[DatasetRow],
    files: &HashMap<String, Vec<u8>>,
    dictionary: &DictionaryInfo,
) -> Vec<Finding> {
    let ctx = rules::RuleContext {
        taxa,
        names,
        facts,
        hazards,
        sources,
        datasets,
        files,
        dictionary,
    };
    let mut out: Vec<Finding> = Vec::new();
    out.extend(rules::trapezoid::check(&ctx));
    out.extend(rules::superseded::check_self(&ctx));
    out.extend(rules::superseded::check_cycle(&ctx));
    out.extend(rules::fact_key::check(&ctx));
    out.extend(rules::license::check_source_nc_commercial(&ctx));
    out.extend(rules::license::check_dataset_sa_nd(&ctx));
    out.extend(rules::license::check_source_commercial_use_required(&ctx));
    out.extend(rules::license::check_source_allowlist(&ctx));
    out.extend(rules::license::check_dataset_allowlist(&ctx));
    out.extend(rules::license::check_source_pd_basis(&ctx));
    out.extend(rules::safety::check(&ctx));
    out.extend(rules::protection::check_param_out_of_scope(&ctx));
    out.extend(rules::protection::check_hazard_out_of_scope(&ctx));
    out.extend(rules::id_ledger::check_absent(&ctx));
    out.extend(rules::id_ledger::check_drift(&ctx));
    out.extend(rules::catalog::check(&ctx));
    out.sort_by_key(sort_key);
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
    use crate::pack::dict_info::DictionaryInfo;
    use std::collections::HashMap;

    #[test]
    fn empty_input_yields_id_ledger_absent_only() {
        // Empty files {} has no ids.lock -> id_ledger::check_absent fires.
        // This matches Python: a pack without ids.lock always produces
        // PACK_ID_LEDGER_ABSENT (ADR-011). All other 15 rules return empty.
        let out = run_rules(
            &[],
            &[],
            &[],
            &[],
            &[],
            &[],
            &HashMap::new(),
            &DictionaryInfo::empty(),
        );
        assert_eq!(out.len(), 1, "expected exactly 1 finding, got: {out:?}");
        assert_eq!(out[0].code, "PACK_ID_LEDGER_ABSENT");
    }

    #[test]
    fn sort_key_orders_by_file_then_code() {
        use super::rules::{FindingLocation, Severity};
        let mut a = Finding {
            code: "ZZZ_CODE",
            severity: Severity::Error,
            message: "x".into(),
            location: FindingLocation::default(),
        };
        let mut b = Finding {
            code: "AAA_CODE",
            severity: Severity::Error,
            message: "x".into(),
            location: FindingLocation::default(),
        };
        let mut c = Finding {
            code: "AAA_CODE",
            severity: Severity::Error,
            message: "x".into(),
            location: FindingLocation {
                file: Some("z.csv".into()),
                ..Default::default()
            },
        };
        let mut findings = [a.clone(), b.clone(), c.clone()];
        findings.sort_by_key(sort_key);
        // file=="" sorts before "z.csv"; empty file has two codes (AAA < ZZZ)
        assert_eq!(findings[0].code, "AAA_CODE");
        assert_eq!(findings[1].code, "ZZZ_CODE");
        assert_eq!(findings[2].location.file.as_deref(), Some("z.csv"));
        let _ = (&mut a, &mut b, &mut c);
    }
}
