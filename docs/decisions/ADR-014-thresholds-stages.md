# ADR-014: Threshold checks and stage resolution

## Status

Accepted 2026-11-09. Implemented in milestone M13.

## Context

M13 adds two categorical calculators:

- **`threshold_check`** classifies a raw value against a four-point
  trapezoid fact (abs_min, opt_min, opt_max, abs_max).
- **`resolve_stage`** returns the biological phase of a taxon on a
  given date.

Both return `CategoricalResult` (ADR-006), not `Result`, because the
answer is a category ("optimal" / "vegetative" / ...), not a number.
This is the first milestone in which the engine uses categorical
outcomes for its own outputs (previous categorical use was only in
refusals).

The threshold trapezoid and the phase durations live in the pack; the
engine must not invent either. Stage vocabulary per archetype comes
from `dictionary/vocab/phases_by_archetype.yaml`.

## Decision

### Threshold checks

- **`threshold_check(pack, taxon_id, parameter, *, value, phase=None,
  scope=None, min_status="approved")`**
- The trapezoid comes from the pack via `resolve_fact`. The caller
  supplies only the raw value.
- **Boundaries are inclusive**: `value == abs_min` and `value == abs_max`
  are `suboptimal`, not `critical`; `value == opt_min` and
  `value == opt_max` are `optimal`.
- Refusals from `resolve_fact` (`Unknown`, `NotApplicable`,
  `InsufficientInput`) propagate unchanged.
- A non-trapezoid fact (scalar, range, enum, etc.) yields
  `not_applicable(reason="parameter ... has shape ... not trapezoid")`.
- ADR-009 envelope: `subject.calculation = "threshold_check"`,
  deterministic `request_id`, `provenance.fact_ids` names the winner,
  `evidence` = the winning fact's evidence grade.

### Stage resolution

- **`resolve_stage(pack, taxon_id, as_of_date, *, planting_date=None,
  gdd_cumulative=None, ptu_cumulative=None, events=None,
  min_status="approved")`**
- **Three modes, dispatched by arguments**:
  - **perennial events**: `events` (phase → date) provided; no
    `planting_date`, no `gdd_cumulative`. The stage is the latest
    dated event at or before `as_of_date`. Events for phases not in
    the archetype's vocabulary are dropped. If no event matches after
    filtering, or if no event falls at or before `as_of_date`, returns
    `insufficient_input`.
  - **annual thermal**: `planting_date` and `gdd_cumulative` provided.
    The phase `phase_thermal_time` facts (scalar, degree_day) are
    accumulated across phases until `cumulative >= gdd_cumulative`.
  - **annual age**: `planting_date` only. The phase `phase_duration`
    facts (scalar, day) are accumulated across phases until
    `cumulative >= elapsed_days`.
- **Boundary semantics (K71)**: `cumulative >= target`. A phase whose
  cumulative duration equals the target still returns that phase. E.g.
  with phase durations 30 / 20 / 10 / 30 and elapsed_days=30, the
  result is `vegetative` (day 30 is the last day of vegetative);
  elapsed_days=31 resolves to `flowering`.
- **Phase vocabulary** from `phases_by_archetype.yaml` (packaged path
  with source-tree fallback).
- **Phase values** from the pack via `resolve_fact`; no duration is
  invented.
- **PTU deferred**: `ptu_cumulative` provided returns
  `not_applicable(reason="photothermal staging requires a
  phase_photothermal_time parameter, not yet in the dictionary")`.
- **Refusals**:
  - both `events` and `planting_date` → `insufficient_input`
    (`missing=["events_or_planting_date"]`).
  - neither → same.
  - unknown taxon → `Unknown(code="no_match")`.
  - no phase facts available → `insufficient_input`
    (`missing=["no_phase_facts"]`).
  - `planting_date > as_of_date` → `insufficient_input`.
  - `gdd_cumulative < 0` → `insufficient_input`.
- ADR-009 envelope: `subject.calculation = "resolve_stage"`,
  deterministic `request_id`, `provenance` names the pack.

### Known limitations (recorded here, to be fixed later)

- **`ptu_cumulative` deferred.** The dictionary has
  `phase_thermal_time` (degree_day), but no
  `phase_photothermal_time`. Adding it is a dictionary change (M13.1
  or M14) plus a data change in `agri-knowledge`. Today the function
  accepts the argument and refuses with an explanatory reason.
- **Phase facts are read one-by-one.** For a 4-phase archetype,
  `resolve_stage` calls `resolve_fact` 4 times. Acceptable at current
  pack sizes; a batched query path could be added later if profiling
  shows it matters.
- **The `min_status` argument applies to phase facts only.** The
  taxon lookup itself and the archetype vocabulary are not
  status-gated. This is intentional: the archetype and the
  archetype's phase list come from the dictionary, not from a fact.
- **`temp_mean` is not a parameter of `resolve_stage`.** The caller
  computes `gdd_cumulative` from actual temperature series (e.g. via
  `agri_core.climate.gdd_series`) and passes the running total. The
  stage resolver never reads weather.

## Alternatives considered

- **One generic trapezoid checker without `resolve_fact`**: rejected.
  The trapezoid must come from the pack; letting the caller pass it
  would move threshold provenance out of the engine and into caller
  code.
- **A single stage resolver parameterised by a callable**: rejected.
  `resolve_fact` already handles status, scope, and safety; a callable
  parameter would duplicate that logic.
- **Boundary `cumulative > target`**: rejected. It misclassifies the
  last day of each phase as the first day of the next (K71).
- **PTU in M13 as a silent no-op**: rejected. `not_applicable` with an
  explicit reason is more honest than a silent 0.
- **Combining `threshold_check` and `resolve_stage` into one function**:
  rejected. The two have different refusals, different envelope
  contents, and different call sites.

## Consequences

- **Positive.** Thresholds and stage durations are composable across
  releases. A new phase or a new threshold is a data change.
- **Positive.** No threshold or phase duration is invented. Every
  value is traced to a pack fact, and the refusal path is explicit.
- **Positive.** Categorical outcomes let downstream tool schemas
  present the category as a discriminator (ADR-006). The
  `label` field carries English display text.
- **Negative.** PTU staging is deferred.
- **Negative.** 4 lookups per call for a 4-phase archetype. At current
  pack sizes (thousands of facts), this is well under any budget.

## References

- ADR-006 — CategoricalResult (status `ok_category`).
- ADR-009 — Result envelope (`subject` and `request_id`).
- ADR-004 — Fact resolution policy (used by `resolve_fact`).
- `dictionary/vocab/phases_by_archetype.yaml` — the per-archetype
  phase vocabulary.
- `dictionary/vocab/stages.yaml` — the "stage" dimension (care, cycle,
  harvest, ...) used by parameters; distinct from biological phases.
- McMaster & Wilhelm 1997 — GDD methods; the caller uses these (via
  `agri_core.climate.gdd_series`) to compute `gdd_cumulative` before
  calling `resolve_stage`.

## See also

- ADR-012 — Climate parameter catalog (the catalog itself is unchanged
  by M13; both `threshold_check` and `resolve_stage` are engine
  generics, not catalog parameters).
- ADR-013 — Thermal time and climate indices (the caller's
  `gdd_cumulative` source).
