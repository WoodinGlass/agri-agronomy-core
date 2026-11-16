//! RustKnowledgeSet: eager, in-memory view built from a loaded pack.
//!
//! Mirrors the `KnowledgeSet` Protocol from `pack/knowledge_set.py`.
//! Construction is fallible on row-level integrity (duplicate PKs).
//!
//! Per ADR-019 §11.5, `normalize` + `name_index` ship as one backend unit:
//! the index is built here at construction time from the same rows the
//! set holds. Never stored, never derived from Python.

use std::collections::BTreeMap;

use crate::pack::name_index::{build_name_index, lookup, NameIndexEntry};
use crate::pack::row_types::{DatasetRow, FactRow, HazardRow, NameRow, SourceRow, TaxonRow};

/// Eager, in-memory view of a loaded pack.
///
/// All indices built at construction. Reads are reference-returning; no
/// interior mutability, no connections, no locks.
pub struct RustKnowledgeSet {
    pub manifest_fields: super::build::ManifestFields,
    pub pack_hash: String,
    pub artifact_sha256: String,
    pub dictionary_version: String,
    pub verified: bool,

    taxa_by_id: BTreeMap<String, TaxonRow>,
    taxa_sorted: Vec<TaxonRow>,
    facts_by_taxon: BTreeMap<String, Vec<FactRow>>,
    facts_by_taxon_param: BTreeMap<(String, String), Vec<FactRow>>,
    facts_all: Vec<FactRow>,
    names_by_taxon: BTreeMap<String, Vec<NameRow>>,
    names_all: Vec<NameRow>,
    name_index: BTreeMap<String, Vec<NameIndexEntry>>,
    hazards_by_taxon: BTreeMap<String, Vec<HazardRow>>,
    hazards_all: Vec<HazardRow>,
    sources_by_id: BTreeMap<String, SourceRow>,
    datasets_by_id: BTreeMap<String, DatasetRow>,
    ids_lock: Option<std::collections::BTreeSet<String>>,
}

#[derive(Debug)]
pub enum KnowledgeSetError {
    DuplicateTaxonId(String),
    DuplicateFactId(String),
    DuplicateNameKey(String),
    DuplicateHazardKey(String),
    DuplicateSourceId(String),
    DuplicateDatasetId(String),
    InvalidPackHash(String),
    TaxonNotFound(String),
}

impl std::fmt::Display for KnowledgeSetError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            KnowledgeSetError::DuplicateTaxonId(s) => write!(f, "duplicate taxon_id: {s}"),
            KnowledgeSetError::DuplicateFactId(s) => write!(f, "duplicate fact_id: {s}"),
            KnowledgeSetError::DuplicateNameKey(s) => write!(f, "duplicate name primary key: {s}"),
            KnowledgeSetError::DuplicateHazardKey(s) => {
                write!(f, "duplicate hazard primary key: {s}")
            }
            KnowledgeSetError::DuplicateSourceId(s) => write!(f, "duplicate source id: {s}"),
            KnowledgeSetError::DuplicateDatasetId(s) => write!(f, "duplicate dataset_id: {s}"),
            KnowledgeSetError::InvalidPackHash(s) => write!(f, "pack_hash invalid: {s}"),
            KnowledgeSetError::TaxonNotFound(s) => write!(f, "taxon not found: {s}"),
        }
    }
}

impl std::error::Error for KnowledgeSetError {}

#[allow(clippy::too_many_arguments)]
impl RustKnowledgeSet {
    pub fn from_rows(
        manifest_fields: super::build::ManifestFields,
        pack_hash: String,
        artifact_sha256: String,
        dictionary_version: String,
        verified: bool,
        ids_lock: Option<std::collections::BTreeSet<String>>,
        taxa: Vec<TaxonRow>,
        names: Vec<NameRow>,
        facts: Vec<FactRow>,
        hazards: Vec<HazardRow>,
        sources: Vec<SourceRow>,
        datasets: Vec<DatasetRow>,
    ) -> Result<Self, KnowledgeSetError> {
        // pack_hash regex check: 'sha256:' + 64 hex
        if pack_hash.len() != 71
            || !pack_hash.starts_with("sha256:")
            || !pack_hash[7..].chars().all(|c| c.is_ascii_hexdigit())
        {
            return Err(KnowledgeSetError::InvalidPackHash(pack_hash));
        }

        // Taxa: dedupe by taxon_id, sort.
        let mut taxa_by_id: BTreeMap<String, TaxonRow> = BTreeMap::new();
        for t in taxa {
            if taxa_by_id.contains_key(&t.taxon_id) {
                return Err(KnowledgeSetError::DuplicateTaxonId(t.taxon_id));
            }
            taxa_by_id.insert(t.taxon_id.clone(), t);
        }
        let taxa_sorted: Vec<TaxonRow> = taxa_by_id.values().cloned().collect();

        // Facts: dedupe by fact_id, index by taxon and by (taxon, param).
        let mut seen_fact: std::collections::BTreeSet<String> = Default::default();
        let mut facts_by_taxon: BTreeMap<String, Vec<FactRow>> = BTreeMap::new();
        let mut facts_by_param: BTreeMap<(String, String), Vec<FactRow>> = BTreeMap::new();
        let mut facts_all: Vec<FactRow> = Vec::with_capacity(facts.len());
        for f in facts {
            if !seen_fact.insert(f.fact_id.clone()) {
                return Err(KnowledgeSetError::DuplicateFactId(f.fact_id));
            }
            facts_by_taxon
                .entry(f.taxon_id.clone())
                .or_default()
                .push(f.clone());
            facts_by_param
                .entry((f.taxon_id.clone(), f.parameter.clone()))
                .or_default()
                .push(f.clone());
            facts_all.push(f);
        }
        for v in facts_by_taxon.values_mut() {
            v.sort_by(|a, b| a.fact_id.cmp(&b.fact_id));
        }
        for v in facts_by_param.values_mut() {
            v.sort_by(|a, b| a.fact_id.cmp(&b.fact_id));
        }
        facts_all.sort_by(|a, b| a.fact_id.cmp(&b.fact_id));

        // Names: dedupe by (taxon_id, name, language, script, kind); sort per taxon.
        let mut seen_name: std::collections::BTreeSet<(String, String, String, String, String)> =
            Default::default();
        let mut names_by_taxon: BTreeMap<String, Vec<NameRow>> = BTreeMap::new();
        let mut names_all: Vec<NameRow> = Vec::with_capacity(names.len());
        for n in names {
            let key = (
                n.taxon_id.clone(),
                n.name.clone(),
                n.language.clone(),
                n.script.clone(),
                n.kind.clone(),
            );
            if !seen_name.insert(key.clone()) {
                return Err(KnowledgeSetError::DuplicateNameKey(format!("{key:?}")));
            }
            names_by_taxon
                .entry(n.taxon_id.clone())
                .or_default()
                .push(n.clone());
            names_all.push(n);
        }
        for v in names_by_taxon.values_mut() {
            v.sort_by(|a, b| {
                (&a.name, &a.language, &a.script, &a.kind).cmp(&(
                    &b.name,
                    &b.language,
                    &b.script,
                    &b.kind,
                ))
            });
        }
        names_all.sort_by(|a, b| {
            (&a.taxon_id, &a.name, &a.language, &a.script, &a.kind).cmp(&(
                &b.taxon_id,
                &b.name,
                &b.language,
                &b.script,
                &b.kind,
            ))
        });

        // Hazards: dedupe by (taxon_id, hazard_code); sort.
        let mut seen_hazard: std::collections::BTreeSet<(String, String)> = Default::default();
        let mut hazards_by_taxon: BTreeMap<String, Vec<HazardRow>> = BTreeMap::new();
        let mut hazards_all: Vec<HazardRow> = Vec::with_capacity(hazards.len());
        for h in hazards {
            let key = (h.taxon_id.clone(), h.hazard_code.clone());
            if !seen_hazard.insert(key.clone()) {
                return Err(KnowledgeSetError::DuplicateHazardKey(format!("{key:?}")));
            }
            hazards_by_taxon
                .entry(h.taxon_id.clone())
                .or_default()
                .push(h.clone());
            hazards_all.push(h);
        }
        for v in hazards_by_taxon.values_mut() {
            v.sort_by(|a, b| a.hazard_code.cmp(&b.hazard_code));
        }
        hazards_all
            .sort_by(|a, b| (&a.taxon_id, &a.hazard_code).cmp(&(&b.taxon_id, &b.hazard_code)));

        // Sources: dedupe by id.
        let mut sources_by_id: BTreeMap<String, SourceRow> = BTreeMap::new();
        for s in sources {
            if sources_by_id.contains_key(&s.id) {
                return Err(KnowledgeSetError::DuplicateSourceId(s.id));
            }
            sources_by_id.insert(s.id.clone(), s);
        }

        // Datasets: dedupe by dataset_id.
        let mut datasets_by_id: BTreeMap<String, DatasetRow> = BTreeMap::new();
        for d in datasets {
            if datasets_by_id.contains_key(&d.dataset_id) {
                return Err(KnowledgeSetError::DuplicateDatasetId(d.dataset_id));
            }
            datasets_by_id.insert(d.dataset_id.clone(), d);
        }

        // Name index: built from sorted taxa + sorted names (per ADR §11.5).
        let name_index = build_name_index(&taxa_sorted, &names_all);

        Ok(Self {
            manifest_fields,
            pack_hash,
            artifact_sha256,
            dictionary_version,
            verified,
            taxa_by_id,
            taxa_sorted,
            facts_by_taxon,
            facts_by_taxon_param: facts_by_param,
            facts_all,
            names_by_taxon,
            names_all,
            name_index,
            hazards_by_taxon,
            hazards_all,
            sources_by_id,
            datasets_by_id,
            ids_lock,
        })
    }

    // ---- per-item lookups ----

    pub fn taxon(&self, taxon_id: &str) -> Option<&TaxonRow> {
        self.taxa_by_id.get(taxon_id)
    }

    pub fn source(&self, source_id: &str) -> Option<&SourceRow> {
        self.sources_by_id.get(source_id)
    }

    pub fn dataset(&self, dataset_id: &str) -> Option<&DatasetRow> {
        self.datasets_by_id.get(dataset_id)
    }

    // ---- iterators (sorted) ----

    pub fn taxa(&self) -> &[TaxonRow] {
        &self.taxa_sorted
    }

    pub fn facts(&self) -> &[FactRow] {
        &self.facts_all
    }

    pub fn names(&self) -> &[NameRow] {
        &self.names_all
    }

    pub fn hazards(&self) -> &[HazardRow] {
        &self.hazards_all
    }

    pub fn ids_lock(&self) -> Option<&std::collections::BTreeSet<String>> {
        self.ids_lock.as_ref()
    }

    // ---- per-taxon collections ----

    /// Returns `Err(())` if taxon unknown; `Ok(empty)` if known but no facts.
    pub fn facts_for(
        &self,
        taxon_id: &str,
        parameter: Option<&str>,
    ) -> Result<&[FactRow], KnowledgeSetError> {
        if !self.taxa_by_id.contains_key(taxon_id) {
            return Err(KnowledgeSetError::TaxonNotFound(taxon_id.to_string()));
        }
        match parameter {
            None => Ok(self
                .facts_by_taxon
                .get(taxon_id)
                .map(|v| v.as_slice())
                .unwrap_or(&[])),
            Some(p) => Ok(self
                .facts_by_taxon_param
                .get(&(taxon_id.to_string(), p.to_string()))
                .map(|v| v.as_slice())
                .unwrap_or(&[])),
        }
    }

    pub fn names_for(&self, taxon_id: &str) -> Result<&[NameRow], KnowledgeSetError> {
        if !self.taxa_by_id.contains_key(taxon_id) {
            return Err(KnowledgeSetError::TaxonNotFound(taxon_id.to_string()));
        }
        Ok(self
            .names_by_taxon
            .get(taxon_id)
            .map(|v| v.as_slice())
            .unwrap_or(&[]))
    }

    pub fn hazards_for(&self, taxon_id: &str) -> Result<&[HazardRow], KnowledgeSetError> {
        if !self.taxa_by_id.contains_key(taxon_id) {
            return Err(KnowledgeSetError::TaxonNotFound(taxon_id.to_string()));
        }
        Ok(self
            .hazards_by_taxon
            .get(taxon_id)
            .map(|v| v.as_slice())
            .unwrap_or(&[]))
    }

    // ---- name index ----

    pub fn names_index(&self, query: &str) -> &[NameIndexEntry] {
        lookup(&self.name_index, query)
    }
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
    use crate::pack::build::ManifestFields;
    use crate::pack::row_types::{FactValue, TaxonRow};

    fn manifest() -> ManifestFields {
        ManifestFields {
            name: "test".into(),
            version: "0.1.0".into(),
            schema_version: 1,
            engine_min: "0.0.0".into(),
            dictionary_min: "1.0.0".into(),
            content_hash: Some(format!("sha256:{}", "a".repeat(64))),
            synthetic: false,
            artifact_sha256: Some(format!("sha256:{}", "b".repeat(64))),
            sqlite_schema_version: Some(1),
            built_by: Some("agri-core 0.0.0".into()),
            hash_alg: Some("rfc8785".into()),
        }
    }

    fn taxon(id: &str, sci: &str) -> TaxonRow {
        TaxonRow {
            taxon_id: id.into(),
            rank: "species".into(),
            scientific_name: sci.into(),
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

    fn fact(id: &str, taxon_id: &str, param: &str) -> FactRow {
        FactRow {
            fact_id: id.into(),
            taxon_id: taxon_id.into(),
            parameter: param.into(),
            phase: None,
            value: FactValue::Scalar {
                unit: "pH".into(),
                value: 7.0,
            },
            scope_json: "{}".into(),
            provenance_kind: "curated".into(),
            src: Some(vec!["S001".into()]),
            dataset_id: None,
            locator: Some("T1".into()),
            evidence: "A".into(),
            status: "approved".into(),
            reviewed_by: Some(vec!["r1".into()]),
            reviewed_at: Some("2026-01-01".into()),
            superseded_by: None,
        }
    }

    #[test]
    fn empty_ks() {
        let ks = RustKnowledgeSet::from_rows(
            manifest(),
            format!("sha256:{}", "a".repeat(64)),
            format!("sha256:{}", "b".repeat(64)),
            "1.0.0".into(),
            true,
            None,
            vec![],
            vec![],
            vec![],
            vec![],
            vec![],
            vec![],
        )
        .unwrap();
        assert!(ks.taxa().is_empty());
        assert!(ks.facts().is_empty());
        assert_eq!(ks.pack_hash, format!("sha256:{}", "a".repeat(64)));
    }

    #[test]
    fn taxa_sorted_by_id() {
        let ks = RustKnowledgeSet::from_rows(
            manifest(),
            format!("sha256:{}", "a".repeat(64)),
            format!("sha256:{}", "b".repeat(64)),
            "1.0.0".into(),
            true,
            None,
            vec![taxon("T000000002", "B"), taxon("T000000001", "A")],
            vec![],
            vec![],
            vec![],
            vec![],
            vec![],
        )
        .unwrap();
        let ids: Vec<&str> = ks.taxa().iter().map(|t| t.taxon_id.as_str()).collect();
        assert_eq!(ids, vec!["T000000001", "T000000002"]);
    }

    #[test]
    fn facts_for_unknown_errs() {
        let ks = RustKnowledgeSet::from_rows(
            manifest(),
            format!("sha256:{}", "a".repeat(64)),
            format!("sha256:{}", "b".repeat(64)),
            "1.0.0".into(),
            true,
            None,
            vec![],
            vec![],
            vec![],
            vec![],
            vec![],
            vec![],
        )
        .unwrap();
        assert!(ks.facts_for("T999999999", None).is_err());
    }

    #[test]
    fn facts_for_known_no_facts_empty() {
        let ks = RustKnowledgeSet::from_rows(
            manifest(),
            format!("sha256:{}", "a".repeat(64)),
            format!("sha256:{}", "b".repeat(64)),
            "1.0.0".into(),
            true,
            None,
            vec![taxon("T000000001", "A")],
            vec![],
            vec![],
            vec![],
            vec![],
            vec![],
        )
        .unwrap();
        assert!(ks.facts_for("T000000001", None).unwrap().is_empty());
    }

    #[test]
    fn facts_indexed_by_taxon_and_param() {
        let ks = RustKnowledgeSet::from_rows(
            manifest(),
            format!("sha256:{}", "a".repeat(64)),
            format!("sha256:{}", "b".repeat(64)),
            "1.0.0".into(),
            true,
            None,
            vec![taxon("T000000001", "A")],
            vec![],
            vec![
                fact("F00000000001", "T000000001", "soil_ph"),
                fact("F00000000002", "T000000001", "gdd_base"),
            ],
            vec![],
            vec![],
            vec![],
        )
        .unwrap();
        assert_eq!(ks.facts_for("T000000001", None).unwrap().len(), 2);
        assert_eq!(
            ks.facts_for("T000000001", Some("soil_ph")).unwrap().len(),
            1
        );
    }

    #[test]
    fn names_index_built() {
        let ks = RustKnowledgeSet::from_rows(
            manifest(),
            format!("sha256:{}", "a".repeat(64)),
            format!("sha256:{}", "b".repeat(64)),
            "1.0.0".into(),
            true,
            None,
            vec![taxon("T000000001", "Solanum lycopersicum")],
            vec![],
            vec![],
            vec![],
            vec![],
            vec![],
        )
        .unwrap();
        let hits = ks.names_index("SOLANUM Lycopersicum");
        assert_eq!(hits.len(), 1);
        assert_eq!(hits[0].taxon_id, "T000000001");
    }

    #[test]
    fn duplicate_taxon_rejected() {
        let r = RustKnowledgeSet::from_rows(
            manifest(),
            format!("sha256:{}", "a".repeat(64)),
            format!("sha256:{}", "b".repeat(64)),
            "1.0.0".into(),
            true,
            None,
            vec![taxon("T000000001", "A"), taxon("T000000001", "B")],
            vec![],
            vec![],
            vec![],
            vec![],
            vec![],
        );
        assert!(r.is_err());
    }

    #[test]
    fn invalid_pack_hash_rejected() {
        let r = RustKnowledgeSet::from_rows(
            manifest(),
            "not-a-valid-hash".into(),
            format!("sha256:{}", "b".repeat(64)),
            "1.0.0".into(),
            true,
            None,
            vec![],
            vec![],
            vec![],
            vec![],
            vec![],
            vec![],
        );
        assert!(r.is_err());
    }
}
