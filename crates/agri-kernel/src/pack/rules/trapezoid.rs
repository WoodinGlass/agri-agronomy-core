//! Rule: `check_trapezoid_not_degenerate`.
//!
//! Mirrors `check_trapezoid_not_degenerate` in `validate.py`. Flags
//! trapezoids where `pts[0] == pts[-1]` (a collapsed trapezoid — effectively
//! a scalar).

use crate::pack::row_types::{FactRow, FactValue};

use super::{py_float_str, py_tuple4_f64, Finding, FindingLocation, RuleContext};

pub const CODE: &str = "PACK_TRAPEZOID_DEGENERATE";

/// Return `PACK_TRAPEZOID_DEGENERATE` for every degenerate trapezoid fact.
pub fn check(ctx: &RuleContext<'_>) -> Vec<Finding> {
    let mut out = Vec::new();
    for fact in ctx.facts {
        let pts = match &fact.value {
            FactValue::Trapezoid { pts, .. } => pts,
            _ => continue,
        };
        if pts[0] != pts[3] {
            continue;
        }
        out.push(Finding::error(
            CODE,
            format!(
                "trapezoid has pts[0] == pts[-1] == {}; \
                 a non-degenerate trapezoid needs abs_min < abs_max (pts={})",
                py_float_str(pts[0]),
                py_tuple4_f64(pts),
            ),
            location_for(fact),
        ));
    }
    out
}

fn location_for(fact: &FactRow) -> FindingLocation {
    FindingLocation::with_taxon_fact_param_phase(
        fact.taxon_id.clone(),
        fact.fact_id.clone(),
        fact.parameter.clone(),
        fact.phase.clone(),
    )
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
    use crate::pack::row_types::{FactRow, FactValue};

    fn fact(id: &str, param: &str, phase: Option<&str>, value: FactValue) -> FactRow {
        FactRow {
            fact_id: id.to_string(),
            taxon_id: "T000000001".to_string(),
            parameter: param.to_string(),
            phase: phase.map(|s| s.to_string()),
            value,
            scope_json: "{}".to_string(),
            provenance_kind: "curated".to_string(),
            src: Some(vec!["S001".to_string()]),
            dataset_id: None,
            locator: Some("Table 1".to_string()),
            evidence: "A".to_string(),
            status: "approved".to_string(),
            reviewed_by: Some(vec!["r1".to_string()]),
            reviewed_at: Some("2026-01-01".to_string()),
            superseded_by: None,
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

    #[test]
    fn no_findings_for_valid_trapezoid() {
        let facts = vec![fact(
            "F00000000001",
            "soil_ph",
            None,
            FactValue::Trapezoid {
                unit: "pH".to_string(),
                pts: [4.5, 6.0, 7.0, 8.5],
            },
        )];
        assert!(check(&ctx(&facts)).is_empty());
    }

    #[test]
    fn finding_for_degenerate() {
        let facts = vec![fact(
            "F00000000001",
            "soil_ph",
            None,
            FactValue::Trapezoid {
                unit: "pH".to_string(),
                pts: [7.0, 7.0, 7.0, 7.0],
            },
        )];
        let out = check(&ctx(&facts));
        assert_eq!(out.len(), 1);
        let f = &out[0];
        assert_eq!(f.code, "PACK_TRAPEZOID_DEGENERATE");
        assert_eq!(f.severity.as_str(), "error");
        assert_eq!(f.location.fact_id.as_deref(), Some("F00000000001"));
        assert_eq!(f.location.taxon_id.as_deref(), Some("T000000001"));
        assert_eq!(f.location.parameter.as_deref(), Some("soil_ph"));
        assert!(f.location.phase.is_none());
        // Message content check (byte-identical tested in cell 6)
        assert!(f.message.contains("pts[0] == pts[-1] == 7.0"));
        assert!(f.message.contains("(pts=(7.0, 7.0, 7.0, 7.0))"));
    }

    #[test]
    fn finding_carries_phase() {
        let facts = vec![fact(
            "F00000000001",
            "air_temp_day",
            Some("flowering"),
            FactValue::Trapezoid {
                unit: "degree_Celsius".to_string(),
                pts: [20.0, 20.0, 20.0, 20.0],
            },
        )];
        let out = check(&ctx(&facts));
        assert_eq!(out.len(), 1);
        assert_eq!(out[0].location.phase.as_deref(), Some("flowering"));
    }

    #[test]
    fn multiple_degenerate_finds_all() {
        let facts = vec![
            fact(
                "F01",
                "soil_ph",
                None,
                FactValue::Trapezoid {
                    unit: "pH".into(),
                    pts: [7.0, 7.0, 7.0, 7.0],
                },
            ),
            fact(
                "F02",
                "soil_ph",
                None,
                FactValue::Trapezoid {
                    unit: "pH".into(),
                    pts: [4.5, 6.0, 7.0, 8.5],
                },
            ),
            fact(
                "F03",
                "soil_ec",
                None,
                FactValue::Trapezoid {
                    unit: "dS/m".into(),
                    pts: [2.0, 2.0, 2.0, 2.0],
                },
            ),
        ];
        let out = check(&ctx(&facts));
        assert_eq!(out.len(), 2);
    }

    #[test]
    fn ignores_non_trapezoid_values() {
        let facts = vec![
            fact(
                "F01",
                "gdd_base",
                None,
                FactValue::Scalar {
                    unit: "degree_Celsius".into(),
                    value: 8.0,
                },
            ),
            fact(
                "F02",
                "soil_ph",
                None,
                FactValue::Range {
                    unit: "pH".into(),
                    min: 6.0,
                    max: 7.0,
                },
            ),
        ];
        assert!(check(&ctx(&facts)).is_empty());
    }
}
