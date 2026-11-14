# ADR-021: Tool schemas and review sheet exports

- **Status:** Accepted
- **Date:** 2026-11-14
- **Deciders:** WoodinGlass (maintainer)
- **Related:** ADR-005 (license allowlist), ADR-006 (categorical outcome),
  ADR-007 (plant-protection scope), ADR-019 (native Rust kernel),
  ADR-020 (RFC 8785 migration, planned)
- **Supersedes:** none
- **Superseded by:** none

## Context

M16 introduces two exports: `tool_schemas.json` for LLM agents and
`review_sheet.csv` for domain experts. Both are generated from the same
Pydantic models as the library, so that a schema or sheet never drifts
from the code that produced the values.

Three constraints shape the decision.

1. **Strict tool-calling APIs.** OpenAI strict and Anthropic strict both
   reject a large part of JSON Schema. `oneOf`, `allOf`, `discriminator`,
   `$ref`, `$defs`, `const`, `minimum`, `maximum`, `minLength`,
   `maxLength`, `pattern` and `format` are all rejected at tool
   registration. A schema that works in one API but not the other is a
   compatibility failure, not a strictness knob.

2. **The tool input is not the calculation output.** The engine returns an
   `Outcome` (eight discriminated variants, see
   `schema/outcome.schema.json`). A tool schema describes only what the
   agent sends to the engine; the output shape lives in a separate
   contract. Embedding `Outcome` in the tool input was rejected in this
   ADR (see Alternatives).

3. **Data files read by an LLM are untrusted.** A review sheet carries
   text from the pack (`reason`, `label`, `note`) into a spreadsheet that
   an LLM may later read. That text can contain instructions. The review
   sheet must not raise its own privileges, and the tool descriptions must
   tell the caller how to handle a refusal.

## Decision

Produce two artifacts, both generated from the same Pydantic models as
the library, but with different commit policies.

### Tool schemas: committed, input-only, strict subset

`schema/tool_schemas.json` is **committed** and **drift-tested**. A test
rejects any difference between the file and the generator output. The
file is regenerated at release time, compared with `cmp`, and attached to
the release only when the comparison passes.

The file contains fourteen tools. A function earns a slot when it:

- answers a user question (not an administrative task),
- takes arguments with units named explicitly (`temp_c`, `et0_mm_day`),
- reads per-taxon values only through `taxon_id` (the model never sends a
  base temperature or a Kc itself),
- has a golden vector and a contract test.

The fourteen tools are:

1. `resolve_taxon`
2. `resolve_fact`
3. `threshold_check`
4. `stage_resolve`
5. `site_suitability`
6. `irrigation_field_etc`
7. `irrigation_paddy_awd`
8. `irrigation_container_band`
9. `fertilizer`
10. `water_quality`
11. `propagation_plan`
12. `et0`
13. `vpd`
14. `gdd`

Excluded: `coverage` and `show` (administrative), `chill_hours` (a
lower-level primitive that belongs behind `threshold_check` or a
caller-supplied series). Splitting irrigation into one tool per mode
avoids a `mode` string that would let a model pick a wrong irrigation
algorithm.

Every tool's `parameters` schema stays inside the strict-compatible
subset:

- `type` (basic types), `enum`, `anyOf`.
- Every property is `required`; optionality is
  `anyOf: [{type: T}, {type: "null"}]`.
- `additionalProperties: false` on every object.
- Range and length information is prose in `description`; no `minimum`,
  `maximum`, `minLength`, `maxLength`.
- Tool names match `^[a-z][a-z0-9_]{0,62}$`.

Every tool description ends with a two-sentence refusal contract: a
non-`ok` status is reported to the user verbatim; the model does not
invent a number or a category; the result is advisory, not for direct
actuation.

### Host-only parameters

`pack`, `min_status` and `require_commercial` are injected by the host
and never appear in any tool schema. This is a security boundary: the
LLM cannot lower the status floor to `draft`, skip the license gate, or
choose a different pack. A test enforces the boundary by asserting that
no tool parameter set intersects the host-only set.

### Review sheet: ephemeral, per-live-fact, CSV-safe

`review_sheet.csv` and its sidecar `review_sheet.manifest.json` are
**ephemeral**. They depend on the pack and on the filter flags, they are
attached to the release, and they are never checked into git. A small
golden file at `tests/golden/exports/review_sheet.csv` acts as a migration
oracle for the Rust port: any change to the generator that is not also a
deliberate golden update fails the contract test.

One row per **live fact**, not per taxon-by-fact pair. Filters:

- `--max-status` (default `reviewed`, i.e. everything below `approved`).
- `--tier` (exact `T0`/`T1`/`T2`/`T3`, repeatable).
- `--taxon` (repeatable `taxon_id`).
- `--safety-critical` (only facts whose parameter has
  `safety_class != none`).

Read-only columns (17): `fact_id`, `taxon_id`, `scientific_name`,
`parameter`, `phase`, `value_pretty`, `value_json`, `unit`, `scope`,
`evidence`, `status`, `safety_class`, `taxon_tier`, `source_citation`,
`source_url`, `source_license`, `current_reviewed_by`.

Fill-in columns (5): `reviewer_id`, `decision`, `corrected_value_json`,
`comment`, `reviewed_on`.

Format: UTF-8, LF line endings, every cell quoted, no timestamp. The
manifest carries `pack_hash`, `csv_sha256`, `sheet_schema_version`,
`synthetic`, `row_count` and the filters, so an ingest step can verify
the sheet was generated against the same pack.

### CSV injection

Any cell that begins with `=`, `+`, `-`, `@`, tab, CR or LF is prefixed
with a tab. The writer uses `QUOTE_ALL`, so the field is stored as text;
Excel and LibreOffice read it as text. The ingest side strips one leading
tab (trusted, because it can only come from our writer) and rejects any
remaining dangerous first character (untrusted).

### Prompt injection

Free text in the review sheet comes from the pack. An LLM reading the
sheet must treat it as data, not as instructions. This ADR records a
**partial** mitigation only. Full mitigation requires length and
character bounds on `note`, `name` and `reason` in the pack validator;
that work is tracked as a separate issue and is not part of M16.

### Version policy

- `tool_schemas_version` (top-level in `schema/tool_schemas.json`):
  SemVer for the tool-schemas contract, independent of the engine
  version. A breaking change to any tool signature bumps MAJOR.
- `sheet_schema_version` (in the review-sheet manifest): SemVer for the
  review-sheet contract. A change to the column set or to the manifest
  shape bumps MAJOR.

Neither version is tied to `pyproject.toml` version or to
`RESOLUTION_POLICY_VERSION`.

## Consequences

### Positive

- One generator for both artifacts; drift tests catch accidental changes.
- The tool schemas are compatible with both OpenAI strict and Anthropic
  strict without per-vendor forks.
- The host-only boundary is enforced by test, not by convention.
- The review sheet is usable in a spreadsheet without external tooling.
- The golden file gives the Rust port a byte-identical oracle.

### Negative

- The strict subset forbids useful JSON Schema features (ranges,
  patterns, `$ref`). Range checks move to prose and to host-side
  validation; the LLM sees them only in English.
- CSV injection defense adds a tab prefix that must be stripped on
  ingest. Any third-party reader must be told the rule.
- Prompt injection from pack text remains a residual risk in M16. The
  partial mitigation is the refusal contract in tool descriptions, not a
  structural guarantee.
- Two version numbers (`tool_schemas_version`, `sheet_schema_version`)
  must be bumped by hand.

### Neutral

- The generator modules live behind `agri_core.export`; nothing else in
  the engine imports them.
- The CLI exposes one command (`agri-core export`) with three format
  options (`tool_schemas`, `review_sheet`, `both`).
- The release workflow regenerates the tool schemas in an isolated venv
  and compares to `schema/tool_schemas.json`; a mismatch fails the
  release.

## Alternatives considered

1. **Embed `Outcome` in the tool output schema.** Rejected: OpenAI strict
   and Anthropic strict do not accept the `oneOf` + `discriminator` shape
   that Pydantic emits for `Outcome`, and even the flattened form would
   change every time `Outcome` gains a variant. The `Outcome` contract
   stays in `schema/outcome.schema.json`; the tool description states how
   to handle a refusal.

2. **Auto-generate a tool per calculator function (about forty tools).**
   Rejected: too many tools with overlapping parameters confuse a model,
   increase token cost, and would turn every function signature into a
   public contract by accident.

3. **One generic `calculate` tool with a `function_name` argument.**
   Rejected: it would need every calculator's parameter set unioned into a
   single wide schema, which hides which parameters matter for which
   function and cannot enforce `additionalProperties: false` usefully.

4. **Commit the review sheet alongside the pack.** Rejected: it duplicates
   the pack, carries the license and attribution obligations of every
   source into the engine repository, and goes stale on every data change.

5. **Include `bundle.json` as in the original M16 sketch.** Deferred:
   it is a re-packaging of the pack with the same attribution obligations
   and no additional consumer, and it was dropped from the M16 scope.

## Notes

- The committed copy of `schema/tool_schemas.json` is regenerated by
  `python -m agri_core.cli export --pack sample --format tool_schemas
  --out schema` and checked by `test_tool_schemas.py`.
- The review sheet golden is regenerated by
  `python -c "from pathlib import Path; ..."` (see the assertion message
  in `test_review_sheet.py`).
- `docs/EXPORTS.md` is the operator-facing reference; this ADR records
  the design decisions behind it.
