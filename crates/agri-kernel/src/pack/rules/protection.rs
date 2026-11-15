//! Rules: `check_param_out_of_scope`, `check_hazard_out_of_scope` (ADR-007).

use super::{py_repr_str, Finding, FindingLocation, RuleContext};
use crate::pack::dict_info::ParameterInfo;

pub const CODE_PARAM: &str = "PACK_PROTECTION_OUT_OF_SCOPE";
pub const CODE_HAZARD: &str = "PACK_HAZARD_CODE_OUT_OF_SCOPE";

const PROTECTION_STAGE: &str = "protection";
const PROTECTION_TOKENS: &[&str] = &[
    "pest",
    "disease",
    "pathogen",
    "weed",
    "threat",
    "biocontrol",
];
const GLOBAL_TOKENS: &[&str] = &["adjuvant", "surfactant", "moa", "frac", "irac", "hrac"];
const GLOBAL_TOKEN_SUFFIXES: &[&str] = &["cide"];
const DOMAIN_TOKENS: &[&str] = &[
    "dose",
    "dosage",
    "dosing",
    "concentration",
    "spray",
    "drench",
    "formulation",
    "phi",
    "rei",
    "withholding",
    "treatment",
    "curative",
    "eradicant",
    "fumigant",
    "fumigation",
    "interval",
    "schedule",
];
const ALLOWED_UNITS: &[&str] = &[
    "centimeter",
    "day",
    "degree_Celsius",
    "degree_day",
    "kilopascal",
    "meter",
    "percent",
];
const GLOBAL_PHRASES: &[&[&str]] = &[
    &["tank", "mix"],
    &["active", "ingredient"],
    &["trade", "name"],
    &["mode", "of", "action"],
];
const PROTECTION_PHRASES: &[&[&str]] = &[&["plant", "protection"]];
const DOMAIN_PHRASES: &[&[&str]] = &[
    &["application", "rate"],
    &["product", "name"],
    &["pre", "harvest"],
    &["re", "entry"],
    &["action", "threshold"],
    &["economic", "threshold"],
];

fn tokenize(s: &str) -> Vec<String> {
    s.to_lowercase()
        .chars()
        .map(|c| {
            if c.is_ascii_lowercase() || c.is_ascii_digit() {
                c
            } else {
                '_'
            }
        })
        .collect::<String>()
        .split('_')
        .filter(|x| !x.is_empty())
        .map(String::from)
        .collect()
}

fn check_tokens(
    tokens: &[String],
    set: &[&str],
    phrases: &[&[&str]],
    suffixes: &[&str],
) -> Vec<String> {
    let mut r = Vec::new();
    for t in tokens {
        if set.contains(&t.as_str()) {
            r.push(format!("forbidden token {}", py_repr_str(t)));
        }
        for suf in suffixes {
            if t.ends_with(suf) {
                r.push(format!(
                    "forbidden token ending {}: {}",
                    py_repr_str(suf),
                    py_repr_str(t)
                ));
            }
        }
    }
    for phrase in phrases {
        let n = phrase.len();
        if tokens.len() >= n {
            for i in 0..=(tokens.len() - n) {
                if let Some(sl) = tokens.get(i..i + n) {
                    if sl.iter().map(|s| s.as_str()).eq(phrase.iter().copied()) {
                        r.push(format!("forbidden phrase {}", phrase.join(" ")));
                    }
                }
            }
        }
    }
    r
}

fn is_protection_domain(p: &ParameterInfo) -> bool {
    if p.stage == PROTECTION_STAGE {
        return true;
    }
    let tokens = tokenize(&p.key);
    if tokens
        .iter()
        .any(|t| PROTECTION_TOKENS.contains(&t.as_str()))
    {
        return true;
    }
    for phrase in PROTECTION_PHRASES {
        let n = phrase.len();
        if tokens.len() >= n {
            for i in 0..=(tokens.len() - n) {
                if let Some(sl) = tokens.get(i..i + n) {
                    if sl.iter().map(|s| s.as_str()).eq(phrase.iter().copied()) {
                        return true;
                    }
                }
            }
        }
    }
    false
}

pub fn check_param_out_of_scope(ctx: &RuleContext<'_>) -> Vec<Finding> {
    let mut out = Vec::new();
    for (key, p) in ctx.dictionary.parameters.iter() {
        let tokens = tokenize(key);
        let mut reasons = check_tokens(
            &tokens,
            GLOBAL_TOKENS,
            GLOBAL_PHRASES,
            GLOBAL_TOKEN_SUFFIXES,
        );
        for v in p.enum_values.as_deref().unwrap_or(&[]) {
            for r in check_tokens(
                &tokenize(v),
                GLOBAL_TOKENS,
                GLOBAL_PHRASES,
                GLOBAL_TOKEN_SUFFIXES,
            ) {
                reasons.push(format!("enum value {}: {}", py_repr_str(v), r));
            }
        }
        if is_protection_domain(p) {
            if let Some(u) = p.unit.as_deref() {
                if !ALLOWED_UNITS.contains(&u) {
                    reasons.push(format!(
                        "unit {} not in protection allowlist",
                        py_repr_str(u)
                    ));
                }
            }
            reasons.extend(check_tokens(&tokens, DOMAIN_TOKENS, DOMAIN_PHRASES, &[]));
            for v in p.enum_values.as_deref().unwrap_or(&[]) {
                for r in check_tokens(&tokenize(v), DOMAIN_TOKENS, DOMAIN_PHRASES, &[]) {
                    reasons.push(format!("enum value {}: {}", py_repr_str(v), r));
                }
            }
            if p.shape == "rule" {
                reasons.push("shape='rule' (free-form payload)".to_string());
            }
            if p.kind == "extension" {
                reasons.push("kind='extension' bypasses engine review".to_string());
            }
            if p.tier_required {
                reasons.push("tier_required=True".to_string());
            }
        }
        if !reasons.is_empty() {
            out.push(Finding::error(
                CODE_PARAM,
                format!(
                    "parameter {} is out of scope: {}",
                    py_repr_str(key),
                    reasons.join("; ")
                ),
                FindingLocation {
                    parameter: Some(key.clone()),
                    ..Default::default()
                },
            ));
        }
    }
    out
}

pub fn check_hazard_out_of_scope(ctx: &RuleContext<'_>) -> Vec<Finding> {
    let mut codes: std::collections::BTreeSet<&str> = Default::default();
    for h in ctx.hazards {
        codes.insert(h.hazard_code.as_str());
    }
    let mut out = Vec::new();
    for code in &codes {
        let tokens = tokenize(code);
        let mut reasons = check_tokens(
            &tokens,
            GLOBAL_TOKENS,
            GLOBAL_PHRASES,
            GLOBAL_TOKEN_SUFFIXES,
        );
        reasons.extend(check_tokens(&tokens, DOMAIN_TOKENS, DOMAIN_PHRASES, &[]));
        if !reasons.is_empty() {
            out.push(Finding::error(
                CODE_HAZARD,
                format!(
                    "hazard code {} is out of scope: {}",
                    py_repr_str(code),
                    reasons.join("; ")
                ),
                FindingLocation {
                    key: Some(code.to_string()),
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
    use crate::pack::dict_info::{AppliesToInfo, DictionaryInfo, ParameterInfo};
    use crate::pack::row_types::HazardRow;
    use crate::pack::rules::EMPTY_FILES;
    use std::collections::BTreeMap;

    fn param(key: &str) -> ParameterInfo {
        ParameterInfo {
            key: key.into(),
            stage: "cycle".into(),
            shape: "scalar".into(),
            unit: Some("day".into()),
            physical_range: Some((0.0, 100.0)),
            enum_values: None,
            enum_source: None,
            phase_set: "none".into(),
            allowed_phases: None,
            applies_to: AppliesToInfo::default(),
            scope_keys: vec![],
            used_by: vec![],
            tier_required: false,
            safety_class: "none".into(),
            kind: "core".into(),
        }
    }
    fn dict(params: Vec<ParameterInfo>) -> DictionaryInfo {
        let mut d = DictionaryInfo::empty();
        let mut m = BTreeMap::new();
        for p in params {
            m.insert(p.key.clone(), p);
        }
        d.parameters = m;
        d
    }
    fn ctx<'a>(hazards: &'a [HazardRow], d: &'a DictionaryInfo) -> RuleContext<'a> {
        RuleContext {
            taxa: &[],
            names: &[],
            facts: &[],
            hazards,
            sources: &[],
            datasets: &[],
            files: &EMPTY_FILES,
            dictionary: d,
        }
    }

    #[test]
    fn tokenize_basic() {
        assert_eq!(tokenize("soil-ph"), vec!["soil", "ph"]);
    }
    #[test]
    fn clean_param_no_finding() {
        let d = dict(vec![param("soil_ph")]);
        assert!(check_param_out_of_scope(&ctx(&[], &d)).is_empty());
    }
    #[test]
    fn global_token_finding() {
        let d = dict(vec![param("fungicide_interval")]);
        let out = check_param_out_of_scope(&ctx(&[], &d));
        assert_eq!(out.len(), 1);
        assert_eq!(out[0].code, CODE_PARAM);
    }
    #[test]
    fn clean_hazard_no_finding() {
        let h = vec![HazardRow {
            taxon_id: "T1".into(),
            hazard_code: "spore_allergy".into(),
            severity: "warning".into(),
            reason: "r".into(),
            as_of: "2026-01-01".into(),
            authority: "a".into(),
            src: Some(vec!["S001".into()]),
            dataset_id: None,
        }];
        assert!(check_hazard_out_of_scope(&ctx(&h, &DictionaryInfo::empty())).is_empty());
    }
    #[test]
    fn hazard_global_token_finding() {
        let h = vec![HazardRow {
            taxon_id: "T1".into(),
            hazard_code: "pesticide_residue".into(),
            severity: "warning".into(),
            reason: "r".into(),
            as_of: "2026-01-01".into(),
            authority: "a".into(),
            src: Some(vec!["S001".into()]),
            dataset_id: None,
        }];
        assert_eq!(
            check_hazard_out_of_scope(&ctx(&h, &DictionaryInfo::empty())).len(),
            1
        );
    }
}
