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

## Decision — Duplicate facts

- Code `PACK_FACT_KEY_DUPLICATE` for facts with identical
  `(taxon_id, parameter, phase, canonical_scope)`. **Error**.
- Two facts with the same key but different values from different `src`
  are corroboration, not duplicates. **No warning.**
- `FACT_CONFLICT` remains M8 (resolution time, not load time).
- `superseded_by` must reference an existing fact. Cycles →
  `PACK_SUPERSEDED_CYCLE`. Self-supersession is an error. Superseded
  facts are excluded from tier calculation and duplicate detection.

## Decision — Exit codes

- `validate`: 0 ok; 1 any `severity = error` finding; 3 pack could not be
  loaded (`knowledge_set is None`).
- `validate --strict`: warnings promote to exit 1.
- `diff`: 0 normal differences; 1 status-aware violations; `--exit-code`
  also promotes normal differences to exit 1.
- `coverage`: 0 informational; 3 unreadable pack.

## Consequences

- `RULES` is a `tuple[RuleFn, ...]` in `pack/validate.py`. Adding a rule
  is a one-line change plus a test.
- Every new code gets a section in `PACK_FORMAT.md`
  (`test_finding_drift.py` enforces this).
- Sample pack must stay at 0 errors, 0 warnings.
