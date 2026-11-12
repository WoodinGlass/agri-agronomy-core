# ADR-017: No edge_thresholds.json in the export milestone

## Status

Accepted 2026-11-12. Removes `edge_thresholds.json` from the M16 milestone
and from the README Exports section.

## Context

M16 (Exports and documentation) listed an `edge_thresholds.json` artifact:
"compact thresholds for gateways and devices that must keep working
offline."

That artifact sits in tension with the engine's stated scope:

- The README "What this is not" section says the engine is "not a
  controller. It does not operate pumps, valves, dosing units or any other
  actuator. It returns values and plans for systems that have their own
  safeguards."
- A compact threshold bundle curated for gateways and devices is a step
  toward on-device automatic actuation: it exposes calibrated cut-offs
  outside the library's envelope checks, assumptions and warnings.
- The project refuses rather than guesses when a surface has a safety
  question. A device-facing threshold bundle is not needed for the
  library's stated scope.

Gateways do not need this artifact to consume the engine: `pack.sqlite`
carries the same facts, and CLI and API outputs are already advisory.

## Decision

1. `edge_thresholds.json` is **not** part of M16. It is removed from the
   README milestones table, the Exports paragraph and the M16 row.
2. M16 continues with `tool_schemas.json`, `review_sheet.csv` per tier, the
   quickstart notebook and the docs.
3. A device-facing bundle that reopens this scope requires a new ADR that
   states the safety argument explicitly. It cannot return as an implicit
   M16 sub-item.

## Consequences

- Consumers that want offline thresholds read `pack.sqlite` or the CLI and
  API outputs. There is no reduced artifact.
- The engine does not gain a device-targeted export surface.
- No public contract change. `tool_schemas.json`, `review_sheet.csv` and
  `bundle.json` are unaffected.

## References

- README "What this is not" (not a controller; not a sensor pipeline).
- ADR-016 (suitability and propagation) for the pattern of refusing an
  unsafe surface even when the code could be written.
