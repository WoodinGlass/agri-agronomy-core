# ADR-007: Plant-protection scope

## Status

Accepted 2026-11-02. Scope and guard active from this release.
Safety-expert review of the in-scope list is deferred; ADR-008 (data
model) is not yet written.

## Context

Users will ask about pests, diseases and their control. Some answers
are low risk (what affects a crop, which conditions favor a disease,
preventive practices). Others carry high safety and legal risk
(chemical use, regulated pests). The engine never invents numbers and
never replaces labels or authorities. Coverage must also scale to about
10,000 taxa without implying that a missing entry means a crop is free
of pests.

## Decision

1. **In scope** (informational, non-chemical): identity of threats
   (pests, pathogens, weeds) with multilingual names; host-threat
   associations scoped by country or region; environmental conditions
   favorable to a threat; preventive cultural practices stated without
   doses.

2. **Deferred** until a domain expert reviewer exists: heat or steam
   treatments with temperature and duration; solarization; monitoring
   thresholds that do not trigger a treatment.

3. **Out of scope by default**: chemical control of any kind, including
   "natural" or home mixtures (products, active ingredients, doses,
   concentrations, mixtures, spray volumes, intervals, pre-harvest and
   re-entry periods, resistance-management schedules); thresholds that
   trigger spraying; quarantine or regulated-pest status and
   import-export requirements; official eradication orders; release of
   biological control agents; protective equipment and first aid;
   symptom-to-cause diagnostic rules; efficacy claims. Such questions
   return `refer_to_label` or `refer_to_authority` via the calculation
   outcome (ADR-006).

4. **Absence is not safety.** A taxon without protection data returns
   `unknown`, never "no pests". Only an explicit, reviewed assessment
   may state that a list is complete.

5. **Floors**: evidence grade A or B only; status `reviewed` or above;
   no `imported` or `draft` facts in this domain; protection parameters
   are never `tier_required`.

6. **Guard** (`PACK_PROTECTION_OUT_OF_SCOPE` on parameters,
   `PACK_HAZARD_CODE_OUT_OF_SCOPE` on hazards). A parameter is in the
   protection domain if `stage == "protection"` **or** its key contains
   a protection token (`pest`, `disease`, `pathogen`, `weed`, `threat`,
   `biocontrol`) **or** the consecutive phrase `plant protection`.

   **Global tier** -- applied to every parameter of every stage, on key
   and enum values:

   - any token ending in `-cide` (pesticide, fungicide, herbicide,
     insecticide, acaricide, nematicide, bactericide, rodenticide,
     molluscicide);
   - tokens `adjuvant`, `surfactant`, `moa`, `frac`, `irac`, `hrac`;
   - phrases `tank mix`, `active ingredient`, `trade name`,
     `mode of action`.

   **Domain tier** -- applied only to protection-domain parameters, on
   key and enum values, plus domain-only constraints:

   - unit outside the allowlist {None, `centimeter`, `day`, `degree_Celsius`, `degree_day`, `kilopascal`, `meter`, `percent`}; default-deny;
   - tokens `dose`, `dosage`, `dosing`, `concentration`, `spray`,
     `drench`, `formulation`, `phi`, `rei`, `withholding`, `treatment`,
     `curative`, `eradicant`, `fumigant`, `fumigation`, `interval`,
     `schedule`;
   - phrases `application rate`, `product name`, `pre harvest`,
     `re entry`, `action threshold`, `economic threshold`;
   - `kind="extension"` (would bypass engine review, violating sec.8);
   - `tier_required=True`;
   - `shape="rule"` (free-form payload can carry dose strings).

   **Hazard codes** (`hazards.csv`) are checked against the same token
   sets: a code carrying a global or domain token emits
   `PACK_HAZARD_CODE_OUT_OF_SCOPE`.

7. **Size.** Threats and relations count against the pack size budget.
   A synthetic threat fixture will be added to the performance tests
   when threat entities land (ADR-008); today the budget is unchanged.

8. **Changing this scope** requires a new ADR and an explicit safety
   review.

## Enforcement

| Item | Mechanism | When |
|---|---|---|
| 1. In-scope entities (threat identity, host, conditions) | Positive review + closed vocab | ADR-008 |
| 2. Deferred items | Reviewer gate | ADR-008 |
| 3. Out-of-scope refusal (`refer_to_label` / `refer_to_authority`) | Calculation outcome (ADR-006); `safety/` module dispatches (M14) | M14+ |
| 4. Absence != safety (returns `unknown`) | Resolution policy (ADR-004) | Done |
| 5a. Protection parameters never `tier_required` | `check_protection_out_of_scope` | Done (this ADR) |
| 5b. Evidence grade A/B, status `reviewed`/`approved`, no `imported`/`draft` facts | Pack validator fact-level check | ADR-008, before first protection parameter |
| 6. Global + domain token / phrase / unit / kind / shape / tier | `check_protection_out_of_scope` + `check_hazard_code_out_of_scope` | Done (this ADR) |
| 7. Pack size budget | `PACK_TOO_LARGE` (engine); threat fixture deferred to ADR-008 | Engine side done, fixture pending |
| 8. Scope change requires new ADR | Process | N/A |

## Known limitations

- **Units not yet in registry.** Wetness duration (`hour`) and
  rotation intervals (`week`, `month`, `year`) are needed for some
  in-scope items but are not canonical units today. Adding them is a
  separate dictionary MINOR change.
- **Extension parameters.** `ParameterKind="extension"` parameters are
  not merged into `dictionary.parameters` by the loader. The guard
  rejects extensions in the protection domain outright (sec.6), which
  covers the safety concern for now.
- **Hazard code risk.** Before this ADR, `hazard_code` was open
  snake_case with no vocabulary check. The new
  `check_hazard_code_out_of_scope` rule closes the observed gap
  (``spray_dose_per_hectare``).
- **`datasets.csv`** has no ``kind`` column, so a
  ``pesticide_products`` dataset kind cannot appear; no additional
  guard needed there.

## Revisit when

- A first protection-domain parameter is proposed (activates the guard
  in practice).
- A domain expert reviewer joins (unblocks Deferred items sec.2).
- `agri-pest-vision` or `agri-rag-agent` ships (validates the
  out-of-scope refusal behavior end-to-end).

## References

- ADR-003 (tiers, license, duplicates)
- ADR-004 (resolution policy: `unknown`, absence is not safety)
- ADR-005 (license allowlist)
- ADR-006 (categorical outcomes)
- `README.md` (section "Not a pesticide tool")
- `docs/SAFETY.md`
