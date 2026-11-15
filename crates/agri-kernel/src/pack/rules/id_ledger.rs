//! Rules: `check_id_ledger_absent`, `check_id_ledger_drift` (ADR-011).

use std::collections::BTreeSet;

use super::{py_repr_str, Finding, FindingLocation, RuleContext};

pub const CODE_ABSENT: &str = "PACK_ID_LEDGER_ABSENT";
pub const CODE_DRIFT: &str = "PACK_ID_LEDGER_DRIFT";
const LEDGER: &str = "ids.lock";

pub fn check_absent(ctx: &RuleContext<'_>) -> Vec<Finding> {
    if ctx.files.contains_key(LEDGER) {
        return Vec::new();
    }
    vec![Finding::error(
        CODE_ABSENT,
        "pack must declare ids.lock (ADR-011). Bootstrap: `agri-core pack scaffold` on the pack (auto-creates ids.lock from current taxa.csv), or `tail -n +2 taxa.csv | cut -d, -f1 | sort > ids.lock`.".to_string(),
        FindingLocation { file: Some(LEDGER.into()), ..Default::default() },
    )]
}

pub fn check_drift(ctx: &RuleContext<'_>) -> Vec<Finding> {
    let raw = match ctx.files.get(LEDGER) {
        Some(b) => b,
        None => return Vec::new(),
    };
    let text = match std::str::from_utf8(raw) {
        Ok(s) => s,
        Err(_) => return Vec::new(),
    };
    let lock_ids: BTreeSet<&str> = text
        .lines()
        .map(|ln| ln.trim())
        .filter(|ln| !ln.is_empty())
        .collect();
    let mut out = Vec::new();
    for t in ctx.taxa {
        if !lock_ids.contains(t.taxon_id.as_str()) {
            out.push(Finding::error(
                CODE_DRIFT,
                format!(
                    "taxon {} is in taxa.csv but not in ids.lock; append it to ids.lock (do not re-derive; append-only)",
                    py_repr_str(&t.taxon_id)
                ),
                FindingLocation {
                    file: Some("taxa.csv".into()),
                    taxon_id: Some(t.taxon_id.clone()),
                    ..Default::default()
                },
            ));
        }
    }
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
    use crate::pack::row_types::TaxonRow;
    use crate::pack::rules::EMPTY_DICT;
    use std::collections::HashMap;

    fn taxon(id: &str) -> TaxonRow {
        TaxonRow {
            taxon_id: id.into(),
            rank: "species".into(),
            scientific_name: "Test".into(),
            accepted_name: None,
            organism_group: "vascular_plant".into(),
            archetype: "annual".into(),
            uses: vec!["vegetable".into()],
            traits: vec![],
            parent_id: None,
            external_ids: None,
            src: Some(vec!["S001".into()]),
            dataset_id: None,
        }
    }
    fn ctx<'a>(taxa: &'a [TaxonRow], files: &'a HashMap<String, Vec<u8>>) -> RuleContext<'a> {
        RuleContext {
            taxa,
            names: &[],
            facts: &[],
            hazards: &[],
            sources: &[],
            datasets: &[],
            files,
            dictionary: &EMPTY_DICT,
        }
    }

    #[test]
    fn absent_when_no_ledger() {
        let f = HashMap::new();
        assert_eq!(check_absent(&ctx(&[], &f)).len(), 1);
    }
    #[test]
    fn no_absent_when_present() {
        let mut f = HashMap::new();
        f.insert(LEDGER.into(), b"T000000001\n".to_vec());
        assert!(check_absent(&ctx(&[], &f)).is_empty());
    }
    #[test]
    fn drift_when_missing() {
        let mut f = HashMap::new();
        f.insert(LEDGER.into(), b"T000000001\n".to_vec());
        let t = vec![taxon("T000000001"), taxon("T000000002")];
        let out = check_drift(&ctx(&t, &f));
        assert_eq!(out.len(), 1);
        assert_eq!(out[0].code, CODE_DRIFT);
    }
}
