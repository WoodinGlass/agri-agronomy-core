# ADR-003: Tiers, license gate, and duplicate facts

Status: Accepted (M7-1). Updated as M7 sub-cells land.

## Decision — Tiers (finalized M7-5)

Tiers are **derived**, not declared. `pack/tiers.py` computes:

- **T0** — identity only. Taxon exists; no live (non-superseded) facts.
- **T1** — at least one live fact at any status (`imported`, `draft`,
  `reviewed`, `approved`). `draft` is **not** excluded; the status
  ordering is `imported < draft < reviewed < approved`.
- **T2** — every parameter with `tier_required=True` that matches the
  taxon (by `applies_to.organism_groups`, `archetypes`, `uses`) has a
  live fact at status >= `reviewed`. Parameters with
  `applies_to.systems` are **excluded** from tier (see below).
  Phase-bearing parameters (`phase_set != "none"`) require **all**
  phases in `allowed_phases` or, if `allowed_phases` is `None`, **all**
  phases in `phases_by_archetype[taxon.archetype]`. Partial phase
  coverage fails. `value.shape == unknown` counts only if
  status >= `reviewed`.
- **T3** — T2 + every `tier_required=True` parameter is `approved` +
  every safety-critical fact (`safety_class != "none"`) is `approved`
  with **>=2 distinct reviewers** (encoded as an ordered `list[str]`
  in the `reviewed_by` column). T3 is unreachable for a taxon whose
  safety-critical facts are `reviewed` (single reviewer) — the T3
  check fails accordingly, and rule `PACK_SAFETY_DOUBLE_REVIEW_MISSING`
  additionally fires as an error (fail-closed).

**Weakest-link per fact.** For each `(parameter, phase)`, the minimum
status across all live facts determines coverage. Fact rows are
iterated in sorted `fact_id` order; row order in the CSV does not
affect the result.

**System-scoped parameters.** `applies_to.systems` is not a property
of a taxon, so parameters like `kc`, `root_depth`, `awd_reflood_depth`,
and `n_max_per_application` are **never** counted for tier. A taxon
can be T3 without any irrigation fact. This is by design; `TierResult`
carries `system_gaps` (matching system-scoped params with no live
fact) so `agri-core coverage` can surface the omission. T2/T3 does
**not** certify system-scoped parameters.

**`reviewed_by` is `list[str] | None`.** Single reviewer encodes as
one element; `"|".join(sorted(items))` is byte-identical to a single
string for the 1-reviewer case, so no CSV migration is needed. Two
reviewers encode as `"a|b"`. Model canonicalizes to `sorted(set(v))`
so reorderings do not appear as diffs.

**Deviation from README.** README says "every core parameter is
approved" for T3. This ADR restricts T3 to `tier_required=True`
parameters (5 of 31) plus safety-critical facts; "every core
parameter" is unreachable in practice and would prevent any taxon
from ever reaching T3. `REVIEW_GUIDE.md` documents the final
definition.

## Decision — License gate (finalized M7-4)

Two rules, identical in `validate_pack_report` and therefore in
`agri-core validate`, `agri-core pack build`, and `agri-core coverage`
(all use the single validation pipeline).

- **`PACK_LICENSE_NC_COMMERCIAL`** — a source with NC license
  (`is_nc_license`) and `commercial_use=yes` is an error. Pack-level
  promotion of `SRC001` from `agri-core lint-sources` (which already
  emits `SRC001` as `error` -> `lint-sources` exits 1). All three
  commands agree: NC+yes is never accepted.
- **`PACK_LICENSE_DATASET_SA_ND`** — a dataset with ShareAlike or
  NoDerivatives license (`is_sa_license` or `is_nd_license`) that is
  referenced by any fact is an error. SA/ND forbid redistribution of
  derived values under this repository's Apache-2.0 license.
  Unreferenced datasets are not flagged (dead weight, not a
  redistribution problem).
- **No rule for "safety-critical requires commercial source"** — not
  in README, removed from earlier drafts.
- **No rule for SA/ND *source*** — BY-SA and BY-ND permit commercial
  use; `commercial_use=yes` is valid for those. Only NC is a
  commercial-use restriction on sources. (SA/ND on *datasets* matters
  for redistribution of *derived values*, hence the separate dataset
  rule.)
- **Detection helpers live in `registry.sources`**
  (`is_nc_license`, `is_sa_license`, `is_nd_license`), reused by
  `agri-core lint-sources` and M7-4 rules. Token splitting on `-`
  (case-insensitive); `NASDAQ` does not match `sa`, `INDIA` does not
  match `nd`.

## Decision — Duplicate facts (finalized M7-3)

- **`PACK_SUPERSEDED_SELF`** — a fact cannot set `superseded_by` to
  its own `fact_id`.
- **`PACK_SUPERSEDED_CYCLE`** — cycles in the `superseded_by` chain
  are rejected. One finding per cycle, anchored at the smallest
  `fact_id` in the cycle for determinism. Self-loops are handled by
  `PACK_SUPERSEDED_SELF`, not here.
- **`PACK_FACT_KEY_DUPLICATE`** — two live facts with identical
  `(taxon_id, parameter, phase, canonical_scope)` and **different**
  `value` are an error. Message names both `fact_id`s and instructs
  the author to supersede one via `superseded_by`.
- **Corroboration is allowed.** Same key, same value, different `src`
  is independent confirmation, not a duplicate.
- **Superseded facts are excluded** from the duplicate check.
- **FK for `superseded_by`** remains `PACK_FK_VIOLATION` (enforced in
  `loader.py::_validate_structure` at load time, consistent with
  `parent_id`, `dataset_id`, `src`). Not renamed; M7-3 does not
  duplicate the FK check.
- `FACT_CONFLICT` remains M8 (resolution time, not load time).
- **Canonical scope form** for key equality: `canonical_json(fact.scope)`
  (sorted keys, compact separators, UTF-8). Matches the encoding used
  by `hash_pack_files` and SQLite `_sql_value`.

## Decision — Exit codes

- `validate`: 0 ok; 1 any `severity = error` finding; 3 pack could not be
  loaded (`knowledge_set is None`).
- `validate --strict`: warnings promote to exit 1.
- `diff`: 0 normal differences; 1 status-aware violations; `--exit-code`
  also promotes normal differences to exit 1.
- `coverage`: 0 informational; 3 unreadable pack.

## Decision — Fact field classification for diff (added M7-6)

`diff` classifies fact field changes into two buckets:

- **Violation** — `value`, `scope`, `parameter`, `taxon_id`, `phase`
  **but only when the OLD fact was `reviewed` or `approved`**. Once
  a fact is reviewed, its content is frozen; any change requires a
  new `fact_id` with `superseded_by` on the old one. `draft` and
  `imported` facts are still under editorial control; their content
  fields may change in place.
- **Acceptable** — `status`, `evidence`, `reviewed_by`, `reviewed_at`,
  `locator`, `superseded_by`, `src`, `dataset_id`, `provenance_kind`;
  **and all content fields when the OLD status was `draft` or
  `imported`**.

Taxon metadata changes (name, archetype, uses, etc.) are reported but
do not exit 1; only taxon *removal* is a violation.

## Decision — Trapezoid degenerate check (added M7-2)

`PACK_TRAPEZOID_DEGENERATE` fires when a trapezoid's `pts[0] == pts[-1]`.
The model already enforces `a <= b <= c <= d` at load
(`TrapezoidValue._check_order`). If additionally `a == d`, all four
points are equal and the "trapezoid" has no suboptimal zone; that is a
scalar with no tolerance band. The finding message says "use scalar".

Range `min <= max` is enforced by `RangeValue._check_order` at load;
violating packs fail `PACK_TABLE_INVALID` before any M7 rule can run.
**No M7 rule for range exists.** This is recorded here so a future
contributor does not add a redundant check.

## Consequences

- `RULES` is a `tuple[RuleFn, ...]` in `pack/validate.py`. Adding a rule
  is a one-line change plus a test.
- Every new code gets a section in `PACK_FORMAT.md`
  (`test_finding_drift.py` enforces this).
- Sample pack must stay at 0 errors, 0 warnings.
