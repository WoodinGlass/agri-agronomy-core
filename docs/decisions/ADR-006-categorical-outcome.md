# ADR-006: Categorical outcomes for calculations

## Status

Proposed 2026-11-02. Blocks M10 (climate calculators).

## Context

`Outcome` (`models/outcome.py`) is a discriminated union on `status`:

    Result | InsufficientInput | Unknown | NotApplicable
          | ReferToLabel | Ambiguous | ReferToAuthority

`Result.value` is `float`, enforced by `allow_inf_nan=False`. This is
correct for M10 numeric calculators:

- `vpd()` -> kPa
- `gdd()` -> degree-days
- `dli()` -> mol/m^2/day
- `et0()` -> mm/day
- `temp_from_elevation()` -> degC

M10 also introduces two calculators whose answer is **not numeric**:

- `check_threshold()` -> `"optimal"` | `"suboptimal"` | `"critical"`
- `stage_resolver()` -> `"vegetative"` | `"flowering"` | `"maturity"`

M11 (irrigation) and M12 (suitability) add more categorical answers.
Coercing them into `Result.value: float` is not an option: there is no
natural numeric encoding, and `stage_resolver` outputs are not ordered.

The decision must land **before M10**. `tool_schemas.json` (M13) is the
public tool-calling contract for downstream LLM agents; reshaping
`Outcome` after M13 exists would force a `schema_version` bump.

## Options considered

### A - Sibling `CategoricalResult` with `status="ok_category"`  (chosen)

Add a new model next to `Result`. Add it to the `Outcome` union. Callers
dispatch on `status`.

- Pros: zero breakage to `Result`. Matches the existing pattern
  (`TaxonOk`, `FactResolved` already do this). Tool schemas enumerate two
  variants. Type-safe without nested unions.
- Cons: callers check two statuses (`"ok"` and `"ok_category"`) for the
  success path.

### B - Make `Result.value` a nested union

`Result.value: NumericValue | CategoryValue`, discriminated by a new
`kind` field.

- Cons: breaks every `result.value` caller; requires two-level dispatch
  (`if status=="ok": if value.kind=="numeric" ...`); `unit` field becomes
  conditional.

### C - Return a normalized score from `check_threshold()`

`check_threshold()` returns e.g. `0.85` on a 0-1 scale; the caller maps
it to a category.

- Cons: `stage_resolver` outputs are not ordered and cannot be encoded
  this way; semantics of "0.85 means optimal" is not discoverable from
  the schema.

### D - Optional `category` field on `Result`

`Result.value: float | None` plus `category: str | None` plus `label:
str | None`.

- Cons: allows invalid combinations (`value=None, category=None`);
  validators cannot express "exactly one of value/category"; `value=0.0`
  for pure categorical is a footgun.

## Decision

**Adopt option A.**

1. **New model `CategoricalResult`** in `models/result.py`, next to
   `Result`. Fields:

       status: Literal["ok_category"]
       category: str        # stable code, e.g. "optimal"
       label: str           # human-readable, English, e.g. "Optimal range"
       method: str
       provenance: Provenance
       evidence: list[EvidenceGrade]
       assumptions: list[Notice]
       warnings: list[Notice]

   Same `extra="forbid"`, `frozen=True` as `Result`.

2. **Add to the `Outcome` union** in `models/outcome.py`:

       Outcome = Annotated[
           Result
           | CategoricalResult
           | InsufficientInput
           | Unknown
           | NotApplicable
           | ReferToLabel
           | Ambiguous
           | ReferToAuthority,
           Field(discriminator="status"),
       ]

3. **Factory** `ok_category(...)` next to `ok(...)`, keyword-only.

4. **Semantics.** The set of allowed `category` codes is decided per
   calculator and documented in its docstring and its dictionary entry.
   `category` is stable; `label` is display text and may change between
   minor releases.

5. **No change to `Result`, `TaxonOk`, `FactResolved`, or any refusal
   model.**

## Consequences

- **No breaking change** for any existing code. `Result.value` stays
  `float`.
- M10 calculators return `Result` (numeric) or `CategoricalResult`
  (categorical). Both carry the same provenance/evidence/warnings shape,
  so generic helpers (`format_outcome`, tool schemas) can share code.
- **Callers** switch on `status`. A helper
  `is_success(outcome) -> bool` returning `outcome.status in {"ok",
  "ok_category"}` will be added to make the two-status success path
  ergonomic.
- **M13 tool schemas** will describe two `"ok"`-family variants. LLM
  agents see `status` as the discriminator and pick accordingly; this is
  already how the refusal family works today.
- **No migration** required: no production consumer of `Result` exists
  (M10 has not shipped, M13 does not exist).

## Non-goals

- No changes to `FactValue` (that is data, not a calculation result).
- No new numeric coercion helper for categories.
- No change to `RESOLUTION_POLICY.md`.

## References

- `src/agri_core/models/outcome.py` - current union
- `src/agri_core/models/result.py` - current `Result`
- `src/agri_core/registry/resolution.py` - existing pattern of sibling
  success models with distinct discriminators
- ADR-004 (resolution policy) - why discriminated unions are used
- Handoff sec.3 - M10 scope (which calculators return which shape)
