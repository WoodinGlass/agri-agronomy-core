# ADR-005: License allowlist for data sources

## Status

Accepted 2026-10-31. Supersedes the license-gate section of ADR-003.

## Context

ADR-003 (M7-4) used a blocklist: a source with an NC license and
`commercial_use=yes` was rejected, and SA/ND datasets were rejected only
when a fact referenced them. That left gaps:

- `commercial_use=no` and `commercial_use=unclear` sources passed.
- Composite SPDX expressions (e.g. `MIT OR Apache-2.0`) were rejected by
  the row model but never by an explicit rule.
- SA/ND datasets that nothing referenced were not flagged.
- The IUCN Red List was mentioned in README, CONTRIBUTING.md and
  REVIEW_GUIDE.md as an input criterion. That database's terms of use
  restrict commercial use, so citing it as an input is incompatible with
  an Apache-2.0 repository.

Apache-2.0 promises commercial use of everything shipped here. The gate
must be default-deny.

## Decision

1. **Allowlist** of exact-match SPDX identifiers, used for both
   `sources.csv` and `datasets.csv`:

   - CC0-1.0, CC-BY-3.0, CC-BY-4.0
   - MIT, BSD-2-Clause, BSD-3-Clause, Apache-2.0
   - LicenseRef-PublicDomain (sources only, see point 3)

2. **`commercial_use=yes` required.** `no` and `unclear` are ERRORs at
   `agri-core validate --strict`, `agri-core lint-sources` (exit != 0)
   and `agri-core pack build`.

3. **`LicenseRef-PublicDomain`** (sources only) requires a `citation`
   beginning with `basis:`. Missing basis →
   `PACK_LICENSE_PD_BASIS_MISSING`. Datasets cannot use
   `LicenseRef-PublicDomain` in 0.1.2: `datasets.csv` has no `citation`
   column, so a PD dataset cannot record its basis. PD datasets are
   rejected outright until a schema change lands.

4. **Blocklist findings remain.** `PACK_LICENSE_NC_COMMERCIAL` (NC + yes)
   and `PACK_LICENSE_DATASET_SA_ND` (SA/ND dataset referenced by a fact)
   stay as independent checks. The allowlist and the blocklist are both
   enforced; defence in depth.

5. **No restricted databases as input.** No IUCN Red List, no Species+,
   no FAO-56 tables. Conservation decisions cite legal instruments
   (CITES Appendices, Permen LHK 106/2018, equivalent national law) or a
   documented lawful cultivation pathway. A maintainer decision may only
   ADD an exclusion, never justify the inclusion of a taxon that would
   otherwise be protected. Per-taxon decisions are recorded in
   `docs/design/`, not in `CHANGELOG.md`.

6. **`agri-knowledge` data license — Proposed.** CC BY 4.0 for
   `LICENSE-DATA` in `agri-knowledge`. CC BY 4.0 explicitly covers
   database rights; CC BY 3.0 unported does not. This ADR does not
   decide it; the decision will be ratified in an ADR in
   `agri-knowledge` when the repository is created.

## Consequences

- **Sample pack passes.** All three sources are `CC0-1.0` and
  `commercial_use=yes`. No change to the sample pack, no `pack lock`
  required.
- **`agri-knowledge` is affected.** Any existing pack with a source or
  dataset row that is `commercial_use=no` or `unclear`, or with a
  license outside the allowlist, fails strict validation starting at
  0.1.2. Those packs must be fixed by **removing the affected facts**,
  **replacing the source**, or **obtaining written permission** from the
  rights holder. Re-labelling a row to pass the gate is not an
  acceptable fix.
- **`release.yml`** runs `agri-core validate --strict` on the
  `agri-knowledge` built pack before attaching it to a GitHub Release.
  A pack that fails strict never ships.
- **No `git filter-repo`.** The four restricted-database category labels
  in `docs/design/plant_wishlist_v4_rationale.md` (in the v0.1.0 and
  v0.1.1 tags) are single-word category labels, not assessment data.
  Verified: `git show v0.1.1:docs/design/plant_wishlist_v4_rationale.md
  | grep -i iucn` returns four taxa labels plus three policy mentions,
  and no assessment fields (no ID, no population trend, no range map,
  no citation to the restricted database). Category labels are not
  substantial copies. The content is removed from HEAD in 0.1.2; the
  tags `v0.1.0` and `v0.1.1` remain as immutable historical snapshots.
  Rewriting history for four labels is disproportionate and would break
  release integrity for existing clones.
- **Adding a license to the allowlist** requires an ADR amendment, an
  update to `_ALLOWED_LICENSES` in `sources.py`, an extension to
  `tests/contract/test_validate_license.py` and
  `tests/unit/test_sources_lint.py`, and a `CHANGELOG.md` entry. All
  four in one PR.
- **Drift test.** The eight allowlist IDs must appear verbatim in this
  ADR and in `CONTRIBUTING.md`; a drift test enforces this.

## References

- ADR-003 (tiers, license gate, duplicate facts) — license-gate section
  superseded by this ADR.
- `PACK_FORMAT.md` §Error code reference — finding codes
  `PACK_LICENSE_NOT_COMMERCIALLY_USABLE`,
  `PACK_LICENSE_OUTSIDE_ALLOWLIST`, `PACK_LICENSE_PD_BASIS_MISSING`.
- `CONTRIBUTING.md` §Data source license policy.
