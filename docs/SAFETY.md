# Safety and limitations

What this library enforces today (v0.1.0). Where a claim is backed by a
test, the test is named in backticks; where a claim is a design decision
that is **not** covered by a test, it is marked
"(design constraint, not tested)" so the gap is explicit.

## Enforced today

### Safety-critical parameters

Parameters with a `safety_class` other than `none` in
[`DICTIONARY.md`](DICTIONARY.md) (`dose_cap`, `toxicity_limit`,
`regulatory`) are never `draft` or `imported`. `resolve_fact` raises the
status floor to `reviewed` for them regardless of the caller's
`min_status`, and records a `safety_min_status_raised` warning.

- `tests/contract/test_resolve_fact.py::test_safety_floor_raised`

### Status floor

Calculators only see facts at or above the caller's `min_status`. The
default is `approved`. `draft` and `imported` are never returned unless
the caller explicitly lowers the floor, and safety-critical parameters
ignore that lowering.

- `tests/contract/test_resolve_fact.py::test_status_default_approved_excludes_reviewed`
- `tests/contract/test_resolve_fact.py::test_min_status_reviewed_includes_reviewed`

### Tier T3 requires two reviewers

A taxon reaches T3 only when every `tier_required` parameter is
`approved`, **and** every safety-critical fact on that taxon has at
least two distinct reviewer IDs in `reviewed_by`. A single-reviewer
approved safety-critical fact is not T3.

- `tests/contract/test_tiers.py::test_mini_t3_requires_approved`
- `tests/contract/test_tiers.py::test_safety_critical_single_reviewer_not_t3`
- `tests/contract/test_tiers.py::test_safety_critical_two_reviewers_t3`
- `tests/contract/test_validate_safety.py::test_rule_fires_on_approved_single_reviewer`
- `tests/contract/test_validate_safety.py::test_rule_passes_approved_two_reviewers`

### License gate

Sources with `commercial_use="no"` are excluded when the caller sets
`require_commercial=True`. A fact whose only source is non-commercial
returns `Unknown(code="license_excluded")`, not the fact.

- `tests/contract/test_resolve_fact.py::test_license_gate_excludes_nc`
- `tests/contract/test_resolve_fact.py::test_license_gate_cc0_passes`

### Pesticides are out of scope

The library does not implement pesticide, herbicide or fungicide dose
calculators. When a caller requests one, the outcome is `refer_to_label`
(follow the product label and local regulations) or `refer_to_authority`
(consult the regulator). This is a **design constraint**: there is no
pesticide calculator module to test. The outcome types themselves are
tested.

- `tests/unit/test_outcome_smoke.py` (`refer_to_label`,
  `refer_to_authority`)
- `tests/unit/test_outcome_validators.py`
- `tests/unit/test_outcome_discrimination.py`

### No actuation

The library returns values and plans; it does not operate pumps, valves,
dosing units or any other actuator. *(design constraint, not tested —
there is no actuator code to test.)*

### `unknown`, `not_applicable` and `insufficient_input` are outcomes

Expected "cannot answer" cases are outcomes, not exceptions. The
resolution outcome types are distinct from `Result` so callers cannot
mistake "could not answer" for a value.

- `tests/contract/test_resolve_fact.py::test_applies_to_mismatch_returns_not_applicable`
- `tests/contract/test_resolve_fact.py::test_phase_none_phased_param_insufficient`

## Planned (M11+)

Not yet enforced. Listed here so that the boundary between "today" and
"planned" is visible.

- Dose caps (`safety_class: dose_cap`) applied inside fertilizer
  calculators. At v0.1.0 the class is recorded and enforced at
  resolution time only; there is no `agri-core calc fertilizer` command
  yet.
- Per-application cap enforcement for `n_max_per_application`,
  `p2o5_max_per_application`, `k2o_max_per_application`, with
  `capped=true` on `Result`.
- Irrigation safety checks: out-of-range water EC / temperature returns
  `refer_to_label` or `refer_to_authority` rather than a value.
- Media and water-quality calculators with the same status floor and
  license gate already used by `resolve_fact`.

## See also

- [`RESOLUTION_POLICY.md`](RESOLUTION_POLICY.md) — filter order and status floor
- [`DICTIONARY.md`](DICTIONARY.md) — which parameters are safety-critical
- [`decisions/ADR-003-tiers-license-duplicates.md`](decisions/ADR-003-tiers-license-duplicates.md) — T0–T3 derivation and license gate
- README §Safety and limitations
