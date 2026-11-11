# ADR-016: Suitability and propagation

## Status

Accepted 2026-11-11. Implementation begins in milestone M15.

## Context

M15 adds two domains that share the `Outcome` contract (ADR-009) and
the "pack is the source of truth" principle (every crop-specific value
comes from a pack, never from code).

- **Suitability**: single and batch site suitability. Given a site
  context (country, region, system, air temperature day and night,
  relative humidity, soil pH, soil EC, VPD, DLI) and a taxon, return
  `suitable`, `marginal` or `unsuitable` with a reason per evaluated
  factor and any hazard flags attached. Factor classification uses the
  four-point trapezoid from M13; thresholds come only from the pack.
- **Propagation**: a dated plan for a taxon and a propagation method.
  Caller supplies `start_date`; the planner emits forward absolute
  dates for each step from pack facts (`propagation_duration_days`,
  `propagation_start_months`). Methods come from a closed vocabulary.

Both domains face four shared design questions:

1. How to return a result without breaking the existing `Outcome` union.
2. How to carry per-factor reasons and hazard flags in that result.
3. How to handle a `critical`-severity hazard recorded for the taxon.
4. How to meet the batch performance expectation in README without
   inventing a budget before measuring.

## Decision

### Suitability

- **D-M15-S1**: `site_suitability` returns `CategoricalResult`
  (ADR-006) with `category` in `{suitable, marginal, unsuitable}`.
  Reuses the classification pattern M13 established for
  `threshold_check`; adds no new success model to `Outcome`.
- **D-M15-S2**: Per-factor reasons are `Notice` objects in
  `CategoricalResult.warnings`, one per evaluated factor, code
  `factor_<parameter>_<state>` where `state` is `optimal`,
  `suboptimal` or `critical`. The overall category is also emitted as
  a `Notice` with code `suitability_overall`.
- **D-M15-S3**: A `critical`-severity hazard for the taxon
  (`HazardRow.severity == "critical"`) short-circuits the calculation:
  `site_suitability` returns `ReferToAuthority` with `flags` carrying
  the hazard codes, before any factor scoring. "Refuse rather than
  guess" for safety and legal hazards.
- **D-M15-S4**: `info` and `warning` hazards do not short-circuit; they
  become `Notice` objects with code `hazard_<hazard_code>` in the
  `CategoricalResult` warnings, and factor scoring proceeds.
- **D-M15-S5**: Classification is rule-based on the per-factor
  categories:
  - any `critical` factor -> `unsuitable`;
  - any `suboptimal` factor (with no `critical`) -> `marginal`;
  - all `optimal` -> `suitable`.
  Deterministic and auditable: the caller always sees which factor
  drove the category.
- **D-M15-S6**: When pack weights are present, a weighted score
  `sum(w_i * s_i) / sum(w_i)` with `s_i` in {0, 0.5, 1} per category
  is reported as a `Notice` with code `suitability_score`. The score
  does **not** change the category. Weights are pack values, not code,
  and are optional; absent weights mean no score notice.
- **D-M15-S7**: `batch_suitability(pack, site, taxon_ids)` returns
  `list[Outcome]` in input order. Each element is an independent
  `site_suitability` result; same envelope, same refusal behaviour.
- **D-M15-S8**: Batch mode pre-fetches relevant facts per taxon from
  `KnowledgeSet` (one pass) rather than invoking `resolve_fact` per
  factor per taxon. A scenario test verifies batch and single results
  are identical for the same (taxon, site) pairs.

### Propagation

- **D-M15-P1**: The plan is a new model `PropagationPlan` with fields
  `taxon_id`, `method`, `start_date`, `steps: list[PropagationStep]`,
  plus the usual envelope fields (`subject`, `request_id`,
  `provenance`, `evidence`, `assumptions`, `warnings`).
  `PropagationStep` is `{step_name, start_date, end_date,
  duration_days}`.
- **D-M15-P2**: `PropagationPlan` is a member of a parallel union
  `PropagationOutcome = PropagationPlan | Unknown | NotApplicable |
  InsufficientInput | ReferToAuthority`. `Outcome` is unchanged. This
  follows the precedent of `FactOutcome` and `TaxonOutcome` (M8),
  which are also parallel unions discriminated by `status`.
- **D-M15-P3**: Signature is
  `propagation_plan(pack, taxon_id, *, start_date: date, method: str,
  min_status: FactStatus | None = "approved") -> PropagationOutcome`.
  Caller supplies `start_date` and `method`; the planner reads
  `propagation_duration_days` and `propagation_start_months` from the
  pack.
- **D-M15-P4**: Dates compute forward: step 1 starts at `start_date`
  (or shifted to the first `propagation_start_months` month at or
  after `start_date`, with a `Notice` recording the shift); each
  subsequent step starts the day after the previous ends. If no
  valid start month exists in the next 12 months for the method, the
  planner returns `NotApplicable` with an explanation.
- **D-M15-P5**: If the taxon has no `propagation_method` fact that
  includes the requested `method`, return `NotApplicable` with
  `reason="method not recorded for taxon"`. If the taxon has no
  propagation facts at all, return `Unknown(code="no_match")`.
  "Refuse rather than guess."

### Shared

- **D-M15-X1**: `dictionary/vocab/methods.yaml` is added as a closed
  vocabulary for `propagation_method` and `scope.method`. Values are
  generic cultivation-method names: `seed`, `stem_cutting`,
  `air_layering`, `budding`, `grafting`, `division`, `rhizome`,
  `tuber`, `bulb`, `offset`, `runner`, `spore`, `tissue_culture`,
  `marcotting`, `sucker`. Curated, not exhaustive; additions follow
  catalog-first and go through an ADR amendment.
- **D-M15-X2**: Twelve new core parameters
  (`suitability_weight_*` x 7, `suitability_threshold_marginal`,
  `suitability_threshold_suitable`, `propagation_method`,
  `propagation_duration_days`, `propagation_start_months`) enter
  `dictionary/parameters.core.yaml`. All `safety_class: none`,
  `tier_required: false`, `used_by: [suitability]` or
  `[propagation]`. Dictionary version 1.1.0 -> 1.2.0 (MINOR:
  additive, no removals, no shape changes to existing keys).
- **D-M15-X3**: `dictionary/vocab/modules.yaml` fills the `reads`
  lists for `suitability` and `propagation` to match. Keeps the
  bidirectional relation checked by `test_vocab_base`.
- **D-M15-X4**: Batch performance is measured, not claimed. The perf
  test `tests/perf/test_suitability_perf.py` measures batch 5000,
  prints actual p50/p95/total, and asserts only a generous upper
  bound (catastrophic-regression guard) until a CI baseline exists.
  README's "<= 200 ms p95" entry becomes "measured: X ms p95 at M15
  (Colab-class CPU, date); tight budget calibration deferred to CI
  baseline". Follows "record evidence, do not invent targets".

## Alternatives considered

- **A separate `SuitabilityResult` model** (rejected).
  `CategoricalResult` already carries category and `warnings`; a
  parallel success model would double the surface for one feature.
  Structured `Notice` objects in `warnings` are sufficient for
  per-factor reasons.
- **`PropagationPlan` as a member of `Outcome`** (rejected). Every
  new member forces every `TypeAdapter` and every JSON Schema
  consumer to update. M8's `FactOutcome` and `TaxonOutcome` are the
  precedent; M15 follows it.
- **Weighted score changes the category** (rejected). A high weight
  on `soil_ph` could mask a `critical` VPD failure. The rule in
  D-M15-S5 is safety-biased; the score is reported, not consulted,
  for the final category.
- **Caller-supplied method without vocabulary** (rejected). Without
  a closed set, `propagation_method` facts cannot be validated, and
  the catalog cannot report coverage. A small vocab costs little and
  enforces honesty.
- **Batch naively loops `resolve_fact`** (rejected). Measured
  `resolve_fact` p95 is ~20 us; 5000 taxa x 7 factors = 35k calls,
  roughly 700 ms. Pre-fetch reduces this to a single pass.
- **Absolute budget before measurement** (rejected). Writing "<= 200
  ms p95" into a perf test before measuring would fail on any machine
  slower than the benchmark. The test measures and reports; the tight
  budget is calibrated from a real baseline once CI exists.

## Consequences

### Positive

- `Outcome` remains stable; consumers of `Outcome` do not change.
- Suitability classification is auditable: the caller sees each
  factor's category and the rule that produced the overall category.
- Critical hazards refuse rather than compute, matching the
  project's refuse-over-guess rule for safety and legal hazards.
- Batch performance is measured before it is claimed.

### Negative

- `suitability_weight_*` and `suitability_threshold_*` parameters are
  `tier_required: false`; a pack with factors but no weights still
  produces a category. The score notice is absent when no weights
  exist.
- `hazards.csv` does not use a closed vocabulary yet
  (`hazard_codes.yaml` is not a vocab file at M15). Hazard codes are
  free-text snake_case validated by pattern only.
- `PropagationOutcome` is a second union for callers to learn.
  Mitigated by parallel structure with `FactOutcome` and
  `TaxonOutcome`.

### Risks

- `PropagationPlan` steps are forward accumulation. If pack facts
  yield durations that do not add up to a real calendar, the plan
  reports what the pack says and does not reject the inconsistency.
  A plan that disagrees with a real calendar is a data problem, not
  an engine problem.
- `suitability_score` uses pack-supplied weights. A pack with extreme
  weights (all on one factor) could report a misleading score even
  though the category rule remains correct. The category is
  authoritative.
- Batch pre-fetch reads facts for all taxon IDs into memory once.
  For the 5000-taxon batch this is well within the M9 memory budget
  (200 MB).

## Known limitations

- **`hazard_codes.yaml` is not a vocab yet.** Hazard codes are
  free-text snake_case strings, validated by pattern. Cross-pack
  consistency relies on the maintainer's discipline, not on a
  vocabulary check.
- **`suitability_weight_*` parameters are not in the climate
  catalog.** They are pack values for a non-climate calculation, not
  climate parameters; `lint-catalog` does not apply to them.
- **`suitability_threshold_marginal` and `suitability_threshold_suitable`
  are defined but not yet consulted.** The classification is rule
  based (D-M15-S5); thresholds are reserved for a future weighted
  variant. If a pack provides them, they are reported in a `Notice`
  but not used to change the category.
- **Batch perf budget is not calibrated.** The M15 perf test prints
  the actual measurement; the tight budget arrives with the first CI
  baseline. README's "<= 200 ms p95" entry becomes "measured: X ms
  p95" once X is known.
- **Propagation step names come from a closed set defined in code,
  not in the dictionary.** The steps are `prepare`, `propagate`,
  `establish`, `ready` for generic methods. Method-specific step
  names are deferred until a milestone that needs them.
- **No `advise` or `explain` subcommand in M15.** CLI adds
  `suitability` and `propagation-plan`; richer outputs are M16
  exports work.

## Amendments

### 2026-11-11 (M15 final)

Four notes recorded during implementation that were not in the original
decision:

- **`ReferToAuthority` is in `PropagationOutcome` but not emitted in
  M15.** The union member is reserved for M16 when the propagation
  hazard short-circuit policy is finalized. `propagation_plan()` never
  returns it in M15. (D-M15-P2)

- **`FlagCode` uppercase transform.** `ReferToAuthority.flags` requires
  `^[A-Z][A-Z0-9_]{1,63}$`. `HazardRow.hazard_code` is lowercase
  snake_case (`^[a-z][a-z0-9_]*$`). `site_suitability` uppercases hazard
  codes when emitting `ReferToAuthority.flags`; the pack value itself
  stays lowercase. (D-M15-S3)

- **`propagation_step_durations_defaulted`.** `propagation_duration_days`
  from the pack is the duration of the `propagate` step only.
  `prepare=1d`, `establish=7d`, `ready=1d` are fixed in code and
  recorded via `Notice(code="propagation_step_durations_defaulted")` in
  each plan's `assumptions`. Total plan span is `N + 9` days. (D-M15-P1,
  D-M15-P4)

- **`evaluate_trapezoid` is a public rename of `thresholds._evaluate`.**
  Suitability shares the one trapezoid classifier with `threshold_check`;
  there is no second implementation. The rename is additive;
  `threshold_check` behaviour is unchanged. (D-M15-S1)

## See also

- [ADR-004](ADR-004-resolution-policy.md) -- Deterministic fact
  resolution, safety floor, scope matching.
- [ADR-006](ADR-006-categorical-outcome.md) -- `CategoricalResult`.
- [ADR-009](ADR-009-result-envelope.md) -- Envelope on every `Outcome`.
- [ADR-010](ADR-010-perf-budgets.md) -- CLI performance budgets.
- [ADR-012](ADR-012-climate-catalog.md) -- Climate catalog and
  `lint-catalog`.
- [ADR-014](ADR-014-thresholds-stages.md) -- Threshold and stage
  calculators; the four-point trapezoid reused by suitability.
- [ADR-015](ADR-015-irrigation-fertilizer-media.md) -- Irrigation,
  fertilizer, media, water; the categorical-pattern reuse for M15.
