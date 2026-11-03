# ADR-009: Result envelope -- subject and request_id

## Status

Proposed 2026-11-03. Blocks M10 (climate calculators). Not yet
implemented; this ADR records the design.

## Context

Every calculation returns an `Outcome` (ADR-004, ADR-006). Today an
outcome carries `status`, value/category, `method`, `provenance`,
`evidence`, `assumptions`, `warnings`, `capped`. It does **not** carry:

- **what the calculation was about** -- the taxon, the scope used, the
  calculation name;
- **a deterministic request identifier** -- so a batch of results from
  concurrent tool calls cannot be matched back to inputs.

Without these, an application that fires N calculations in parallel
(an LLM agent calling `vpd`, `gdd`, `check_threshold` on many taxa)
cannot bind result #3 to its input, nor deduplicate results across
retries. VPD from raw weather inputs has no `fact_id` to fall back on;
the current `provenance` is empty for those outcomes.

The decision must land **before M10 ships**. Factories are keyword-only
(ADR-006), so adding fields is non-breaking for existing callers; but
adding them after M10 ships would force a `schema_version` bump and
break M13 `tool_schemas.json`.

## Decision

1. **`Subject` model** in `models/envelope.py`:

       class Subject(BaseModel):
           taxon_id: str | None = None
           taxon_name: str | None = None
           scope: dict[str, Any] = {}     # scope keys used for fact lookup
           calculation: str               # e.g. "vpd", "gdd", "check_threshold"
           calculation_version: str       # semver of the calculation definition

   `taxon_id` and `scope` are `None`/empty for calculations with no
   taxon (VPD from weather, temperature from elevation).
   `calculation_version` starts at `"0.1.0"` for all M10 calculators;
   each calculator may bump it independently when its semantics change.

2. **`request_id: str | None`** on every `Outcome` member. Deterministic
   hash of the request:

       request_id = "req_" + sha256(canonical_json({
           "subject": subject.model_dump(mode="json") if subject else None,
           "inputs": inputs,             # caller inputs, canonicalized
           "engine_version": __version__,
           "pack_hash": pack_hash,       # None for pack-free calculations
       }))[:32]

   Computed by a helper `compute_request_id(*, subject, inputs, pack_hash=None)`
   in `models/envelope.py`. Calculators call it **before** computing
   the outcome and attach the result to whatever outcome they return
   (success or refusal).

   `engine_version` is read from `agri_core.__version__` inside the
   helper; it is **not** a separate field on the outcome. It is baked
   into the hash, so a version change changes every `request_id`.
   The audit trail (a separate ADR, Step 3 of the review) will expose
   it explicitly for reproducibility.

3. **`subject: Subject | None = None`** on every `Outcome` member.
   Optional so current tests that call `ok(...)` without a subject keep
   working. M10 calculators **MUST** populate it; enforcement is a
   test, not a model validator (see the Enforcement section below).

4. **All 8 outcome variants** carry the envelope:

   | Class | New fields |
   |---|---|
   | `Result` | `subject`, `request_id` |
   | `CategoricalResult` | `subject`, `request_id` |
   | `InsufficientInput` | `subject`, `request_id` |
   | `Unknown` | `subject`, `request_id` |
   | `NotApplicable` | `subject`, `request_id` |
   | `ReferToLabel` | `subject`, `request_id` |
   | `Ambiguous` | `subject`, `request_id` |
   | `ReferToAuthority` | `subject`, `request_id` |

   Refusals are responses to calculations and need the same identity.
   `TaxonOutcome` and `FactOutcome` (separate unions in
   `registry/resolution.py`) are **out of scope**: `TaxonOk` already
   carries `taxon_id`; `FactResolved` carries `fact.taxon_id`. Adding
   `request_id` there is a separate decision if a batch-resolution use
   case appears.

5. **Consistency rule.** A model validator on each outcome asserts:

       if request_id is not None then subject is not None

   `request_id` without a subject is not acceptable -- "request id of
   what?". The reverse (`subject` without `request_id`) is allowed for
   tests that construct outcomes directly.

6. **`compute_request_id` helper** in `models/envelope.py`. Pure, no
   I/O. Reuses `canonical_json` from `models/canonical.py`.

7. **Schema regeneration.** `schema/outcome.schema.json` regenerates:
   `$defs` gains `Subject`; every outcome variant gains `subject` and
   `request_id`.

8. **No change to `is_success()`** -- the two success statuses stay
   `{"ok", "ok_category"}`.

9. **No change to `Provenance`.** Engine version is inside
   `request_id`, not exposed as a field. The audit trail (Step 3 of the
   review) will expose it explicitly.

## Non-goals

- No `Request` model in this ADR. That is **Step 2** of the review and
  lands together with the first M10 calculator. `Subject` and
  `request_id` are the envelope fields; `Request` is the input
  container.
- No `TraceRecord` / `summarize`. **Step 3** of the review.
- No change to `TaxonOutcome`, `FactOutcome`, `MetaInfo`.
- No change to `RESOLUTION_POLICY.md`.
- No persistence: the engine remains pure.
- No `engine_version` field on `Provenance` or on any outcome (it is
  inside `request_id`).

## Consequences

- Adding optional `subject` and `request_id` to 8 models is mechanical
  but touches 8 model classes and 8 factory functions.
- M13 `tool_schemas.json` will describe the envelope once. Every
  outcome variant appears with the same envelope fields; LLM agents
  see `status`, `subject`, `request_id` at the top of every response.
- Existing tests calling `ok(...)`, `unknown(...)`, etc. without the
  new fields keep working (defaults).
- `request_id` is a 36-character string (`"req_"` + 32 hex). When a
  response carries many outcomes, the envelope roughly doubles the
  response size. This is the cost of determinism; a future schema bump
  may shorten the hex suffix.

## Enforcement of M10 (a test, not a model rule)

`tests/contract/test_m10_envelope.py` (added with M10, not this ADR)
asserts, for every M10 calculator function:

    outcome = vpd(temp_c=25.0, rh_pct=60.0)  # or gdd, dli, ...
    assert outcome.subject is not None
    assert outcome.subject.calculation == "vpd"
    assert outcome.request_id is not None
    assert outcome.request_id.startswith("req_")

The same test asserts determinism: two calls with the same inputs
produce the same `request_id`; a call with different inputs produces
a different one.

## Revisit when

- A second calculation group (M11, M12) ships and `Subject.scope`
  needs to carry more than `dict[str, Any]`.
- An application needs `inputs` inside the outcome (currently only the
  digest is captured via `request_id`).
- A batch use case appears for `TaxonOutcome` or `FactOutcome`;
  reconsider adding `request_id` there.

## References

- ADR-004 (resolution policy)
- ADR-006 (categorical outcomes; keyword-only factories)
- ADR-007 (plant-protection scope)
- `src/agri_core/models/result.py`
- `src/agri_core/models/refusals.py`
- `src/agri_core/models/provenance.py`
- `src/agri_core/models/outcome.py`
- `src/agri_core/models/canonical.py` (`canonical_json`)
- Review: "Hitung banyak tanaman sekaligus", point 1
