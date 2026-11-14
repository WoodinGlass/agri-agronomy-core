# Exports

M16. `agri-core export` generates two artifacts from a loaded knowledge
pack. Both are versioned public contracts. This document is the reference
for their format, threat model and regeneration.

## Two artifacts

| Artifact | File | Committed? |
|---|---|---|
| Tool schemas | `schema/tool_schemas.json` | Yes (drift-tested) |
| Review sheet | `dist/exports/review_sheet.csv` + `review_sheet.manifest.json` | No (ephemeral) |

`tool_schemas.json` is committed because it is a stable contract; a drift
test rejects any change that is not regenerated. `review_sheet.csv` is
ephemeral because it depends on the pack and on the filter flags, is not
safe to check in, and is attached to the release.

## Tool schemas

`schema/tool_schemas.json` contains fourteen function-calling tools for
LLM agents, generated from the same Pydantic models as the library.

### Tools

1. `resolve_taxon` -- resolve a name (any language) to a `taxon_id`.
2. `resolve_fact` -- read one fact (value + provenance) for a taxon.
3. `threshold_check` -- classify a value against trapezoid thresholds.
4. `stage_resolve` -- growth stage from age, thermal time, or events.
5. `site_suitability` -- evaluate a site against a taxon at a phase.
6. `irrigation_field_etc` -- net irrigation by ETc.
7. `irrigation_paddy_awd` -- paddy alternate wetting and drying.
8. `irrigation_container_band` -- container and band-grown irrigation.
9. `fertilizer` -- element rate to product amount, dose-capped.
10. `water_quality` -- EC, pH, SAR and RSC checks.
11. `propagation_plan` -- dated propagation plan.
12. `et0` -- reference evapotranspiration (Penman-Monteith with a
    Hargreaves-Samani fallback).
13. `vpd` -- vapour pressure deficit.
14. `gdd` -- growing degree days from daily temperatures.

`coverage`, `show` and `chill_hours` are not exposed as tools: two are
administrative commands, and `chill_hours` is a lower-level primitive that
belongs behind `threshold_check` or a caller-supplied series.

### Input-only, strict subset

Each tool carries only an **input** schema. The output shape (`Outcome`,
eight discriminated variants) stays in `schema/outcome.schema.json`; the
description of every tool states that any non-`ok` status is reported
verbatim. This is deliberate. OpenAI strict and Anthropic strict reject
`oneOf`, `allOf`, `discriminator`, `$ref`, `$defs`, `const`, `minimum`,
`maximum`, `minLength`, `maxLength`, `pattern` and `format`, so the schema
stays in the strict-compatible subset:

- `type` (basic types), `enum`, `anyOf`.
- Every property is `required`; optionality is modeled as
  `anyOf: [{type: T}, {type: "null"}]`.
- `additionalProperties: false` on every object.
- Physical ranges (min/max) and string length bounds are stated in
  `description` as plain English.

### Host-only parameters

The following parameters are **host-injected** and never appear in a tool
schema, so the LLM cannot lower the status floor or skip the license
gate:

- `pack` -- the knowledge pack to query.
- `min_status` -- the minimum fact status the caller accepts.
- `require_commercial` -- the license gate.

### Refusal contract

Every tool description ends with a two-sentence contract: a non-`ok`
status (`unknown`, `insufficient_input`, `not_applicable`,
`refer_to_label`, `refer_to_authority`, `ambiguous`) is reported to the
user verbatim; the model must not invent a number or a category; results
are advisory, not for direct actuation.

## Review sheet

`review_sheet.csv` (with sidecar `review_sheet.manifest.json`) contains
one row per **live fact** (not a per-taxa x per-fact cartesian product),
filtered by:

- `--max-status` (default: `reviewed`, i.e. everything below `approved`).
- `--tier` (exact `T0`/`T1`/`T2`/`T3` filter, repeatable).
- `--taxon` (repeatable `taxon_id` filter).
- `--safety-critical` (only facts whose parameter has
  `safety_class != none`).

### Columns

Read-only (17): `fact_id`, `taxon_id`, `scientific_name`, `parameter`,
`phase`, `value_pretty`, `value_json`, `unit`, `scope`, `evidence`,
`status`, `safety_class`, `taxon_tier`, `source_citation`,
`source_url`, `source_license`, `current_reviewed_by`.

Fill-in (5): `reviewer_id`, `decision`, `corrected_value_json`,
`comment`, `reviewed_on`.

Format: UTF-8, LF line endings, every cell quoted (`QUOTE_ALL`), no
timestamps. The manifest carries `pack_hash`, `csv_sha256`,
`sheet_schema_version`, `synthetic`, `row_count` and the filters used, so
an ingest step can verify that the sheet was generated against the same
pack.

### CSV injection defense

Any cell whose first character is `=`, `+`, `-`, `@`, tab, CR or LF is
prefixed with a tab. The CSV writer uses `QUOTE_ALL`, so the field is
stored as text. Excel and LibreOffice read it as text; a formula
injection cannot execute. The ingest side strips one leading tab
(trusted, because it can only come from our writer) and rejects any
remaining dangerous first character (untrusted).

### Prompt injection mitigation

Free text in the review sheet comes from the pack. An LLM reading the
sheet must treat it as data, not as instructions. This is a **partial**
mitigation. Full mitigation requires length and character bounds on
`note`, `name` and `reason` in the pack validator; that work is tracked
as a separate issue and is not part of M16.

## Version policy

- `tool_schemas_version` (top-level in `schema/tool_schemas.json`):
  SemVer for the tool-schemas contract, independent of the engine
  version. A breaking change to any tool signature bumps MAJOR.
- `sheet_schema_version` (in the review-sheet manifest): SemVer for the
  review-sheet contract. A change to the column set or to the manifest
  shape bumps MAJOR.

Neither version is tied to `pyproject.toml` version or to
`RESOLUTION_POLICY_VERSION`.

## Regeneration

```bash
# From the repo root.
python -m agri_core.cli export --pack sample --out dist/exports --format both

# Or via the Makefile.
make exports
```

The release workflow runs the same command inside an isolated venv,
compares the output to `schema/tool_schemas.json` and to
`tests/golden/exports/review_sheet.csv`, and only attaches the artifacts
to the release when both comparisons pass.

## Related

- `schema/tool_schemas.json`
- `schema/outcome.schema.json` (result contract, not tool input)
- `src/agri_core/export/tool_schemas.py`
- `src/agri_core/export/review_sheet.py`
- `tests/contract/test_tool_schemas.py`
- `tests/contract/test_review_sheet.py`
