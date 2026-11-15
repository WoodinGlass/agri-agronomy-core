//! Rule: `check_safety_double_review`.

use std::collections::BTreeSet;

use super::{Finding, FindingLocation, RuleContext};

pub const CODE: &str = "PACK_SAFETY_DOUBLE_REVIEW_MISSING";

pub fn check(ctx: &RuleContext<'_>) -> Vec<Finding> {
    let mut out = Vec::new();
    for fact in ctx.facts {
        let param = match ctx.dictionary.parameters.get(&fact.parameter) {
            Some(p) => p,
            None => continue,
        };
        if param.safety_class == "none" {
            continue;
        }
        if fact.status != "approved" {
            continue;
        }
        let n = fact
            .reviewed_by
            .as_deref()
            .unwrap_or(&[])
            .iter()
            .collect::<BTreeSet<_>>()
            .len();
        if n < 2 {
            out.push(Finding::error(
                CODE,
                format!(
                    "fact {} is safety-critical (safety_class={}) and approved but has {} reviewer(s); \
                     approved safety-critical facts require >=2 distinct reviewers",
                    fact.fact_id, param.safety_class, n
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
    out
}

#[cfg(test)]
#[allow(clippy::unwrap_used, clippy::expect_used, clippy::panic)]
mod tests {
    use super::*;
    use crate::pack::dict_info::{AppliesToInfo, DictionaryInfo, ParameterInfo};
    use crate::pack::row_types::{FactRow, FactValue};
    use crate::pack::rules::EMPTY_FILES;
    use std::collections::BTreeMap;

    fn fact(status: &str, reviewers: &[&str]) -> FactRow {
        FactRow {
            fact_id: "F1".into(),
            taxon_id: "T000000001".into(),
            parameter: "n_max".into(),
            phase: None,
            value: FactValue::Scalar {
                unit: "kg".into(),
                value: 10.0,
            },
            scope_json: "{}".into(),
            provenance_kind: "curated".into(),
            src: Some(vec!["S001".into()]),
            dataset_id: None,
            locator: Some("T1".into()),
            evidence: "A".into(),
            status: status.into(),
            reviewed_by: if reviewers.is_empty() {
                None
            } else {
                Some(reviewers.iter().map(|s| s.to_string()).collect())
            },
            reviewed_at: Some("2026-01-01".into()),
            superseded_by: None,
        }
    }
    fn dict(sc: &str) -> DictionaryInfo {
        let mut d = DictionaryInfo::empty();
        let mut m = BTreeMap::new();
        m.insert(
            "n_max".into(),
            ParameterInfo {
                key: "n_max".into(),
                stage: "fertilizer".into(),
                shape: "scalar".into(),
                unit: Some("kg".into()),
                physical_range: Some((0.0, 1000.0)),
                enum_values: None,
                enum_source: None,
                phase_set: "none".into(),
                allowed_phases: None,
                applies_to: AppliesToInfo::default(),
                scope_keys: vec![],
                used_by: vec![],
                tier_required: true,
                safety_class: sc.into(),
                kind: "core".into(),
            },
        );
        d.parameters = m;
        d
    }
    fn ctx<'a>(facts: &'a [FactRow], d: &'a DictionaryInfo) -> RuleContext<'a> {
        RuleContext {
            taxa: &[],
            names: &[],
            facts,
            hazards: &[],
            sources: &[],
            datasets: &[],
            files: &EMPTY_FILES,
            dictionary: d,
        }
    }

    #[test]
    fn no_finding_when_not_safety() {
        let f = vec![fact("approved", &["r1"])];
        assert!(check(&ctx(&f, &dict("none"))).is_empty());
    }
    #[test]
    fn finding_when_one_reviewer() {
        let f = vec![fact("approved", &["r1"])];
        assert_eq!(check(&ctx(&f, &dict("dose_cap"))).len(), 1);
    }
    #[test]
    fn no_finding_when_two_reviewers() {
        let f = vec![fact("approved", &["r1", "r2"])];
        assert!(check(&ctx(&f, &dict("dose_cap"))).is_empty());
    }
    #[test]
    fn no_finding_when_not_approved() {
        let f = vec![fact("reviewed", &["r1"])];
        assert!(check(&ctx(&f, &dict("dose_cap"))).is_empty());
    }
}
