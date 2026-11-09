# ADR-015: Irrigation, fertilizer, media and water

## Status

Accepted 2026-11-10. Implemented in milestone M14 (sub-phases M14a–M14g).

## Context

M14 adds three domains that share one contract: `Outcome` (ADR-009),
`CategoricalResult` (ADR-006) for non-numeric answers, and pack-only
crop values.

- **Irrigation**: `irrigate_field_etc` (numeric), `irrigate_paddy_awd`
  (categorical), `irrigate_container_band` (categorical). Kc, stage
  lengths, depletion fraction, `must_flood_phases`, `awd_reflood_depth`,
  and `moisture_band` all come from the pack.
- **Fertilizer**: `fertilize_n`, `fertilize_p2o5`, `fertilize_k2o`.
  Caller supplies the nutrient dose and product composition; the
  engine converts to product mass and enforces the per-application
  dose cap. Caps are `safety_class=dose_cap` facts.
- **Media/water**: `compute_sar` (Richards 1954), `compute_rsc`
  (Eaton 1950), `check_water_quality` (categorical). Limits come from
  `water_ec_max` / `water_temp_max`.

## Decision

### Irrigation

- **Three separate functions**, not one dispatcher. Each mode has a
  different input shape and output type; a dispatcher would force
  unused arguments.
- **Container band is categorical** (`irrigate` / `hold` / `drain`)
  read from the `moisture_band` trapezoid. A numeric volume would need
  pot volume, substrate, and drainage rate, none in the dictionary.
- **Paddy AWD is phase-aware** (`reflood` / `hold`). A phase listed in
  `must_flood_phases` forces `reflood` regardless of measured depth;
  otherwise compare `water_table_depth_cm` to `awd_reflood_depth`.
- **`field_etc` returns `max(0, ETc - P_eff)`** (Q7=A1, not
  `not_applicable`). A numeric 0 is more useful than a category here:
  it preserves the resolved Kc in provenance and distinguishes
  "no irrigation needed" from "no Kc fact".
- **Kc comes only from the pack.** No built-in Kc table. FAO-56 is
  not used (its reuse terms and handbook tables are out of policy).
  `resolve_fact` with `phase_set=kc` keeps phase and scope handling
  unchanged.

### Fertilizer

- **Caller supplies composition** (Q2=A). Formula:
  `product_kg_ha = effective_nutrient_kg_ha / (product_pct / 100)`.
  No hardcoded product names.
- **Dose cap enforced in-function** (Q9=A). `resolve_fact` resolves
  `*_max_per_application`; `apply_dose_cap` clamps the nutrient
  amount (not product -- cap units are nutrient) and sets
  `capped=True` + `Notice(code="dose_cap_applied")`.
- **K2 = refuse if cap missing.** No hardcoded fallback.
- **Q14b = sample-pack safety facts at `reviewed`.** Enough for tests;
  does not trigger `PACK_SAFETY_DOUBLE_REVIEW_MISSING`. Real packs
  must use `approved` + 2 reviewers.
- **N = `min_status=None` default.** Lets `resolve_fact` raise the
  floor to `reviewed` and attach `safety_min_status_raised`. Callers
  who pass `min_status="approved"` remain strict.
- **Alpha = `method_ref` changed** for `compute_fertilizer_n/p2o5/k2o`
  from `IUPAC atomic weights` to `caller composition (division)`.
  The formula is a pure division. IUPAC is reserved for the future
  `p2o5_to_p` / `k2o_to_k` utility (deferred).

### Media and water quality

- **Q6 = SAR/RSC in catalog, not dictionary.** Inputs are kwargs, no
  pack lookup. Adding dictionary parameters would have been a MINOR
  bump for values the engine never resolves from a pack.
- **Q8 = `check_water_quality` is categorical.** Four exhaustive
  categories (`ok`, `exceed_ec`, `exceed_temp`, `exceed_both`).
- **D-M14f-1** = `dimensionless` for SAR and RSC (matches catalog).
- **D-M14f-2** = `*_meq_l` argument names carry the unit
  (`meq/L` is not in `CANONICAL_UNITS`; the docstring states it).
- **D-M14f-3** = `check_water_quality` defaults to `min_status="approved"`.
  Limits are `safety_class=none`, so no floor change.
- **D-M14f-4** = temperature limit resolved first. Surfaces the
  unknown-valued `water_temp_max` (`F00000000013` on `T000000004`)
  before any EC lookup.
- **D-M14f-6** = unknown-valued limit becomes `Unknown(code=None)`.
  `value_unknown` is `planned`, not active; emitting it would fail
  the drift test.
- **D-M14f-7** = `check_water_quality` not in catalog. Engine-generic,
  same reasoning as `threshold_check` / `resolve_stage` (M13).

### Cross-cutting

- **Runtime narrowing via `isinstance(x, tuple)`.** `Outcome` is
  `typing.Annotated[Union[...], FieldInfo(...)]` -- `isinstance(x, Outcome)`
  raises `TypeError` at runtime. `_resolve_limit` returns a 4-tuple on
  success and an `Outcome` refusal otherwise; the caller narrows with
  `if not isinstance(x, tuple): return x`.
- **K1 = SAR/RSC return numbers only.** No banding in the engine.
- **No FAO-56, FAO-29, EU Regulation 2003/2003, or handbook tables.**
  SAR: Richards 1954 equation only (USDA Handbook 60 is public
  domain, but the classification table is not reproduced). RSC:
  Eaton 1950 equation only. Fertilizer: pure division. ETc: Allen
  1996 composition.

## Alternatives considered

- **Q1 = inline fixture** (rejected). Milestone acceptance says
  "passes against the sample pack"; the sample pack now exercises
  resolution end to end.
- **Single dispatcher `irrigate(mode=...)`** (rejected).
- **Q7 = A2 (`not_applicable` when ETc <= P_eff)** (rejected). Hides
  Kc provenance and makes two different answers indistinguishable.
- **Keep `IUPAC atomic weights` on fertilizer rows** (rejected).
  Formula does not use them.
- **`EU Regulation 2003/2003` as `method_ref`** (rejected).
  Regulations change; handoff forbids regulatory citations.
- **External `enforce_dose_cap` helper** (rejected). Safety
  enforcement must be in the function producing the recommendation.
- **`min_status=None` for `check_water_quality`** (rejected). Limits
  are `safety_class=none`, so normal floor applies.

## Consequences

### Positive

- One `Outcome` contract across irrigation, fertilizer, and media.
- Safety is enforced in-function (`capped` field + warning code).
- Every crop value comes from the pack; the engine refuses rather
  than guessing.
- Provenance carries fact IDs, pack version, pack hash.

### Negative

- `capped=True` can surprise a caller who reads only `value`.
  Mitigated by `dose_cap_applied` warning + `capped` field.
- SAR/RSC do not validate agronomic plausibility (K1).
- No elemental-P / elemental-K convenience: caller must convert
  before calling (deferred utility).

### Risks

- Sample-pack safety facts are synthetic `reviewed`; not for real
  decisions.
- `docs/SAFETY.md` previously described the safety floor as raising
  "regardless of the caller's `min_status`"; the implementation
  raises only if the caller's floor is lower. Updated in this
  milestone (see `docs/SAFETY.md` L26-29): now aligned with the
  code behavior.

## Known limitations and tracked debt

- **`# type: ignore[arg-type]` (2) in `src/agri_core/irrigation/modes.py`.**
  `evidence=` gets `list[EvidenceGrade]`; mypy treats it as `list[str]`
  without an explicit cast. Cleanup: `cast(list[EvidenceGrade], ...)`.
- **`provenance.source_ids=[]`** for all M14 calculators. Pack facts
  carry `src`; the calculator does not propagate. Follow-up touches
  `resolve_fact` and all calculators uniformly.
- **`p2o5_to_p` / `k2o_to_k` not shipped.** Pure math utilities
  (0.4364, 0.8301 from IUPAC atomic weights). No catalog row yet.
- **`agri-core calc` CLI deferred.** README CLI row updated from
  "calc in M14" to "calc deferred". Wrapper needs naming and parsing
  design.
- **`compute_sar` / `compute_rsc` return `dimensionless`.**
  RSC physically carries `meq/L`; caller applies it.
- **`irrigate_field_etc` returns 0 rather than `not_applicable`** when
  precipitation covers ETc (Q7=A1, deliberate).

## References

- Richards, L. A. (1954). *Diagnosis and Improvement of Saline and
  Alkali Soils*. USDA Agriculture Handbook No. 60. Public domain (US
  Government work). Equation only.
- Eaton, F. M. (1950). "Significance of Carbonates in Irrigation
  Waters." *Soil Science* 69(2):123-134. Equation only.
- Allen, R. G. (1996). "Assessing integrity of weather data for
  reference-evapotranspiration estimation." *Journal of Irrigation
  and Drainage Engineering* 122(2):97-106. ETc = Kc * ET0 composition.
- McMaster, G. S. & Wilhelm, W. W. (1997). "Growing degree-days: one
  equation, two interpretations." *Agricultural and Forest Meteorology*
  87:291-300. Context for thermal time (M12).
- Lampayan, R. M. et al. (2015). "Adoption and economics of alternate
  wetting and drying water management for irrigated lowland rice."
  *Field Crops Research* 170:95-108. AWD threshold context; the value
  comes from the pack.
- IUPAC (2021). "Atomic weights of the elements 2021." *Pure and
  Applied Chemistry*. Reserved for the future `p2o5_to_p` /
  `k2o_to_k` utility; not used in M14 main path.

## See also

- [ADR-004](ADR-004-resolution-policy.md) -- Deterministic fact
  resolution, safety floor, scope matching.
- [ADR-006](ADR-006-categorical-outcome.md) -- `CategoricalResult`.
- [ADR-007](ADR-007-plant-protection-scope.md) -- Plant-protection
  boundary; not modified by M14.
- [ADR-009](ADR-009-result-envelope.md) -- Envelope on every `Outcome`.
- [ADR-012](ADR-012-climate-catalog.md) -- Climate catalog and
  `lint-catalog`.
- [ADR-014](ADR-014-thresholds-stages.md) -- Threshold and stage
  calculators; the `CategoricalResult` pattern reused by M14.
