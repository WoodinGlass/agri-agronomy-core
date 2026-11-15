//! Rule: `check_fact_key_duplicate`.
//!
//! Mirrors `validate.py`. Flags live facts with identical fact key
//! `(taxon_id, parameter, phase, canonical_scope)` and **different**
//! values. Same key with same value across different `src` is
//! corroboration, not a duplicate. Superseded facts are excluded.

use std::collections::BTreeMap;

use crate::pack::row_types::FactRow;

use super::{py_repr_opt_str, py_repr_str, Finding, FindingLocation, RuleContext};

pub const CODE: &str = "PACK_FACT_KEY_DUPLICATE";

type Key = (String, String, Option<String>, String);

pub fn check(ctx: &RuleContext<'_>) -> Vec<Finding> {
    // Python iterates `ks.facts()` in sorted fact_id order. We sort here
    // so `first` (the "kept" row) is always the smallest fact_id.
    let mut facts: Vec<&FactRow> = ctx.facts.iter().collect();
    facts.sort_by(|a, b| a.fact_id.cmp(&b.fact_id));

    let mut by_key: BTreeMap<Key, &FactRow> = BTreeMap::new();
    let mut out = Vec::new();

    for fact in facts {
        if fact.superseded_by.is_some() {
            continue;
        }
        let key: Key = (
            fact.taxon_id.clone(),
            fact.parameter.clone(),
            fact.phase.clone(),
            fact.scope_json.clone(),
        );
        match by_key.entry(key) {
            std::collections::btree_map::Entry::Vacant(e) => {
                e.insert(fact);
            }
            std::collections::btree_map::Entry::Occupied(e) => {
                let first = *e.get();
                if first.value == fact.value {
                    continue;
                }
                out.push(Finding::error(
                    CODE,
                    format!(
                        "conflicting facts for (taxon={}, parameter={}, phase={}, scope={}): {} vs {}; supersede one via superseded_by",
                        fact.taxon_id,
                        py_repr_str(&fact.parameter),
                        py_repr_opt_str(fact.phase.as_deref()),
                        fact.scope_json,
                        first.fact_id,
                        fact.fact_id,
                    ),
                    FindingLocation {
                        taxon_id: Some(fact.taxon_id.clone()),
                        fact_id: Some(fact.fact_id.clone()),
                        parameter: Some(fact.parameter.clone()),
                        phase: fact.phase.clone(),
                        ..Default::default()
                    },
                ));
            }
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
    use crate::pack::row_types::FactValue;

    fn fact_with(
        id: &str,
        param: &str,
        phase: Option<&str>,
        scope_json: &str,
        value: FactValue,
        superseded_by: Option<&str>,
    ) -> FactRow {
        FactRow {
            fact_id: id.to_string(),
            taxon_id: "T000000001".to_string(),
            parameter: param.to_string(),
            phase: phase.map(|s| s.to_string()),
            value,
            scope_json: scope_json.to_string(),
            provenance_kind: "curated".to_string(),
            src: Some(vec!["S001".to_string()]),
            dataset_id: None,
            locator: Some("Table 1".to_string()),
            evidence: "A".to_string(),
            status: "approved".to_string(),
            reviewed_by: Some(vec!["r1".to_string()]),
            reviewed_at: Some("2026-01-01".to_string()),
            superseded_by: superseded_by.map(|s| s.to_string()),
        }
    }

    fn ctx<'a>(facts: &'a [FactRow]) -> RuleContext<'a> {
        use crate::pack::rules::{EMPTY_DICT, EMPTY_FILES};
        RuleContext {
            taxa: &[],
            names: &[],
            facts,
            hazards: &[],
            sources: &[],
            datasets: &[],
            files: &EMPTY_FILES,
            dictionary: &EMPTY_DICT,
        }
    }

    fn scalar(v: f64) -> FactValue {
        FactValue::Scalar {
            unit: "pH".into(),
            value: v,
        }
    }

    #[test]
    fn no_finding_when_no_duplicate() {
        let facts = vec![
            fact_with("F01", "soil_ph", None, "{}", scalar(7.0), None),
            fact_with("F02", "gdd_base", None, "{}", scalar(8.0), None),
        ];
        assert!(check(&ctx(&facts)).is_empty());
    }

    #[test]
    fn no_finding_when_same_value() {
        // Same key, same value -> corroboration, not a duplicate.
        let facts = vec![
            fact_with("F01", "soil_ph", None, "{}", scalar(7.0), None),
            fact_with("F02", "soil_ph", None, "{}", scalar(7.0), None),
        ];
        assert!(check(&ctx(&facts)).is_empty());
    }

    #[test]
    fn finding_when_different_value() {
        let facts = vec![
            fact_with("F01", "soil_ph", None, "{}", scalar(7.0), None),
            fact_with("F02", "soil_ph", None, "{}", scalar(6.5), None),
        ];
        let out = check(&ctx(&facts));
        assert_eq!(out.len(), 1);
        assert_eq!(out[0].code, "PACK_FACT_KEY_DUPLICATE");
        assert_eq!(out[0].severity.as_str(), "error");
        // "first" is F01 (smaller); "vs" is F02
        assert!(
            out[0].message.contains("F01 vs F02"),
            "msg: {}",
            out[0].message
        );
        assert!(out[0].message.contains("parameter='soil_ph'"));
        assert!(out[0].message.contains("phase=None"));
        assert_eq!(out[0].location.fact_id.as_deref(), Some("F02"));
    }

    #[test]
    fn no_finding_when_superseded() {
        // Superseded facts are excluded from this rule.
        let facts = vec![
            fact_with("F01", "soil_ph", None, "{}", scalar(7.0), None),
            fact_with("F02", "soil_ph", None, "{}", scalar(6.5), Some("F03")),
        ];
        assert!(check(&ctx(&facts)).is_empty());
    }

    #[test]
    fn phase_distinguishes_keys() {
        // Different phase -> different key -> no duplicate.
        let facts = vec![
            fact_with("F01", "kc", Some("initial"), "{}", scalar(0.6), None),
            fact_with("F02", "kc", Some("midseason"), "{}", scalar(0.9), None),
        ];
        assert!(check(&ctx(&facts)).is_empty());
    }

    #[test]
    fn scope_distinguishes_keys() {
        let facts = vec![
            fact_with(
                "F01",
                "soil_ph",
                None,
                r#"{"system":"field"}"#,
                scalar(7.0),
                None,
            ),
            fact_with(
                "F02",
                "soil_ph",
                None,
                r#"{"system":"container"}"#,
                scalar(6.5),
                None,
            ),
        ];
        assert!(check(&ctx(&facts)).is_empty());
    }

    #[test]
    fn phase_in_message_when_present() {
        let facts = vec![
            fact_with("F01", "kc", Some("initial"), "{}", scalar(0.6), None),
            fact_with("F02", "kc", Some("initial"), "{}", scalar(0.7), None),
        ];
        let out = check(&ctx(&facts));
        assert_eq!(out.len(), 1);
        assert!(
            out[0].message.contains("phase='initial'"),
            "msg: {}",
            out[0].message
        );
        assert_eq!(out[0].location.phase.as_deref(), Some("initial"));
    }

    #[test]
    fn three_duplicates_yield_two_findings() {
        let facts = vec![
            fact_with("F01", "soil_ph", None, "{}", scalar(7.0), None),
            fact_with("F02", "soil_ph", None, "{}", scalar(6.5), None),
            fact_with("F03", "soil_ph", None, "{}", scalar(7.5), None),
        ];
        let out = check(&ctx(&facts));
        // F02 vs F01 (F01 kept as first), F03 vs F01 (F01 still first)
        assert_eq!(out.len(), 2);
        assert!(out[0].message.contains("F01 vs F02"));
        assert!(out[1].message.contains("F01 vs F03"));
    }
}
