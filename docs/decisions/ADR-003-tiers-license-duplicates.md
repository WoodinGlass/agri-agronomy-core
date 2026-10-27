# ADR-003: Tiers, license gate, and duplicate facts

Status: Accepted (M7-1). Updated as M7 sub-cells land.

## Decision — Tiers

- **T0** — identity only. Taxon present in `taxa.csv`, no facts.
- **T1** — at least one fact of any status. `imported < draft < reviewed
  < approved`. T1 does **not** skip `draft`; any fact counts.
- **T2** — every parameter with `tier_required = true` is present at
  status >= `reviewed` **or** present with `value.shape = unknown` and
  status >= `reviewed`. Weak-link per fact: minimum status across the
  taxon's current facts per parameter (and per phase, see below) wins.
- **T3** — T2 + every `tier_required = true` parameter is `approved` +
  every safety-critical fact is `approved` with at least two independent
  reviewers, encoded as a comma-separated list in the existing
  `reviewed_by` TEXT column.

Notes:

- `applies_to.systems` is not counted for tiers. `TierResult` carries
  `system_gaps`: parameters whose `applies_to.systems` is non-empty and
  that are absent from the taxon's facts. `coverage` displays
  `system_gaps` but does not use them in the tier calculation.
- Phase coverage requires **all** phases in `allowed_phases` ∩
  `phases_by_archetype[archetype]` to be present at the required status.
  Partial phase coverage fails.
- **Deviation from README:** README says "every core parameter"; this ADR
  restricts T2/T3 to `tier_required = true` (5 of 31 parameters) because
  "every core parameter" is unreachable in practice and the flag exists
  precisely for this purpose. `REVIEW_GUIDE.md` will be updated in M7-5.

## Decision — License gate

Two rules, identical in `validate`, `build`, and `coverage`:

- **L1** — a source with NC license (CC-BY-NC-*, CC-BY-NC-SA-*,
  CC-BY-NC-ND-*) and `commercial_use = yes` is an error. This matches
  `lint-sources` (`SRC001`) and is promoted from a source-row warning to
  a pack-level error.
- **L2** — a dataset whose `license` is SA (CC-BY-SA-*) or ND
  (CC-BY-ND-*, CC-BY-NC-ND-*) that is referenced by any `dataset_id` in
  the pack is an error. Derived values must be redistributable under the
  pack's own license, which SA and ND forbid.

No rule for "safety-critical requires commercial source" — not in README.

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
