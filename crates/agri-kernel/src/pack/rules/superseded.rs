//! Rules: `check_superseded_self`, `check_superseded_cycle`.
//!
//! Mirrors `validate.py`. Both flag structural problems in the
//! `superseded_by` chain (a fact pointing at itself, or a cycle).
//! Self-loops are handled by `check_superseded_self`; cycles of length
//! >= 2 are handled by `check_superseded_cycle`.

use std::collections::{BTreeMap, BTreeSet, HashMap};

use crate::pack::row_types::FactRow;

use super::{Finding, FindingLocation, RuleContext};

pub const CODE_SELF: &str = "PACK_SUPERSEDED_SELF";
pub const CODE_CYCLE: &str = "PACK_SUPERSEDED_CYCLE";

// ---- check_superseded_self ----

/// Flag facts that reference themselves via `superseded_by`.
pub fn check_self(ctx: &RuleContext<'_>) -> Vec<Finding> {
    let mut out = Vec::new();
    for fact in ctx.facts {
        let is_self = fact
            .superseded_by
            .as_deref()
            .map(|s| s == fact.fact_id.as_str())
            .unwrap_or(false);
        if !is_self {
            continue;
        }
        out.push(Finding::error(
            CODE_SELF,
            format!(
                "fact {} supersedes itself; superseded_by must be a different fact_id",
                fact.fact_id
            ),
            FindingLocation {
                taxon_id: Some(fact.taxon_id.clone()),
                fact_id: Some(fact.fact_id.clone()),
                parameter: Some(fact.parameter.clone()),
                ..Default::default()
            },
        ));
    }
    out
}

// ---- check_superseded_cycle ----

/// Detect cycles in the `superseded_by` chain (excluding self-loops).
///
/// Walks each chain forward tracking a local path; when a node repeats
/// within the path, that sub-path is a cycle. One finding per cycle,
/// anchored at the smallest `fact_id` in the cycle for determinism.
/// Self-loops are excluded (handled by `check_self`).
pub fn check_cycle(ctx: &RuleContext<'_>) -> Vec<Finding> {
    // Index by fact_id; BTreeMap keeps sorted iteration matching Python
    // `for start in sorted(facts_by_id)`.
    let mut facts_by_id: BTreeMap<&str, &FactRow> = BTreeMap::new();
    for f in ctx.facts {
        facts_by_id.insert(f.fact_id.as_str(), f);
    }

    let mut visited: BTreeSet<&str> = BTreeSet::new();
    // Canonical cycle signature: sorted Vec<&str>. Dedup key.
    let mut reported: BTreeSet<Vec<&str>> = BTreeSet::new();
    let mut out = Vec::new();

    // Sorted iteration by fact_id (BTreeMap keys are sorted).
    let starts: Vec<&str> = facts_by_id.keys().copied().collect();
    for start in starts {
        if visited.contains(start) {
            continue;
        }
        let mut path: Vec<&str> = Vec::new();
        let mut local_seen: HashMap<&str, usize> = HashMap::new();

        let mut node: Option<&str> = Some(start);
        while let Some(n) = node {
            if visited.contains(n) || local_seen.contains_key(n) {
                break;
            }
            local_seen.insert(n, path.len());
            path.push(n);
            let nxt = facts_by_id.get(n).and_then(|f| f.superseded_by.as_deref());
            node = nxt.filter(|t| facts_by_id.contains_key(t));
        }

        // Cycle closes if `node` is in local_seen.
        if let Some(pos) = node.and_then(|n| local_seen.get(n).copied()) {
            let cycle_nodes: Vec<&str> = path.iter().skip(pos).copied().collect();
            if cycle_nodes.len() >= 2 {
                let mut cycle_sorted = cycle_nodes;
                cycle_sorted.sort_unstable();
                let cycle_sig = cycle_sorted.clone();
                if !reported.contains(&cycle_sig) {
                    reported.insert(cycle_sig);
                    let anchor = cycle_sorted.first().copied().unwrap_or("");
                    if let Some(anchor_fact) = facts_by_id.get(anchor) {
                        out.push(Finding::error(
                            CODE_CYCLE,
                            format!(
                                "cycle in superseded_by: {} -> ...",
                                cycle_sorted.join(" -> ")
                            ),
                            FindingLocation {
                                taxon_id: Some(anchor_fact.taxon_id.clone()),
                                fact_id: Some(anchor.to_string()),
                                parameter: Some(anchor_fact.parameter.clone()),
                                ..Default::default()
                            },
                        ));
                    }
                }
            }
        }

        for p in path {
            visited.insert(p);
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

    fn fact(id: &str, superseded_by: Option<&str>) -> FactRow {
        FactRow {
            fact_id: id.to_string(),
            taxon_id: "T000000001".to_string(),
            parameter: "soil_ph".to_string(),
            phase: None,
            value: FactValue::Scalar {
                unit: "pH".into(),
                value: 7.0,
            },
            scope_json: "{}".to_string(),
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

    // ---- check_self ----

    #[test]
    fn self_no_finding_when_null() {
        let facts = vec![fact("F01", None)];
        assert!(check_self(&ctx(&facts)).is_empty());
    }

    #[test]
    fn self_no_finding_when_other() {
        let facts = vec![fact("F01", Some("F02"))];
        assert!(check_self(&ctx(&facts)).is_empty());
    }

    #[test]
    fn self_finding_when_self_ref() {
        let facts = vec![fact("F01", Some("F01"))];
        let out = check_self(&ctx(&facts));
        assert_eq!(out.len(), 1);
        assert_eq!(out[0].code, "PACK_SUPERSEDED_SELF");
        assert_eq!(out[0].severity.as_str(), "error");
        assert_eq!(out[0].location.fact_id.as_deref(), Some("F01"));
        assert!(out[0].message.contains("supersedes itself"));
        assert!(out[0]
            .message
            .contains("superseded_by must be a different fact_id"));
    }

    // ---- check_cycle ----

    #[test]
    fn cycle_no_finding_on_chain() {
        // F01 -> F02 -> None (no cycle)
        let facts = vec![fact("F01", Some("F02")), fact("F02", None)];
        assert!(check_cycle(&ctx(&facts)).is_empty());
    }

    #[test]
    fn cycle_no_finding_on_self_loop() {
        // F01 -> F01 is self-loop, handled by check_self, not here.
        let facts = vec![fact("F01", Some("F01"))];
        assert!(check_cycle(&ctx(&facts)).is_empty());
    }

    #[test]
    fn cycle_finding_on_two_cycle() {
        // F01 <-> F02
        let facts = vec![fact("F01", Some("F02")), fact("F02", Some("F01"))];
        let out = check_cycle(&ctx(&facts));
        assert_eq!(out.len(), 1);
        assert_eq!(out[0].code, "PACK_SUPERSEDED_CYCLE");
        assert!(out[0].message.contains("F01 -> F02"));
        assert!(out[0].message.contains(" -> ..."));
        // anchor = smallest fact_id
        assert_eq!(out[0].location.fact_id.as_deref(), Some("F01"));
    }

    #[test]
    fn cycle_finding_on_three_cycle_anchor_smallest() {
        // F02 -> F03 -> F01 -> F02 (anchor should be F01)
        let facts = vec![
            fact("F01", Some("F02")),
            fact("F02", Some("F03")),
            fact("F03", Some("F01")),
        ];
        let out = check_cycle(&ctx(&facts));
        assert_eq!(out.len(), 1);
        assert!(out[0].message.contains("F01 -> F02 -> F03"));
        assert_eq!(out[0].location.fact_id.as_deref(), Some("F01"));
    }

    #[test]
    fn cycle_dedup_two_entries_same_cycle() {
        // Both F01 and F02 enter the same cycle; only one finding.
        let facts = vec![fact("F01", Some("F02")), fact("F02", Some("F01"))];
        let out = check_cycle(&ctx(&facts));
        assert_eq!(out.len(), 1);
    }

    #[test]
    fn cycle_two_disjoint_cycles() {
        // F01 <-> F02 and F03 <-> F04
        let facts = vec![
            fact("F01", Some("F02")),
            fact("F02", Some("F01")),
            fact("F03", Some("F04")),
            fact("F04", Some("F03")),
        ];
        let out = check_cycle(&ctx(&facts));
        assert_eq!(out.len(), 2);
    }
}
