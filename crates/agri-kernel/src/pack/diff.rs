//! Pack diff: pure Rust core. No I/O, no PyO3.
//!
//! Mirrors Python pack/diff.py for row-changed detection, classification,
//! and violation ordering. Messages are rendered on the Python side
//! (_render_violation); this module returns structured data only.

use std::collections::{BTreeMap, BTreeSet};

use crate::pack::row_types::{FactRow, FactValue, TaxonRow};

// ---- Config (injected by adapter; never hardcoded here) ----

#[derive(Debug, Clone)]
pub struct DiffConfig {
    pub acceptable_fields: BTreeSet<String>,
    pub violation_fields: BTreeSet<String>,
    pub protected_statuses: BTreeSet<String>,
}

// ---- Result types ----

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Classification {
    Acceptable,
    Violation,
}

impl Classification {
    pub fn as_str(self) -> &'static str {
        match self {
            Classification::Acceptable => "acceptable",
            Classification::Violation => "violation",
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct FactChangeRaw {
    pub fact_id: String,
    pub fields_changed: Vec<String>,
    pub classification: Classification,
    pub old_status: String,
    pub new_status: String,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ViolationKind {
    FactIdReused,
    TaxonRemoved,
    FactRemoved,
    IdRemovedFromLedger,
}

impl ViolationKind {
    pub fn as_str(self) -> &'static str {
        match self {
            ViolationKind::FactIdReused => "fact_id_reused",
            ViolationKind::TaxonRemoved => "taxon_removed",
            ViolationKind::FactRemoved => "fact_removed",
            ViolationKind::IdRemovedFromLedger => "id_removed_from_ledger",
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum ViolationMeta {
    FactIdReused { fields_changed: Vec<String> },
    Empty,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ViolationRaw {
    pub kind: ViolationKind,
    pub entity_id: String,
    pub meta: ViolationMeta,
}

#[derive(Debug, Clone, PartialEq)]
pub struct DiffOutcome {
    pub identical: bool,
    pub taxa_added: Vec<String>,
    pub taxa_removed: Vec<String>,
    pub taxa_changed: Vec<String>,
    pub facts_added: Vec<String>,
    pub facts_removed: Vec<String>,
    pub facts_changed: Vec<FactChangeRaw>,
    pub violations: Vec<ViolationRaw>,
}

// ---- Core ----

pub fn diff_rows(
    old_taxa: &[TaxonRow],
    new_taxa: &[TaxonRow],
    old_facts: &[FactRow],
    new_facts: &[FactRow],
    old_ids_lock: Option<&BTreeSet<String>>,
    new_ids_lock: Option<&BTreeSet<String>>,
    cfg: &DiffConfig,
) -> DiffOutcome {
    let old_taxa_by = taxa_map(old_taxa);
    let new_taxa_by = taxa_map(new_taxa);
    let old_facts_by = facts_map(old_facts);
    let new_facts_by = facts_map(new_facts);

    let mut taxa_added: Vec<String> = Vec::new();
    for k in new_taxa_by.keys() {
        if !old_taxa_by.contains_key(k) {
            taxa_added.push(k.clone());
        }
    }
    let mut taxa_removed: Vec<String> = Vec::new();
    for k in old_taxa_by.keys() {
        if !new_taxa_by.contains_key(k) {
            taxa_removed.push(k.clone());
        }
    }
    let mut taxa_changed: Vec<String> = Vec::new();
    for (k, o) in old_taxa_by.iter() {
        if let Some(n) = new_taxa_by.get(k) {
            if o != n {
                taxa_changed.push(k.clone());
            }
        }
    }
    let mut facts_added: Vec<String> = Vec::new();
    for k in new_facts_by.keys() {
        if !old_facts_by.contains_key(k) {
            facts_added.push(k.clone());
        }
    }
    let mut facts_removed: Vec<String> = Vec::new();
    for k in old_facts_by.keys() {
        if !new_facts_by.contains_key(k) {
            facts_removed.push(k.clone());
        }
    }

    let mut facts_changed: Vec<FactChangeRaw> = Vec::new();
    let mut violations: Vec<ViolationRaw> = Vec::new();

    for (fid, of) in old_facts_by.iter() {
        let nf = match new_facts_by.get(fid) {
            Some(row) => row,
            None => continue,
        };
        if of == nf {
            continue;
        }
        let changed = diff_fields(of, nf, cfg);
        if changed.is_empty() {
            continue;
        }
        let classification = classify(&of.status, &changed, cfg);
        facts_changed.push(FactChangeRaw {
            fact_id: fid.clone(),
            fields_changed: changed.clone(),
            classification,
            old_status: of.status.clone(),
            new_status: nf.status.clone(),
        });
        if classification == Classification::Violation {
            violations.push(ViolationRaw {
                kind: ViolationKind::FactIdReused,
                entity_id: fid.clone(),
                meta: ViolationMeta::FactIdReused {
                    fields_changed: changed,
                },
            });
        }
    }

    for tid in &taxa_removed {
        violations.push(ViolationRaw {
            kind: ViolationKind::TaxonRemoved,
            entity_id: tid.clone(),
            meta: ViolationMeta::Empty,
        });
    }
    for fid in &facts_removed {
        violations.push(ViolationRaw {
            kind: ViolationKind::FactRemoved,
            entity_id: fid.clone(),
            meta: ViolationMeta::Empty,
        });
    }

    if let (Some(ol), Some(nl)) = (old_ids_lock, new_ids_lock) {
        for tid in ol.iter() {
            if !nl.contains(tid) {
                violations.push(ViolationRaw {
                    kind: ViolationKind::IdRemovedFromLedger,
                    entity_id: tid.clone(),
                    meta: ViolationMeta::Empty,
                });
            }
        }
    }

    taxa_added.sort();
    taxa_removed.sort();
    taxa_changed.sort();
    facts_added.sort();
    facts_removed.sort();
    facts_changed.sort_by(|a, b| a.fact_id.cmp(&b.fact_id));
    violations.sort_by(|a, b| {
        a.kind
            .as_str()
            .cmp(b.kind.as_str())
            .then_with(|| a.entity_id.cmp(&b.entity_id))
    });

    let identical = taxa_added.is_empty()
        && taxa_removed.is_empty()
        && taxa_changed.is_empty()
        && facts_added.is_empty()
        && facts_removed.is_empty()
        && facts_changed.is_empty();

    DiffOutcome {
        identical,
        taxa_added,
        taxa_removed,
        taxa_changed,
        facts_added,
        facts_removed,
        facts_changed,
        violations,
    }
}

fn taxa_map(rows: &[TaxonRow]) -> BTreeMap<String, TaxonRow> {
    let mut m: BTreeMap<String, TaxonRow> = BTreeMap::new();
    for r in rows {
        m.insert(r.taxon_id.clone(), r.clone());
    }
    m
}

fn facts_map(rows: &[FactRow]) -> BTreeMap<String, FactRow> {
    let mut m: BTreeMap<String, FactRow> = BTreeMap::new();
    for r in rows {
        m.insert(r.fact_id.clone(), r.clone());
    }
    m
}

fn diff_fields(old: &FactRow, new: &FactRow, cfg: &DiffConfig) -> Vec<String> {
    let mut fields: BTreeSet<&str> = BTreeSet::new();
    for f in cfg.acceptable_fields.iter() {
        fields.insert(f.as_str());
    }
    for f in cfg.violation_fields.iter() {
        fields.insert(f.as_str());
    }
    let mut changed: Vec<String> = Vec::new();
    for f in fields.into_iter() {
        if !fact_field_eq(old, new, f) {
            changed.push(f.to_string());
        }
    }
    changed
}

fn fact_field_eq(old: &FactRow, new: &FactRow, field: &str) -> bool {
    match field {
        "status" => old.status == new.status,
        "evidence" => old.evidence == new.evidence,
        "reviewed_by" => old.reviewed_by == new.reviewed_by,
        "reviewed_at" => old.reviewed_at == new.reviewed_at,
        "locator" => old.locator == new.locator,
        "superseded_by" => old.superseded_by == new.superseded_by,
        "src" => old.src == new.src,
        "dataset_id" => old.dataset_id == new.dataset_id,
        "provenance_kind" => old.provenance_kind == new.provenance_kind,
        "value" => fact_value_eq(&old.value, &new.value),
        "scope" => old.scope_json == new.scope_json,
        "parameter" => old.parameter == new.parameter,
        "taxon_id" => old.taxon_id == new.taxon_id,
        "phase" => old.phase == new.phase,
        _ => true,
    }
}

fn fact_value_eq(a: &FactValue, b: &FactValue) -> bool {
    a == b
}

fn classify(old_status: &str, changed: &[String], cfg: &DiffConfig) -> Classification {
    if !cfg.protected_statuses.contains(old_status) {
        return Classification::Acceptable;
    }
    for f in changed {
        if cfg.violation_fields.contains(f.as_str()) {
            return Classification::Violation;
        }
    }
    Classification::Acceptable
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

    fn cfg() -> DiffConfig {
        let acceptable: BTreeSet<String> = [
            "status",
            "evidence",
            "reviewed_by",
            "reviewed_at",
            "locator",
            "superseded_by",
            "src",
            "dataset_id",
            "provenance_kind",
        ]
        .iter()
        .map(|s| s.to_string())
        .collect();
        let violation: BTreeSet<String> = ["value", "scope", "parameter", "taxon_id", "phase"]
            .iter()
            .map(|s| s.to_string())
            .collect();
        let protected: BTreeSet<String> = ["reviewed", "approved"]
            .iter()
            .map(|s| s.to_string())
            .collect();
        DiffConfig {
            acceptable_fields: acceptable,
            violation_fields: violation,
            protected_statuses: protected,
        }
    }

    fn mk_taxon(id: &str, sci: &str) -> TaxonRow {
        TaxonRow {
            taxon_id: id.to_string(),
            rank: "species".to_string(),
            scientific_name: sci.to_string(),
            accepted_name: None,
            organism_group: "vascular_plant".to_string(),
            archetype: "annual".to_string(),
            uses: vec!["vegetable".to_string()],
            traits: Vec::new(),
            parent_id: None,
            external_ids: None,
            src: Some(vec!["S001".to_string()]),
            dataset_id: None,
        }
    }

    fn mk_fact(id: &str, taxon: &str, status: &str, value: f64) -> FactRow {
        FactRow {
            fact_id: id.to_string(),
            taxon_id: taxon.to_string(),
            parameter: "gdd_base".to_string(),
            phase: None,
            value: FactValue::Scalar {
                unit: "degree_Celsius".to_string(),
                value,
            },
            scope_json: "{}".to_string(),
            provenance_kind: "curated".to_string(),
            src: Some(vec!["S001".to_string()]),
            dataset_id: None,
            locator: None,
            evidence: "A".to_string(),
            status: status.to_string(),
            reviewed_by: None,
            reviewed_at: None,
            superseded_by: None,
        }
    }

    #[test]
    fn identical_packs_no_diff() {
        let taxa = vec![mk_taxon("T1", "Testus")];
        let facts = vec![mk_fact("F1", "T1", "approved", 1.0)];
        let out = diff_rows(&taxa, &taxa, &facts, &facts, None, None, &cfg());
        assert!(out.identical);
        assert!(out.taxa_added.is_empty());
        assert!(out.facts_changed.is_empty());
        assert!(out.violations.is_empty());
    }

    #[test]
    fn fact_value_changed_reviewed_is_violation() {
        let taxa = vec![mk_taxon("T1", "Testus")];
        let old_facts = vec![mk_fact("F1", "T1", "reviewed", 1.0)];
        let new_facts = vec![mk_fact("F1", "T1", "reviewed", 2.0)];
        let out = diff_rows(&taxa, &taxa, &old_facts, &new_facts, None, None, &cfg());
        assert!(!out.identical);
        assert_eq!(out.facts_changed.len(), 1);
        assert_eq!(out.facts_changed[0].fact_id, "F1");
        assert_eq!(
            out.facts_changed[0].fields_changed,
            vec!["value".to_string()]
        );
        assert_eq!(
            out.facts_changed[0].classification,
            Classification::Violation
        );
        assert_eq!(out.violations.len(), 1);
        assert_eq!(out.violations[0].kind, ViolationKind::FactIdReused);
        assert_eq!(out.violations[0].entity_id, "F1");
    }

    #[test]
    fn fact_value_changed_draft_is_acceptable() {
        let taxa = vec![mk_taxon("T1", "Testus")];
        let old_facts = vec![mk_fact("F1", "T1", "draft", 1.0)];
        let new_facts = vec![mk_fact("F1", "T1", "draft", 2.0)];
        let out = diff_rows(&taxa, &taxa, &old_facts, &new_facts, None, None, &cfg());
        assert_eq!(out.facts_changed.len(), 1);
        assert_eq!(
            out.facts_changed[0].classification,
            Classification::Acceptable
        );
        assert!(out.violations.is_empty());
    }

    #[test]
    fn taxon_removed_is_violation() {
        let old_taxa = vec![mk_taxon("T1", "A"), mk_taxon("T2", "B")];
        let new_taxa = vec![mk_taxon("T1", "A")];
        let out = diff_rows(&old_taxa, &new_taxa, &[], &[], None, None, &cfg());
        assert!(!out.identical);
        assert_eq!(out.taxa_removed, vec!["T2".to_string()]);
        assert_eq!(out.violations.len(), 1);
        assert_eq!(out.violations[0].kind, ViolationKind::TaxonRemoved);
        assert_eq!(out.violations[0].entity_id, "T2");
    }

    #[test]
    fn ids_lock_removed_is_violation() {
        let mut ol: BTreeSet<String> = BTreeSet::new();
        ol.insert("T1".to_string());
        ol.insert("T2".to_string());
        let mut nl: BTreeSet<String> = BTreeSet::new();
        nl.insert("T1".to_string());
        let out = diff_rows(&[], &[], &[], &[], Some(&ol), Some(&nl), &cfg());
        assert_eq!(out.violations.len(), 1);
        assert_eq!(out.violations[0].kind, ViolationKind::IdRemovedFromLedger);
        assert_eq!(out.violations[0].entity_id, "T2");
    }
}
