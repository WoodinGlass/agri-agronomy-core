//! Rules: 6 license rules.

use super::{py_repr_str, Finding, FindingLocation, RuleContext};

const ALLOWED_SOURCES: &[&str] = &[
    "CC0-1.0",
    "CC-BY-3.0",
    "CC-BY-4.0",
    "MIT",
    "BSD-2-Clause",
    "BSD-3-Clause",
    "Apache-2.0",
    "LicenseRef-PublicDomain",
];
const ALLOWED_DATASETS: &[&str] = &[
    "CC0-1.0",
    "CC-BY-4.0",
    "MIT",
    "BSD-2-Clause",
    "BSD-3-Clause",
    "Apache-2.0",
];
const COMPOSITE_MARKERS: &[&str] = &[" AND ", " OR ", " WITH ", "+"];
const PD_SENTINEL: &str = "LicenseRef-PublicDomain";
const PD_BASIS_PREFIX: &str = "basis:";

pub fn is_nc_license(id: &str) -> bool {
    let l = id.to_lowercase();
    l.split('-').any(|t| t == "nc" || t == "noncommercial")
}
pub fn is_sa_license(id: &str) -> bool {
    let l = id.to_lowercase();
    l.split('-').any(|t| t == "sa" || t == "sharealike")
}
pub fn is_nd_license(id: &str) -> bool {
    let l = id.to_lowercase();
    l.split('-')
        .any(|t| t == "nd" || t == "noderiv" || t == "noderivatives")
}
pub fn is_allowed_license(id: &str, for_dataset: bool) -> bool {
    if id.is_empty() || id == "unclear" || id == "NOASSERTION" {
        return false;
    }
    if COMPOSITE_MARKERS.iter().any(|m| id.contains(m)) {
        return false;
    }
    if id.starts_with("LicenseRef-") && id != PD_SENTINEL {
        return false;
    }
    if is_nc_license(id) || is_sa_license(id) || is_nd_license(id) {
        return false;
    }
    let set = if for_dataset {
        ALLOWED_DATASETS
    } else {
        ALLOWED_SOURCES
    };
    set.contains(&id)
}
pub fn has_pd_basis(citation: Option<&str>) -> bool {
    citation
        .map(|c| c.starts_with(PD_BASIS_PREFIX))
        .unwrap_or(false)
}

fn loc(file: &str, key: &str) -> FindingLocation {
    FindingLocation {
        file: Some(file.into()),
        key: Some(key.into()),
        ..Default::default()
    }
}

pub const CODE_NC_COMMERCIAL: &str = "PACK_LICENSE_NC_COMMERCIAL";
pub const CODE_DATASET_SA_ND: &str = "PACK_LICENSE_DATASET_SA_ND";
pub const CODE_NOT_COMMERCIALLY_USABLE: &str = "PACK_LICENSE_NOT_COMMERCIALLY_USABLE";
pub const CODE_OUTSIDE_ALLOWLIST: &str = "PACK_LICENSE_OUTSIDE_ALLOWLIST";
pub const CODE_PD_BASIS_MISSING: &str = "PACK_LICENSE_PD_BASIS_MISSING";

pub fn check_source_nc_commercial(ctx: &RuleContext<'_>) -> Vec<Finding> {
    let mut out = Vec::new();
    for s in ctx.sources {
        if s.commercial_use == "yes" && is_nc_license(&s.license) {
            out.push(Finding::error(
                CODE_NC_COMMERCIAL,
                format!(
                    "source {} has non-commercial license {} but commercial_use=yes",
                    s.id,
                    py_repr_str(&s.license)
                ),
                loc("sources.csv", &s.id),
            ));
        }
    }
    out
}

pub fn check_dataset_sa_nd(ctx: &RuleContext<'_>) -> Vec<Finding> {
    let mut referenced: std::collections::BTreeSet<&str> = Default::default();
    for f in ctx.facts {
        if let Some(d) = f.dataset_id.as_deref() {
            referenced.insert(d);
        }
    }
    let mut out = Vec::new();
    for d in ctx.datasets {
        if !referenced.contains(d.dataset_id.as_str()) {
            continue;
        }
        if is_sa_license(&d.license) || is_nd_license(&d.license) {
            out.push(Finding::error(CODE_DATASET_SA_ND,
                format!("dataset {} has {} (SA/ND) and is referenced by a fact; derived values cannot be redistributed under this pack's license", d.dataset_id, py_repr_str(&d.license)),
                loc("datasets.csv", &d.dataset_id)));
        }
    }
    out
}

pub fn check_source_commercial_use_required(ctx: &RuleContext<'_>) -> Vec<Finding> {
    let mut out = Vec::new();
    for s in ctx.sources {
        if s.commercial_use != "yes" {
            out.push(Finding::error(CODE_NOT_COMMERCIALLY_USABLE,
                format!("source {} has commercial_use={}; every shipped source must be commercial_use=yes", s.id, py_repr_str(&s.commercial_use)),
                loc("sources.csv", &s.id)));
        }
    }
    out
}

pub fn check_source_allowlist(ctx: &RuleContext<'_>) -> Vec<Finding> {
    let mut out = Vec::new();
    for s in ctx.sources {
        if !is_allowed_license(&s.license, false) {
            out.push(Finding::error(
                CODE_OUTSIDE_ALLOWLIST,
                format!(
                    "source {} has license {}, not on the commercial-use allowlist (see ADR-005)",
                    s.id,
                    py_repr_str(&s.license)
                ),
                loc("sources.csv", &s.id),
            ));
        }
    }
    out
}

pub fn check_dataset_allowlist(ctx: &RuleContext<'_>) -> Vec<Finding> {
    let mut out = Vec::new();
    for d in ctx.datasets {
        if !is_allowed_license(&d.license, true) {
            out.push(Finding::error(CODE_OUTSIDE_ALLOWLIST,
                format!("dataset {} has license {}, not on the dataset allowlist (see ADR-005; LicenseRef-PublicDomain is not supported for datasets in 0.1.2)", d.dataset_id, py_repr_str(&d.license)),
                loc("datasets.csv", &d.dataset_id)));
        }
    }
    out
}

pub fn check_source_pd_basis(ctx: &RuleContext<'_>) -> Vec<Finding> {
    let mut out = Vec::new();
    for s in ctx.sources {
        if s.license != PD_SENTINEL {
            continue;
        }
        if !has_pd_basis(Some(&s.citation)) {
            out.push(Finding::error(CODE_PD_BASIS_MISSING,
                format!("source {} is LicenseRef-PublicDomain but its citation does not begin with 'basis:'", s.id),
                loc("sources.csv", &s.id)));
        }
    }
    out
}

#[cfg(test)]
#[allow(clippy::unwrap_used, clippy::expect_used, clippy::panic)]
mod tests {
    use super::*;
    use crate::pack::row_types::{DatasetRow, SourceRow};
    use crate::pack::rules::{EMPTY_DICT, EMPTY_FILES};

    fn s(id: &str, lic: &str, cu: &str, cit: &str) -> SourceRow {
        SourceRow {
            id: id.into(),
            url: "https://x".into(),
            license: lic.into(),
            commercial_use: cu.into(),
            access_date: "2026-01-01".into(),
            citation: cit.into(),
        }
    }
    fn d(id: &str, lic: &str) -> DatasetRow {
        DatasetRow {
            dataset_id: id.into(),
            name: "n".into(),
            version: "1".into(),
            license: lic.into(),
            checksum: "sha256:0000000000000000000000000000000000000000000000000000000000000000"
                .into(),
            url: Some("https://x".into()),
            locator: None,
            access_date: "2026-01-01".into(),
        }
    }
    fn ctx<'a>(s: &'a [SourceRow], d: &'a [DatasetRow]) -> RuleContext<'a> {
        RuleContext {
            taxa: &[],
            names: &[],
            facts: &[],
            hazards: &[],
            sources: s,
            datasets: d,
            files: &EMPTY_FILES,
            dictionary: &EMPTY_DICT,
        }
    }

    #[test]
    fn nc() {
        assert!(is_nc_license("CC-BY-NC-4.0"));
        assert!(!is_nc_license("CC-BY-4.0"));
    }
    #[test]
    fn sa_nd() {
        assert!(is_sa_license("CC-BY-SA-4.0"));
        assert!(is_nd_license("CC-BY-ND-4.0"));
    }
    #[test]
    fn composite() {
        assert!(!is_allowed_license("MIT AND Apache-2.0", false));
    }
    #[test]
    fn pd() {
        assert!(is_allowed_license("LicenseRef-PublicDomain", false));
        assert!(!is_allowed_license("LicenseRef-PublicDomain", true));
    }
    #[test]
    fn nc_finding() {
        let x = vec![s("S1", "CC-BY-NC-4.0", "yes", "x")];
        assert_eq!(check_source_nc_commercial(&ctx(&x, &[])).len(), 1);
    }
    #[test]
    fn cu_finding() {
        let x = vec![s("S1", "CC0-1.0", "no", "x")];
        assert_eq!(check_source_commercial_use_required(&ctx(&x, &[])).len(), 1);
    }
    #[test]
    fn ds_finding() {
        let x = vec![d("D000000001", "CC-BY-3.0")];
        assert_eq!(check_dataset_allowlist(&ctx(&[], &x)).len(), 1);
    }
}
