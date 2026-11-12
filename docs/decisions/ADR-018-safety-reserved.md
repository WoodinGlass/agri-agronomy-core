# ADR-018: regulatory and toxicity_limit are reserved safety classes

## Status

Accepted 2026-11-12. Clarifies `dictionary/vocab/safety_classes.yaml` and
closes the contradiction with "Not a compliance tool" in the README.

## Context

`dictionary/vocab/safety_classes.yaml` defines four values: `none`,
`dose_cap`, `toxicity_limit` and `regulatory`. As of this decision:

- No parameter in `dictionary/parameters.core.yaml` uses `toxicity_limit`
  or `regulatory`.
- Every safety-critical parameter uses `dose_cap` (three parameters:
  `n_max_per_application`, `p2o5_max_per_application`,
  `k2o_max_per_application`).
- The README says the engine is "not a compliance tool. It does not encode
  national or regional rules on fertilizers, water use or plant
  protection." A live `regulatory` class invites exactly that.

Removing the two values is a MAJOR dictionary change (a removed enum value
is a breaking change) for no benefit: the classes are inert. The honest fix
is to keep them reserved and test that nothing uses them.

## Decision

1. `toxicity_limit` and `regulatory` remain in the vocabulary as
   **reserved**. No parameter, core or extension, may use them until a new
   ADR defines the hazard model and the review workflow.
2. `dictionary/vocab/safety_classes.yaml` records the reserved status.
3. `docs/SAFETY.md` stops describing them as currently used classes.
4. A contract test fails if any parameter uses them.
5. Enabling either class requires a new ADR that states:
   - the hazard model (which harm, measured how),
   - the source class the values must come from (no restricted databases),
   - the review workflow (double review, plus the caller-facing refusal
     path).

## Consequences

- The contradiction between "Not a compliance tool" and a live
  `regulatory` class is closed.
- `resolve_fact` behaviour is unchanged: `dose_cap` is the only
  safety-critical class in use.
- Enabling a reserved class later is a MAJOR dictionary release plus an
  ADR; this ADR does not pre-approve one.

## References

- README "What this is not" (not a compliance tool; not a pesticide tool).
- `dictionary/vocab/safety_classes.yaml`.
- `docs/SAFETY.md` "Safety-critical parameters".
- ADR-005 (license allowlist): the no-restricted-databases rule that any
  future hazard model must respect.
