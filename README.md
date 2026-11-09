<h1 align="center">agri-agronomy-core</h1>

<p align="center"><strong>Offline, deterministic calculation engine and data contract for cultivation knowledge across countries and taxa.</strong><br>
Every crop-specific value comes from a verified knowledge pack, never from a language model.</p>

<p align="center">
  <a href="https://github.com/WoodinGlass/agri-agronomy-core/actions/workflows/ci.yml"><img src="https://github.com/WoodinGlass/agri-agronomy-core/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <img src="https://img.shields.io/badge/status-0.1.2--foundation-blue" alt="Status">
  <img src="https://img.shields.io/badge/python-3.11%20%7C%203.12%20%7C%203.13%20%7C%203.14-blue" alt="Python">
  <img src="https://img.shields.io/badge/license-Apache--2.0-blue" alt="License">
  <img src="https://img.shields.io/badge/mypy-strict-blue" alt="mypy">
  <img src="https://img.shields.io/badge/pre--commit-enabled-brightgreen" alt="pre-commit">
  <img src="https://img.shields.io/github/last-commit/WoodinGlass/agri-agronomy-core" alt="Last commit">
</p>

> **0.1.2 (foundation release) + M8 review follow-up + M10 climate catalog on `main` (unreleased).** The tag `v0.1.2` covers the data contract, the pack lifecycle, and deterministic fact resolution; `v0.1.1` fixed `agri-core pack lock` on a stale `content_hash`; `v0.1.2` makes the data license gate default-deny with an explicit allowlist and adds `NOTICE`, `ADR-005`, and related CI checks (see [CHANGELOG](CHANGELOG.md)). **Since `v0.1.2`, the M8 review follow-up series (G1–G14) tightened the resolution contract**: `RESOLUTION_POLICY_VERSION` 1.0.0 → 1.4.0, `Unknown.filter_counts` + `Unknown.warnings` + refined refusal codes (`below_min_status`, `scope_not_covered`, `input_too_long`), `MetaInfo.engine_min`, `resolve_taxon` input length guard (200 chars), Hypothesis fuzz, cross-process determinism, and a multi-scale perf test (1k/10k/100k). **M10 ships the climate parameter catalog (32 rows) with the `lint-catalog` gate, a generated `docs/CLIMATE_CATALOG.md`, and a shipped excluded list that `validate` uses to reject matching extension parameters (`PACK_CATALOG_EXCLUDED_PARAMETER`, dormant until extension parameters enter the pack format — see [ADR-012](docs/decisions/ADR-012-climate-catalog.md)).** All recorded in the `[Unreleased]` section of [CHANGELOG](CHANGELOG.md). The calculation engine (atmosphere and radiation, ET0, thermal time and climate indices, thresholds and stages, irrigation, fertilizer, media, suitability, propagation) ships in v0.2+, followed by soil-water, drought and vegetation-index modules. Interfaces, the pack format and the JSON Schemas may still change in the 0.x line; see [Versioning and releases](#versioning-and-releases). This project provides a calculation engine and a data contract; it is not professional agronomic advice. Read [Safety and limitations](#safety-and-limitations) before relying on any output.

## What this is

`agri-agronomy-core` is two things:

1. **A data contract.** JSON Schemas, a parameter dictionary, a climate parameter catalog, a pack format (CSV tables, hashed at lock time and verified at load) and a deterministic fact-resolution policy. The contract lives here. The data lives in [`agri-knowledge`](https://github.com/WoodinGlass/agri-knowledge).
2. **A calculation engine.** Pure-Python functions that read a knowledge pack and compute climate quantities and indices, threshold checks, growth stages, irrigation, soil-water balance, fertilizer amounts, growing-media recipes, site suitability and propagation plans.

The engine covers vegetables, fruit, staple carbohydrates, fodder (grown for feed, not rations), ornamental plants and cultivated fungi. Rare species are carried with a legal-status attribute taken from legal instruments, not from restricted databases (see [Protected species](#protected-species)). "Agronomy" is used loosely to mean cultivation.

Adding a taxon or a country is a data change in `agri-knowledge`, not a code change here. Every crop-specific value the engine uses comes from a pack with a citation. Equations and physical constants live in tested code and are referenced in the documentation.

It runs fully offline: no network access, database server, API key or GPU. The pack is a single immutable file; loading it never touches the network.

## What this is not

- **Not a data repository.** This repository contains the engine, the schemas, the dictionary and the sample pack used by tests. Real data lives in `agri-knowledge`.
- **Not a substitute for an agronomist, extension service, product label or local law.** It supports decisions; it does not make them.
- **Not a pesticide tool.** It never calculates pesticide, herbicide or fungicide doses. Such requests return `refer_to_label` or `refer_to_authority`. The scope of plant-protection data is defined in [ADR-007](docs/decisions/ADR-007-plant-protection-scope.md); a two-tier guard rejects chemical-control tokens in every parameter (`PACK_PROTECTION_OUT_OF_SCOPE`).
- **Not a controller.** It does not operate pumps, valves, dosing units or any other actuator. It returns values and plans for systems that have their own safeguards.
- **Not a UV or lamp-design tool.** Ultraviolet dosing (UV-A, UV-B, UV-C), germicidal use and lamp or light-spectrum recipes are out of scope for safety reasons. Photosynthetically active radiation (PAR, PPFD) and the daily light integral (DLI) are supported as plant-light quantities.
- **Not a server, database or user interface.** There is no HTTP API or web editor, only a Python package and a command-line tool.
- **Not a sensor pipeline or a data provider.** It does not read, clean or store sensor streams, and it does not download or redistribute weather, climate-grid or satellite data. Callers pass values in, with explicit units.
- **Not machine learning.** It contains no models and performs no training or inference.
- **Not a crop recommender, diagnostic tool, growth simulator or yield forecaster.** It evaluates the crop you name. It does not rank crops, identify pests or diseases, simulate biomass or growth rates, or predict yield.
- **Not a compliance tool.** It does not encode national or regional rules on fertilizers, water use or plant protection.
- **Not an encyclopedia.** Coverage is exactly what the pack contains, and `unknown` is a valid answer.

## Design principles

1. **Numbers come from data and tested code, never from a language model.** The engine may explain a result; it must not invent one.
2. **Refuse rather than guess.** Every calculation returns an `Outcome`. Missing input gives `insufficient_input`. Missing data gives `unknown`. An ambiguous taxon name gives `ambiguous`. A question that does not apply gives `not_applicable`. A legal or regulatory question gives `refer_to_authority`. There are no silent defaults, and expected "cannot answer" cases are never exceptions.
3. **The pack is the source of truth.** Every fact carries a `fact_id`, a status, an evidence grade, a scope and a source. Every `Result` records which fact IDs it used, the pack version and pack hash, and the source IDs behind the values.
4. **Deterministic fact resolution.** Facts are filtered in a fixed order, scope matching uses union semantics, and ties are broken by specificity, status, review date and `fact_id`. The engine never borrows a value from another taxon or region; no match gives `unknown(code="no_match")`; conflicts raise `fact_conflict`. See `docs/RESOLUTION_POLICY.md` for the normative spec and worked examples.
5. **Pure and repeatable.** No I/O in calculators and no hidden clock: dates are arguments. The same input against the same pack always gives the same output.
6. **Immutable, explicit state.** A loaded pack is a `KnowledgeSet`: immutable, thread-safe, created by the caller. No singletons, hidden caches, current-directory lookups or environment-variable reads.
7. **Scoped, not global.** No single pH, temperature or dose fits every taxon, country and growing system. Values declare their scope; the engine answers `unknown` outside it.
8. **Conservative by default.** Fertilizer amounts have per-application caps, pesticides are never computed, conversions that need an explicit factor (such as EC to ppm) refuse to run without one, and safety-critical parameters are never `draft` or `imported`.
9. **Three kinds of change, three kinds of release.**
   - *Data only* (taxa, names, facts, countries, sources): a new pack release in `agri-knowledge`. No engine release.
   - *Dictionary* (core parameters used by calculators): an engine **minor** release. Extension parameters that are informational only are declared inside the pack and validated by the engine, with no engine release.
   - *Code* (a new calculation mode or archetype registered in the code): an engine release.
10. **Commercially usable throughout.** The code is Apache-2.0, and every source behind a shipped pack must allow commercial use. See [Licensing policy](#licensing-policy).
11. **Catalog first.** A climate parameter is added to the [climate parameter catalog](#climate-parameter-catalog), with its method reference, license status and safety tier, before any code is written for it. The gate runs on the catalog, so a parameter that fails the license or safety rules never reaches the engine.

## Features

| # | Area | What it does | Target | Status |
|---|------|--------------|--------|--------|
| 1 | Data contract | JSON Schemas for `outcome`, `source`, `taxon`, `name`, `fact`, `hazard`, `parameter`, `dataset`, `manifest`. Core dictionary (`parameters.core.yaml`) with physical ranges, `applies_to`, tier requirements, phases per archetype, safety-class taxonomy and an append-only lock. | M2–M4 | Done |
| 2 | Pack lifecycle | `load` (hash-verified, eager `KnowledgeSet`) in M5; `scaffold`, `build` (CSV → SQLite + manifest, reproducible) in M6; full `validate`, `diff`, `coverage` in M7. | M5–M7 | Done |
| 3 | Registry | `resolve_taxon(name, language?)` returns `ok`, `ambiguous` or `unknown`. `resolve_fact` applies the deterministic resolution policy. `meta()` reports engine version, pack version, `schema_version`, `resolution_policy_version` and pack hash. | M8 | Done |
| 4 | Climate catalog and contract | One catalog of every climate parameter (`docs/design/climate_catalog_v1.csv`): kind (`computed`, `input`, `pack_value`), unit, method reference, owning repository, `commercial_use`, safety tier, status and milestone. A `lint-catalog` gate rejects rows whose source is not commercially usable, rows with a high safety tier that are not excluded, and `implemented` `computed` rows without a method reference or a test. A list of excluded parameters, generated from the catalog and shipped with the package, lets `validate` reject matching extension parameters in a pack. `docs/CLIMATE_CATALOG.md` is generated from the CSV. | M10 | Done |
| 5 | Atmosphere, radiation and ET0 | Vapor pressure deficit (VPD), dew point and wet-bulb temperature, daylength and photoperiod, solar and net radiation with the clearness index, photosynthetic photon flux density (PPFD) and daily light integral (DLI) with explicit conversion factors, wind speed and direction from U/V components, wind run, wind-speed height adjustment, and pressure and temperature estimates from elevation. Reference evapotranspiration (ET0): Penman–Monteith reference-crop method, with a Hargreaves–Samani fallback. Every estimated input is reported as an assumption. | M11 | Done |
| 6 | Thermal time and climate indices | Growing degree days (GDD) with documented methods, chilling (chill hours, Utah units, Dynamic-model portions) and photothermal units. One generic index engine (threshold, window, aggregation) driven by a documented registry: day counts, dry, wet, frost and heat spells, rolling sums and temperature extremes. Bioclimatic variables from monthly values, and 10-day or monthly aggregation. A gap in a series gives `insufficient_input`; nothing is filled silently. | M12 | Done |
| 7 | Thresholds and stages | Four-point trapezoid checks that return `optimal`, `suboptimal` or `critical`. Stage resolver from planting age and thermal time (GDD or photothermal units); perennials driven by dated events supplied by the caller. Observed dates (sowing, germination, flowering, maturity) enter as caller-supplied events. Threshold and stage values come only from the pack. | M13 | Not started |
| 8 | Irrigation, fertilizer, media and water | Three irrigation modes (`field_etc`, `paddy_awd`, `container_band`), crop evapotranspiration (ETc) from a stage-wise Kc curve, nutrient-to-product conversion with safety caps, growing-media recipes, and water-quality limits and indices (SAR, RSC). Every mode declares the parameters it requires; missing → `unknown` or `insufficient_input`. Kc values come only from the pack. | M14 | Not started |
| 9 | Suitability and propagation | Single and batch site suitability with `suitable`/`marginal`/`unsuitable` and per-factor reasons; dated propagation plans. | M15 | Not started |
| 10 | Exports | `tool_schemas.json` (function-calling schemas with `taxon_id`, `country`, `system`), `edge_thresholds.json` per site, `review_sheet.csv` per tier. | M16 | Not started |
| 11 | Soil water balance | Pedotransfer estimates of field capacity, wilting point and available water from texture and organic matter; a daily soil-water balance with depletion and a water-stress coefficient (Ks) that feeds the `field_etc` irrigation mode. Depletion fractions and other crop values come only from the pack. | M17 | Not started |
| 12 | Drought and season indices | Standardized Precipitation Index (SPI) with a minimum-record check, an aridity index (precipitation over ET0), and rainy-season onset and cessation from a registry of documented, configurable definitions. | M18 | Not started |
| 13 | Vegetation-index band math | Band-ratio indices computed from caller-supplied reflectance values: NDVI, EVI, SAVI, GNDVI, NDRE, NGRDI and PSRI, plus two water indices kept apart by name (`ndwi_mcfeeters` from green and NIR, `ndmi` from NIR and SWIR). No raster I/O and no imagery in this repository. LAI, FAPAR and canopy cover are inputs, not computed. | M19 | Not started |
| 14 | Command line | `lint-sources` and a basic `validate` ship in M0; `pack lock` in M5; `pack scaffold` and `pack build` in M6; full `validate --json --strict`, `diff` and `coverage` in M7; `show` in M8; `lint-catalog` in M10; `calc` in M14; `export` in M16. | M0, M5–M16 | In progress |

## Quick start

### Install

Releases are distributed as git tags. Pin one:

```bash
pip install "git+https://github.com/WoodinGlass/agri-agronomy-core@v0.1.2"
```

`v0.1.2` is the current patch release; `v0.1.0` is the foundation release. `v0.1.1` remains available but does not enforce the license allowlist; use `v0.1.2` for new work. To track the main branch instead, replace `@v0.1.2` with `@main` (development only; not recommended for anything you deploy).

Each published release is also on PyPI: `pip install agri-agronomy-core==<version>` (verify the `SHA256SUMS` from the matching GitHub Release).

Requires Python 3.11 or newer (tested on 3.11, 3.12, 3.13 and 3.14 on Ubuntu-latest, and on 3.11 on Windows-latest). Runtime dependencies: Pydantic v2, jsonschema, PyYAML (`safe_load` only), pint, Typer, packaging and `sqlite3` (Python stdlib). Pure Python, CPU only.

### Google Colab

Install in any Colab cell:

```python
!pip install -q "git+https://github.com/WoodinGlass/agri-agronomy-core@v0.1.2"
```

No API key or GPU is needed. Pure Python, CPU only.

### Data packs

Data packs are released separately by [`agri-knowledge`](https://github.com/WoodinGlass/agri-knowledge) under Semantic Versioning. A release carries `agri-knowledge-<version>.tar.gz` (a built pack that extracts to `agri-knowledge-<version>/`) and a `SHA256SUMS` file. Check the hash, extract the archive and pass the directory to `load_knowledge_set`. The first data release, `v0.1.0`, is planned after `agri-knowledge` milestone K5; until then the synthetic sample pack bundled with the package (used by `--pack sample`) is the only pack available.

```bash
VERSION=0.1.0   # planned; not released yet
BASE=https://github.com/WoodinGlass/agri-knowledge/releases/download/v$VERSION
curl -fLO $BASE/agri-knowledge-$VERSION.tar.gz
curl -fLO $BASE/SHA256SUMS
sha256sum --check --ignore-missing SHA256SUMS
tar -xzf agri-knowledge-$VERSION.tar.gz
```

### Python

The snippet uses the signatures the contract tests exercise today. Calculation functions (`vpd`, `gdd`, `et0`, irrigation, fertilizer) ship in M11–M14.

```python
from pathlib import Path

from agri_core import registry
from agri_core.pack import load_knowledge_set

# Load a pack explicitly. No current-directory lookup, no environment variables.
# The directory is an extracted agri-knowledge release (planned: v0.1.0).
pack = load_knowledge_set(Path("/data/agri-knowledge-0.1.0"))

# Resolve a taxon by name. Returns TaxonOk, Ambiguous or Unknown.
outcome = registry.resolve_taxon(pack, "tomato")
if outcome.status == "ok":
    print(outcome.taxon_id, outcome.name, outcome.matched_via)
elif outcome.status == "ambiguous":
    print([c.taxon_id for c in outcome.candidates], "truncated=", outcome.truncated)
else:  # "unknown"
    print(outcome.code, outcome.reason)

# Optional: prefer a name in a given language tag (e.g. from names.csv).
outcome = registry.resolve_taxon(pack, "Bawang", language="id")
taxon_id = outcome.taxon_id if outcome.status == "ok" else None

# Resolve a fact for a taxon. Returns FactResolved, Unknown, NotApplicable
# or InsufficientInput.
fact = registry.resolve_fact(pack, taxon_id, "soil_ph")
if fact.status == "ok":
    print(fact.value_pretty, fact.fact.fact_id, fact.provenance.pack_hash)

# Metadata for the loaded pack (pure; no filesystem or clock access).
info = registry.meta(pack)
print(info.engine_version, info.pack_version, info.content_hash)
```

### Command line

```bash
agri-core --help
agri-core validate --pack sample [--json] [--strict]   # manifest + sources + structural rules (M7)
agri-core lint-sources --pack sample       # sources.csv checks
agri-core pack lock --pack src/agri_core/_samples/sample_pack   # regenerate content_hash (repairs a stale hash)
agri-core pack scaffold --pack PATH --scientific-name NAME --archetype annual --use vegetable  # add a taxon
agri-core pack build --pack src/agri_core/_samples/sample_pack --out build/  # build SQLite
agri-core coverage --pack sample          # tier distribution + per-taxon coverage
agri-core diff --old A --new B [--json] [--exit-code]  # compare two packs

# M8 resolution and inspection
agri-core show --pack sample --name "Testus annualis" [--language LANG] [--json]                 # resolve a name
agri-core show --pack sample --taxon T000000001 [--min-status S] [--require-commercial] [--json]  # show a taxon + facts
agri-core show --pack sample --fact F00000000001 [--json]                                        # show a fact by id

# M10 climate catalog
agri-core lint-catalog --catalog docs/design/climate_catalog_v1.csv    # lint the climate parameter catalog
```

## Output contract

Every calculation returns an `Outcome`, a discriminated union whose `status` field says what happened. Expected "cannot answer" cases are outcomes, not exceptions, and every outcome is JSON-serializable. Exceptions are reserved for programmer errors, such as a wrong argument type or an unparseable unit string.

| `status` | Type | When |
|---|---|---|
| `ok` | `Result` | The calculation succeeded with a numeric answer. |
| `ok_category` | `CategoricalResult` | The calculation succeeded with a non-numeric answer (an enum, category, or rule). Per [ADR-006](docs/decisions/ADR-006-categorical-outcome.md); carries the envelope fields plus `value_category` instead of `value`/`unit`. |
| `insufficient_input` | `InsufficientInput` | A required input is missing, or a conversion needs an explicit factor (EC to ppm: 0.5, 0.64 or 0.7). Lists what is missing. |
| `unknown` | `Unknown` | The answer needs a value the pack marks as unknown, or no fact covers the requested scope. Gives a `reason` and an optional stable `code` (registered in `schema/unknown_code_registry.json`; six active as of 0.1.2 + M8 review follow-up: `empty_input`, `no_match`, `input_too_long`, `below_min_status`, `scope_not_covered`, `license_excluded`). `FactOutcome`'s `Unknown` also carries `filter_counts` and `warnings` (see [Resolution outcomes](#resolution-outcomes-m8)). |
| `not_applicable` | `NotApplicable` | The question does not apply (for example no standard Kc, or a propagation method the taxon does not use). Gives a reason. |
| `refer_to_label` | `ReferToLabel` | Pesticides: follow the product label and local regulations. |
| `ambiguous` | `Ambiguous` | A taxon name resolves to more than one candidate. Lists `candidates` (each with `taxon_id`, `name`, optional `note`), capped at 20 with `truncated: bool`; the caller must choose one. |
| `refer_to_authority` | `ReferToAuthority` | The answer depends on a legal or regulatory authority. Gives a `reason` and a sorted, unique list of `flags` (stable uppercase codes). |

A successful `Result` has `status` plus these payload fields:

| Field | Meaning |
|---|---|
| `status` | Always `ok`. |
| `subject` | Envelope metadata (ADR-009): what the calculation is about. Optional in the model today; required for calculators from M11 onward. |
| `request_id` | Deterministic request identifier (ADR-009): same subject and inputs give the same `request_id`. Optional in the model today; required for calculators from M11 onward. |
| `value` | The computed value. Always finite: NaN and infinity are rejected because they are not valid JSON. |
| `unit` | Explicit unit. The library never guesses units. |
| `method` | How it was computed (for example which ET0 method). |
| `provenance` | Where the numbers came from: fact IDs, pack version, pack hash and source IDs. |
| `evidence` | Evidence grade(s) of the facts used. |
| `assumptions` | Every assumed or defaulted condition, stated explicitly. Each has a stable `code` and a message. |
| `warnings` | Fallback methods, out-of-range inputs, near-threshold results, `fact_conflict`, `safety_min_status_raised`. Each has a stable `code` and a message. |
| `capped` | `true` if a safety cap limited the result. |

The word `unknown` appears at three levels: a fact whose value is marked unknown (with a reason), a factor without data inside a suitability breakdown, and the `unknown` outcome returned when an answer would need such a value.

### Resolution outcomes (M8)

`resolve_taxon` returns a `TaxonOutcome`, `resolve_fact` returns a `FactOutcome`. These are **separate unions** from `Outcome`, discriminated by `status`, kept apart to avoid the `status="ok"` collision with `Result`. Each has its own `TypeAdapter` in `registry/resolution.py` and its own JSON Schema in `schema/`.

- **`TaxonOk`** (`status="ok"`): `taxon_id`, `name`, `matched_via` (`scientific_name` / `accepted_name` / `names`), `scientific_name`, `rank`. `resolve_taxon(pack, name, *, language=None)` accepts an optional BCP-47 tag; when set and at least one matching entry carries it, the candidate set narrows to those entries before `matched_via` precedence. When no entry matches, the full set is used (soft preference — a scientific-name query with `language="id"` still resolves via `scientific_name`). Input is capped at **200 characters** (`_MAX_INPUT_LENGTH`); over-bound input returns `Unknown(code="input_too_long")` **before** normalization.
- **`FactResolved`** (`status="ok"`): `fact` (the winning `FactRow`), `value` / `value_pretty` (`format_value(fact.value)`), `alternatives` (other non-superseded matches, sorted by the same tie-break), `provenance` (`fact_ids` names only the winner; `pack_version`, `pack_hash`, `source_ids`), `warnings` (`fact_conflict`, `safety_min_status_raised`), `min_status_applied` (the effective status floor after default and safety-floor adjustments; `"imported"` when no floor applies).
- **`Unknown`** shared by both unions: `reason` (mandatory), optional `code`, and two G8 fields:
  - `filter_counts` (`dict[str, int] | None`): per-stage exclusion counts from the resolver's filter loop (`total`, `superseded`, `min_status`, `phase`, `scope`, `license`). `None` for `resolve_taxon` and for early-exit paths (empty input, taxon not found, parameter not found).
  - `warnings` (`list[Notice]`): carries `scope_values_available` (G8-4) when the request scope shares a key with a fact but the values differ; range values are not enumerated.

  The registry `schema/unknown_code_registry.json` tracks each code as `active` (already emitted) or `planned` (reserved for a later release); a drift test rejects `planned` codes appearing in source. **Six active codes**: `empty_input`, `no_match`, `input_too_long` (G9), `below_min_status` (G8), `scope_not_covered` (G8), `license_excluded`. `value_unknown` remains `planned` (G6: unknown-valued winners surface as `FactResolved(value=UnknownValue)`, not `Unknown`).
- **`Ambiguous`** (from `resolve_taxon`): `candidates` capped at 20, sorted by `taxon_id`; `truncated=True` when the cap is hit.
- **`NotApplicable`**: `applies_to` mismatch on `resolve_fact`.
- **`InsufficientInput`**: missing or invalid `phase` on `resolve_fact`.

### `MetaInfo` (`meta(pack)`)

`meta(pack) -> MetaInfo` is a pure function over the loaded pack: `engine_version`, `resolution_policy_version` (G5, mirrors `RESOLUTION_POLICY_VERSION`), `pack_version`, `schema_version`, `dictionary_version`, `content_hash` (mirrors `pack_hash`), `artifact_sha256` (`None` for source packs), `synthetic`, `verified`, `engine_min` (G12, from `pack.manifest.engine_min`, the minimum engine version the pack requires).

## Pack format

A pack is a directory with a manifest and CSV tables. `agri-core pack build` compiles it into a verified SQLite file plus a manifest that records hashes. `docs/PACK_FORMAT.md` is the reference for the format as it stands today, including the built-pack SQLite section.

```
<pack>/
├─ advisories.csv         # critical corrections keyed by fact_id
├─ datasets.csv           # reference tables (fertilizer products, media, soil tests) with scope and license
├─ facts/                 # one CSV per taxon: facts/<taxon_id>.csv
│                        #   one row per fact: fact_id, taxon_id, parameter, phase, value, scope, src, evidence, status
├─ hazards.csv            # hazard flags per taxon or scope
├─ names.csv              # aliases per taxon: taxon_id, name, language, kind
├─ pack.toml              # manifest: name, version, schema_version, engine_min,
│                        #   dictionary_min, synthetic, content_hash
├─ sources.csv            # one row per source: id, url, license, commercial_use, access_date, citation
└─ taxa.csv               # one row per taxon: taxon_id, rank, scientific_name, parent_id
```

`pack.toml`:

```toml
name = "agri-knowledge"
version = "0.1.0"
schema_version = 1
engine_min = "0.1.2"
dictionary_min = "1.0.0"
synthetic = false
# Regenerate with `agri-core pack lock --pack PATH`. sha256 of the pack's
# canonical content; see docs/PACK_FORMAT.md for the algorithm.
content_hash = "sha256:..."
```

### Facts

Each fact is one value at one scope. The engine resolves facts deterministically: filter by status (with a `reviewed` safety floor for safety-critical parameters), match `applies_to`, validate phase, exclude superseded facts, match scope by union semantics, then order by specificity (`len(scope)`), status, review date and `fact_id`. Conflicts between alternatives raise a `fact_conflict` warning and are returned as `alternatives`. No matching fact gives `unknown(code="no_match")`.

| Field | Meaning |
|---|---|
| `fact_id` | Stable identifier; never reused. Superseded facts are kept with `superseded_by`. |
| `taxon_id` | Opaque ID created by `agri-core scaffold` (M6); scientific names may change without changing the ID. |
| `parameter` | A core parameter from `parameters.core.yaml` or an extension parameter declared in the pack. |
| `phase` | A phase from `phases_by_archetype`. |
| `value` | One of eight shapes: `trapezoid`, `range`, `scalar`, `enum`, `enum_set`, `bool`, `rule`, `unknown`. |
| `scope` | Country, region, elevation range, growing system, variety, season, use. Empty keys are wildcards; filled keys must cover the caller's context. |
| `src` | Source IDs, each defined in `sources.csv`. |
| `evidence` | `A` (guideline or peer-reviewed) to `D` (anecdotal). |
| `status` | `imported`, `draft`, `reviewed` or `approved`. Calculators only see facts at or above the caller's minimum. |

### Statuses and tiers

- **Statuses** move from `imported` (bulk import from a licensed dataset) to `draft` (entered, not yet checked) to `reviewed` (matched to its citation by a maintainer) to `approved` (signed off by a domain expert).
- **Tiers are derived, not declared.** `agri-core coverage` computes them (see `docs/decisions/ADR-003-tiers-license-duplicates.md`):
  - **T0** identity only (name, rank, parent); no live facts.
  - **T1** at least one live fact at any status (`imported`, `draft`, `reviewed`, `approved`).
  - **T2** every `tier_required` parameter that matches the taxon's `applies_to` (organism group, archetype, uses) has a live fact at status ≥ `reviewed`, or `value.shape == unknown` with status ≥ `reviewed`. Phase-bearing parameters require all their phases; `applies_to.systems` parameters are excluded from tier (they appear in `TierResult.system_gaps`). Weakest-link per fact.
  - **T3** T2 + every `tier_required` parameter is `approved` + every safety-critical fact is `approved` with ≥2 distinct reviewers in `reviewed_by`.

### Safety-critical parameters

Parameters with a `safety_class` other than `none` are safety-critical in the dictionary. The classes are:

| Class | Meaning |
|---|---|
| `dose_cap` | Functional upper bound on the recommendable amount per application. Prevents overdose without classifying the hazard type. |
| `toxicity_limit` | Threshold above which a hazard harms humans, animals or the environment. |
| `regulatory` | Flag or limit mandated by a specific jurisdiction. |

Safety-critical parameters may never be `draft` or `imported`; `approved` requires two independent reviews. `resolve_fact` raises the minimum status floor to `reviewed` for safety-critical parameters and records the elevation as a `safety_min_status_raised` warning. The resulting `FactResolved` carries `min_status_applied: FactStatus` (G5) — the **effective** floor after the default (`approved`) and any safety-floor adjustment — so callers do not have to recompute it. Salinity (`soil_ec`, `water_ec_max`) is a tolerance condition for the plant, not an applied amount and not a hazard to humans, animals or the environment; it stays `safety_class: none`.

### Pack security

- The engine verifies the pack hash on load.
- SQLite is opened read-only and immutable, with `trusted_schema=OFF`. A TOCTOU guard raises `PackStaleArtifactError` (`PACK_STALE_ARTIFACT`) if the built artifact changed on disk after load.
- YAML, if used for overlays, is read with `safe_load` only.
- Pack size is bounded.
- A pack from an untrusted source is not loaded without a pinned hash.

## Dictionary

The core dictionary (`dictionary/parameters.core.yaml`) defines, for every parameter the engine consumes:

- `key`, `stage`, `shape` (one of the eight fact-value shapes), `unit`
- `physical_range` (physical sanity bound, not an agronomic judgement)
- `phase_set` (one of `none`, `biological`, `kc`) and optional `allowed_phases`
- `applies_to` (organism groups, archetypes, uses, systems, traits; AND between dimensions, OR within, omitted dimension means unlimited)
- `scope_keys` (which keys may appear in a fact's scope)
- `used_by` (which modules read the parameter) and `tier_required`
- `safety_class` and, when not `none`, a `rationale`
- `kind` (`core` or `extension`)
- `introduced_in` (SemVer of the dictionary release that first added the key)

The vocabulary files under `dictionary/vocab/` are the closed sets a pack may reference: `archetypes`, `phases_by_archetype`, `phase_sets`, `stages`, `systems`, `environments`, `uses`, `traits`, `organism_groups`, `climate_zones`, `growth_habits`, `establishment_states`, `yield_targets`, `scope_keys`, `modules` and `safety_classes`.

### Archetypes

Eight archetypes carry default biological phases: `annual`, `aquatic`, `biennial`, `epiphyte`, `fungal`, `geophyte`, `herbaceous_perennial`, `woody_perennial`.

Five more are present in the vocabulary without default phases and gain phases when a taxon and a calculator first need them: `algae`, `bryophyte`, `gymnosperm`, `lichen`, `pteridophyte`.

### Dictionary lock

- `dictionary/dictionary.lock` is an append-only log, one line per release: `<version> <contract_hash>`, sorted by SemVer. The last line is the running version.
- `contract_hash` is the SHA-256 of canonical JSON (sorted keys, no whitespace, `-0.0` normalized per RFC 8785) of `{parameters, vocab, units}`. The version string is not part of the hash; the `(version, hash)` pair is verified separately.
- `dictionary/history/<version>.json` is a frozen snapshot of `{version, parameters, vocab, units}` per release. Older snapshots are never edited; changing a released dictionary requires a new version and a new snapshot.
- `classify_change(old, new)` returns the required SemVer bump from a bundle diff. It is fail-closed: any change not explicitly classified as `PATCH` or a known `MINOR` pattern returns `MAJOR`. `MINOR` covers added keys and widened `applies_to` / `scope_keys` / `allowed_phases` / `physical_range` / vocabularies / custom units. `PATCH` is limited to `description` and `rationale` changes.

Adding a **core** parameter is a minor engine release. Adding an **extension** parameter is a pack change, validated by the engine, with no engine release.

## Taxa and identifiers

- Taxon IDs are created by `agri-core scaffold` (M6) and are opaque (Crockford base32 with a `T` prefix, ten characters). They are never reused.
- Scientific names may change without changing the ID.
- `rank` is one of `cultivar_group`, `genus`, `hybrid`, `species`.
- `parent_id` is for navigation only; it does not imply inheritance of facts. Values never flow from parent to child automatically.

## Coverage

**Data release plan.** The first data release, `agri-knowledge` `v0.1.0` (planned after its milestone K5), carries tomato and rice at tier T2 for Indonesia and one more country, a T0 taxonomic backbone with multilingual names for the priority list, and legal flags. After that, `agri-knowledge` adds one group per iteration (fruit, fodder, ornamentals, then rare plants), each starting with a source audit.

**Design targets for the engine.** Six reference profiles across five archetypes are chosen to exercise every irrigation mode, the propagation planner and the suitability refusal path. They arrive in `agri-knowledge` as their groups come up; until then the tests use the synthetic sample pack.

| Profile | Archetype | Notes |
|---|---|---|
| Rice | annual | `paddy_awd` irrigation mode |
| Tomato | annual | `field_etc` irrigation mode |
| Mango | woody_perennial | Propagation: air layering, budding |
| Vanilla | epiphyte | `container_band` irrigation; propagation: stem cuttings |
| Genlisea | herbaceous_perennial | `container_band` irrigation; ornamental carnivorous |
| Black truffle | fungal | Suitability profile. Expected `unsuitable` at warm, low-elevation tropical sites, so it tests that the library can say no |

The propagation planner returns the `not_applicable` outcome for rice, tomato and black truffle.

**Protected species are excluded.** Taxa listed in the Appendices to CITES (any appendix) or protected under national regulations such as Permen LHK 106/2018 (Indonesia) are not included in the sample pack or in the initial `agri-knowledge` release unless a documented lawful cultivation pathway exists (for example, an artificial-propagation exemption, or data on commercially cultivated varieties rather than wild-type material). The policy is described in [Protected species](#protected-species). Per-taxon decisions are recorded in `docs/design/plant_wishlist_v4_rationale.md` and `docs/design/plant_wishlist_v4_migration.md`, citing legal instruments only.

Planned next: maize, chili pepper, broccoli, potato, lettuce, grape, apple, watermelon, melon, blueberry, lychee, wasabi and bonsai (per species, with a technique module for pruning, wiring and repotting). Carnivorous plants are split by genus; the wishlist covers Genlisea, Byblis, Drosophyllum, Drosera, Pinguicula, Utricularia and Roridula.

**International by design.** Profiles are not tied to a country. Each value declares its scope (elevation, variety, growing system) and its source, so the same crop can carry different values for different conditions. Crop names carry aliases in several languages, and new aliases are welcome. Region-specific material, such as soil-test interpretation tables, is tagged with the region and method it applies to.

## Exports (M16)

- `bundle.json`: all profiles, the sources table (including license, `commercial_use` and attribution text) and metadata in one versioned file.
- `tool_schemas.json`: function-calling schemas for LLM agents, generated from the same Pydantic models as the library so tools and code cannot drift apart.
- `edge_thresholds.json`: compact thresholds for gateways and devices that must keep working offline.
- `review_sheet.csv`: one row per value, so domain experts can review in a spreadsheet without using GitHub.

Every export carries the license and the attribution text of the sources behind its values.

## Safety and limitations

- **Reference data, not advice.** Values may be incomplete, out of date, or wrong for your site, variety, climate, soil, water or growing system. Check with a local agronomist or extension service before acting.
- **Local rules and labels come first.** Rules on fertilizers, water use and plant protection differ between countries and regions. This library does not encode them.
- **Pesticides are out of scope.** Follow the product label and local regulations.
- **Caps are a backstop.** Per-application fertilizer caps are conservative upper bounds. They do not replace regional nutrient-management rules. Check the `capped` field.
- **Status matters.** Use `approved` facts for decisions affecting real crops. Use `reviewed` facts only in development and pilots with human oversight. Never use `draft` or `imported` facts for decisions.
- **Inputs decide quality.** The library checks types and units, but it cannot detect a faulty sensor, a wrong measurement or a biased weather series. Estimated inputs are reported as assumptions, and gaps in a series are refused rather than filled.
- **No automatic actuation.** Do not connect outputs directly to pumps, valves or dosing units without independent interlocks (limits, timeouts, manual override) and human approval.
- **`unknown`, `not_applicable`, `ambiguous` and `unsuitable` are real answers.** Do not work around them.
- **No warranty.** See [License](#license).

## Data and provenance

The engine enforces provenance; the data lives in [`agri-knowledge`](https://github.com/WoodinGlass/agri-knowledge), released under CC BY 4.0.

- Every fact is an individual value (a number, a range or a rule) written in our own words and structure, with a citation.
- Passages, tables and figures are not copied from sources, and third-party datasets are not bulk-imported. A dataset is imported only when its license is on the accepted list in the [Licensing policy](#licensing-policy) and the license gate passes.
- `sources.csv` has one row per source: ID, URL, license, `commercial_use`, access date and citation details.
- Golden tests use vectors we derive ourselves: a hand derivation from the published equations, or the output of an independent, permissively licensed implementation whose name and version are recorded next to the vectors. Worked examples, tables and figures are not copied from standards or handbooks.
- Equations are implemented from the primary literature and referenced in the documentation. A method name such as "Penman–Monteith" or "Hargreaves–Samani" identifies a published method; it does not mean that text, tables or figures of a handbook are included. Code is not copied from copyleft-licensed or unlicensed implementations.
- Weather series, climate grids and satellite data are supplied by the caller. The engine implements published formulas and ships no such datasets; the license of a dataset is checked where the dataset enters (for a pack, in `sources.csv`).
- Reviewers are identified by ID; names appear only with consent. Packs and exports contain no personal data.
- Organizations and publications are named only to identify sources. There is no affiliation or endorsement.

### Licensing policy

Everything this project ships can be used commercially.

- **Rule.** A source is accepted only if its license lets anyone use, modify and redistribute the values commercially, with attribution at most.
- **Accepted.** CC0 1.0 and other public-domain dedications; works that are in the public domain under the law that applies to them (recorded in `sources.csv` with a citation that starts with `basis:`); CC BY 3.0 and 4.0; MIT, BSD and Apache-2.0 for values taken from software.
- **Rejected.** Any NonCommercial, ShareAlike or NoDerivatives variant of a Creative Commons license; ODbL and GPL-family licenses; "free for research or non-commercial use" terms; "all rights reserved" material without a written permission on file; sources with no stated license.
- **Terms of use count.** Website, database and API terms bind users even when individual facts are not protected by copyright. A source whose terms restrict commercial use is rejected, even if the same value could be found elsewhere. At the time of writing this includes the IUCN Red List and the Species+/CITES Checklist database, whose terms require written permission for commercial use, the WorldClim climate grids (non-commercial use; redistribution and commercial use need permission) and the HadEX2 climate-extremes dataset (conditions on commercial use). Terms change, so a source's license is re-read and its check date recorded.
- **`commercial_use`** records a maintainer's reading of a source's license: `yes`, `no` or `unclear`. A pack can be released only when every source is `yes`. `agri-core validate --strict` rejects `no` and `unclear`, and `unclear` counts as `no` until a maintainer resolves it. It is a record of a review, not legal advice or a guarantee.
- **License gate.** `agri-core validate --strict` also rejects any license outside the accepted list, and `agri-core lint-sources` fails when `commercial_use` and `license` contradict each other.
- **Attribution.** Packs and exports carry each source's license and the attribution text it requires.

### Climate parameter catalog

The catalog (`docs/design/climate_catalog_v1.csv`, with its rationale in `docs/design/climate_catalog_v1_rationale.md`) is the single list of climate parameters that the engine computes, expects as input, or reads from a pack. `docs/CLIMATE_CATALOG.md` is generated from it and is never edited by hand. A parameter enters the catalog before any code is written for it.

- **Kinds.** `computed`: the engine implements the method. `input`: the caller supplies the value and the engine checks unit and range. `pack_value`: a crop- or region-specific number (a base temperature, a threshold, a stage length) that lives in an `agri-knowledge` pack and never in code.
- **Statuses.** `planned`, `implemented`, `backlog` (considered, not scheduled) and `excluded` (will not be added; the reason is recorded).
- **Columns.** `param_id`, `group`, `kind`, `unit`, `method_ref`, `owner_repo`, `commercial_use`, `safety_tier` (`low` or `high`), `status`, `milestone`, `test_id`, `checked_on` and `reason`.
- **Gate.** `agri-core lint-catalog` fails when a `planned` or `implemented` row has a `commercial_use` other than `yes`, when a row with a `high` safety tier is not `excluded`, or when an `implemented` `computed` row has no `method_ref` or no `test_id` (a `planned` `computed` row may carry `TBD` until it is implemented). `checked_on` records when a license was last read, because terms change. `agri-core validate` also rejects an extension parameter in a pack that matches an `excluded` row, in the way the plant-protection guard of [ADR-007](docs/decisions/ADR-007-plant-protection-scope.md) rejects chemical-control tokens.
- **Link to `agri-knowledge`.** A `pack_value` row names the dictionary key that carries its value. Adding that key is a dictionary change here; supplying values is a data change there. A new pack-supplied parameter starts with `tier_required: false`, so existing tiers do not drop; making it required later changes derived tiers and needs a coordinated release of both repositories. Without a pack value the answer is `unknown` or `insufficient_input`; the engine never falls back to a built-in number.
- **Plant-protection boundary.** Leaf wetness and similar microclimate variables are inputs only. The engine does not turn them into disease or pest risk (see [ADR-007](docs/decisions/ADR-007-plant-protection-scope.md)).
- **Excluded by design.** Ultraviolet dosing and UV-C use, lamp and light-spectrum recipes, laboratory plant-response measurements, and anything with a high safety or legal risk.

### Protected species

- A taxon listed in the Appendices to CITES (any appendix) or protected under a national regulation such as Permen LHK 106/2018 (Indonesia) is not included in the sample pack or in the initial `agri-knowledge` release unless a documented lawful cultivation pathway exists.
- Acceptable pathways include: artificial propagation explicitly exempted by the source instrument, or data on commercially cultivated varieties rather than wild-type material.
- Decisions cite legal instruments (the text of the Appendices, national regulations). They do not copy data from restricted databases, and the IUCN Red List is not used as an input because its terms restrict commercial use. Maintainers may still decline a taxon on conservation grounds; the reasoning is recorded without importing data from restricted databases.
- Facts about a protected taxon recorded by a third party must cite their source and state the legal status; they are not added to `agri-knowledge` without the maintainer confirming the pathway.
- The detailed policy, the list of excluded taxa and the replacements are recorded in `docs/design/plant_wishlist_v4_rationale.md`.
- This is a design choice, not a legal opinion. Users redistributing data for commercial purposes should verify CITES and national rules for each species independently.

## Contributing

Contributions are welcome. Data contributions go to [`agri-knowledge`](https://github.com/WoodinGlass/agri-knowledge); code contributions go here. Every data contribution must meet the [Licensing policy](#licensing-policy). Proposals for new climate parameters start as a row in the [climate parameter catalog](#climate-parameter-catalog); the license and safety gate decides whether a row can be accepted.

See [`CONTRIBUTING.md`](CONTRIBUTING.md) for the full rules, contribution scope, evidence requirements, licensing terms, protected-species policy, and the code owners list.

## Security

Code scanning uses [CodeQL default setup](https://docs.github.com/en/code-security/code-scanning/introduction-to-code-scanning/about-code-scanning-with-codeql):
GitHub-hosted CodeQL analysis runs against the repository's
default branch and pull requests. The retired
`github/codeql-action` workflow-file approach is not used.

Dependency review runs on every pull request via
`actions/dependency-review-action` (SHA-pinned in
`.github/workflows/dependency-review.yml`).

- **Vulnerabilities** in code or dependencies: report them privately via GitHub's private vulnerability reporting (Security tab, "Report a vulnerability"), not as a public issue.
- **Harmful data errors** (an unsafe cap, a wrong unit, a threshold off by an order of magnitude): report to [`agri-knowledge`](https://github.com/WoodinGlass/agri-knowledge) with a citation and the `fact_id`. For immediate risk, report privately as above.
- The library makes no network calls; pack loading verifies hashes and opens SQLite read-only with `trusted_schema=OFF`; YAML is read with `safe_load` only.

See [`SECURITY.md`](SECURITY.md) for the full policy, supported versions, scope and security guarantees.

## Verifying a release

Every release artifact is attested with
[GitHub Artifact Attestations](https://docs.github.com/en/actions/security-for-github-actions/using-artifact-attestations),
which records the workflow that built it and the commit it came from.
Verify with the GitHub CLI:

```bash
gh attestation verify agri_agronomy_core-X.Y.Z-py3-none-any.whl \
  --repo WoodinGlass/agri-agronomy-core
gh attestation verify agri_agronomy_core-X.Y.Z.tar.gz \
  --repo WoodinGlass/agri-agronomy-core
gh attestation verify sample_pack.zip \
  --repo WoodinGlass/agri-agronomy-core
```

Every release also ships an SBOM (`sbom.cdx.json`), CycloneDX 1.6
JSON. It lists the wheel's **runtime** dependencies, built from an
isolated virtual environment, not the engine's development tooling.
Verify it with the same mechanism:

```bash
gh attestation verify sbom.cdx.json \
  --repo WoodinGlass/agri-agronomy-core
```

Also verify the release `SHA256SUMS`. GitHub flattens release
asset names to their basenames, so check with `--ignore-missing`
if you only downloaded some assets:

```bash
sha256sum --check --ignore-missing SHA256SUMS
```

The pack hash (``content_hash`` in ``pack.toml``) is verified by
``agri-core`` on load; the engine refuses to run a pack whose hash
does not match.

## Versioning and releases

- Semantic Versioning applies to the engine and to public contracts: `Outcome` and its members, the JSON Schemas, the dictionary and the exported tool schemas. `RESOLUTION_POLICY_VERSION` (currently `1.4.0`) follows its own SemVer — MAJOR for a semantic change to an existing decision, MINOR for an additive rule or field, PATCH for clarity. See ADR-004 §"resolution policy version".
- During the 0.x line a **minor** release may break a public contract; when it does, the breaking change is called out under a `### Changed` (or `### Removed`) heading in `CHANGELOG.md`. A major version is reserved for the point at which the contract is considered stable.
- Every pack carries a `schema_version` and an `engine_min`. The engine supports two consecutive `schema_version` values and ships `agri-core pack migrate` to move a pack forward. A pack that declares a `schema_version` the engine does not support is rejected; a pack that requires a newer engine than the one running is rejected.
- Every fact has a stable `fact_id`. A superseded fact is marked with `superseded_by`; a critical correction will be published as an advisory in the pack (planned; the loader currently rejects non-empty `advisories.csv`). See ADR-004 G3 for the advisory contract that fires when loading ships.
- Every release pins the `agri-knowledge` version it was tested against. A canary CI job against `agri-knowledge` `main`, to surface incompatibilities early, is **planned for v0.2.0** (not yet implemented).
- **Order of changes across the two repositories.** A change that needs a new core parameter or a new method lands in this order: the catalog row and the dictionary change here (an engine minor release), then the data in `agri-knowledge`, validated against that engine release, then a new pack release (Semantic Versioning; MAJOR only when `schema_version` or the pack format changes) that declares the `engine_min` and `dictionary_min` it needs. The `agri-knowledge` CI runs the same `agri-core validate --strict` that this repository ships.
- `dictionary/dictionary.lock` records `<version> <contract_hash>` per dictionary release; the SemVer rule is that adding a key is `MINOR`, removing / renaming / changing shape, unit, phase_set, enum values or narrowing a dimension is `MAJOR`, and description / rationale changes are `PATCH`. `classify_change` enforces this and is exercised by the test suite.
- Releases are git tags and GitHub Releases (wheel, sdist, sample pack, `SHA256SUMS`, CycloneDX SBOM, and — when the pinned `agri-knowledge` version has shipped — the built packs of `agri-knowledge`). v0.1.x is not on PyPI; v0.2.0 and later are published to PyPI via `.github/workflows/publish.yml` (Trusted Publishing).

## Citing

If you use the engine in research or in a product, please cite this repository with the release tag you used. If you rely on specific facts, please also cite the original sources recorded in the pack's `sources.csv`. Citation is a request, not a condition of the license.

A machine-readable citation is available in [`CITATION.cff`](CITATION.cff); GitHub's "Cite this repository" button reads it directly.

### Decision records

Architectural decisions are recorded as ADRs under
[`docs/decisions/`](docs/decisions/):

- [ADR-001](docs/decisions/ADR-001-knowledge-set.md) — `KnowledgeSet` as a `Protocol`; the loader returns an immutable implementation.
- [ADR-002](docs/decisions/ADR-002-build-and-hash.md) — Two-hash model and deterministic SQLite build.
- [ADR-003](docs/decisions/ADR-003-tiers-license-duplicates.md) — Tier derivation (T0–T3), license gate, and duplicate-fact detection.
- [ADR-004](docs/decisions/ADR-004-resolution-policy.md) — Taxon and fact resolution policy (`ok`, `unknown`, `ambiguous`, ...). Includes the M8 review follow-up series G2–G13 (semantic locks for `superseded_by`, advisories, specificity, status policy, unknown precedence, no-fuzzy policy, filter counts, input length guard).
- [ADR-005](docs/decisions/ADR-005-license-allowlist.md) — Default-deny license allowlist. Supersedes the license-gate section of ADR-003.
- [ADR-006](docs/decisions/ADR-006-categorical-outcome.md) — `CategoricalResult` (`status="ok_category"`) for non-numeric answers.
- [ADR-007](docs/decisions/ADR-007-plant-protection-scope.md) — Plant-protection scope and two-tier guard; data model deferred to ADR-008.
- [ADR-009](docs/decisions/ADR-009-result-envelope.md) — Envelope on every `Outcome`: `subject` and deterministic `request_id`.
- [ADR-010](docs/decisions/ADR-010-perf-budgets.md) — CLI performance budgets for `pack build`, `validate`, `coverage`, `diff`.
- [ADR-011](docs/decisions/ADR-011-id-ledger.md) — Append-only taxon ID ledger (`ids.lock`).
- [ADR-012](docs/decisions/ADR-012-climate-catalog.md) — Climate parameter catalog and contract (`lint-catalog`, generated document, shipped excluded list, extension-parameter guard).
- [ADR-013](docs/decisions/ADR-013-thermal-indices.md) — Thermal time, generic climate index engine, and bioclimatic variables (GDD methods 1 and 2, chilling, photothermal units, 13-index registry, Nix 1986 subset).

ADR-008 is intentionally reserved (plant-protection data model, after M15) and
will be written as its own ADR when that work starts.

## Milestones

| Milestone | Status | Scope | Done when |
|---|---|---|---|
| **M0** Foundation | Done | Repository, `pyproject.toml`, CI, pre-commit, `Outcome` and `Result` models, JSON Schemas, `sources.csv` linter, wheel smoke test. | CI is green on the empty but valid package, and a clean-venv install of the wheel passes `agri-core validate --pack sample`. |
| **M1** Data split | Done | Remove `profiles/` and `LICENSE-DATA`; the engine keeps schemas, dictionary and sample pack. | `pip install git+...` loads from a clean env without the `profiles/` folder; README reflects the split. |
| **M2** Contract models | Done | `Outcome` (8 members: 7 statuses + `ok_category` from ADR-006), `Result`, row models (`taxon`, `name`, `fact`, `hazard`, `dataset`, `source`), identifier primitives (Crockford base32), `ParameterDef` v1.0.0, `PhaseSet`, `ScopeKey`. | Drift tests, frozen / extra-forbid invariants, and identifier pattern tests pass. |
| **M3** Row JSON schemas | Done | JSON schemas for the 6 row models and the 8-shape `FactValue` union, generated from the Pydantic models. | Drift tests green; `EnumSetValue` in `FactValue` tested; `$defs` checked. |
| **M4** Core dictionary 1.0.0 | Done | 31 parameters at `dictionary_version: 1.0.0`, `dictionary.lock` (append-only), `history/1.0.0.json`, `classify_change` for SemVer, safety-class taxonomy. | Lock hash verified against the running dictionary; `introduced_in` matches first snapshot; `test_semver_compat` infrastructure ready. |
| **M5** Loader and sample pack | Done | `compute_pack_hash` / `verify_pack_hash`; `load_knowledge_set(path)`; immutable `KnowledgeSet`; sample pack with 8 synthetic taxa, one per initial archetype (`annual`, `aquatic`, `biennial`, `epiphyte`, `fungal`, `geophyte`, `herbaceous_perennial`, `woody_perennial`), without real agronomic data. | Hash determinism and mismatch tests pass; sample pack loads cleanly; foreign keys on `taxon_id`, `parameter`, `src` verified. |
| **M6** Build | Done | `scaffold` (opaque taxon IDs, never reused) plus `build` (CSV → SQLite + manifest, reproducible). | Wheel and pack build reproducibly (identical SHA-256 twice). |
| **M7** Validate, diff, coverage, license gate | Done | Trapezoid order, scope validity, unit resolution, duplicate detection, tier derivation (T0–T3), `diff` report, `coverage`, license gate. | Sample pack passes validate with 0 errors; `diff` matches fixtures; coverage assigns tiers; license gate rejects NC + `commercial_use=yes`. |
| **M8** `resolve_taxon` and `resolve_fact` | Done | Deterministic resolution per the fixed policy (ADR-004); `meta()`; `show` CLI with three modes (`--name`, `--taxon`, `--fact`). **M8 review follow-up (G1–G14)**: semantic locks in ADR-004 (superseded, advisories, specificity, status policy, unknown precedence, no-fuzzy, filter counts, input length guard), `RESOLUTION_POLICY_VERSION` 1.0.0 → 1.4.0, `Unknown.filter_counts` + `Unknown.warnings` + refined refusal codes, `FactResolved.min_status_applied`, `MetaInfo.engine_min`, `resolve_taxon` length guard (200 chars), Hypothesis fuzz, cross-process determinism, multi-scale perf test (1k/10k/100k). | `resolve_taxon` p95 ≤ 5 ms on a 10k-taxa pack (measured ≈ 12 µs); **1483 tests collected** across markers (619 unit, 842 contract, 5 property, 2 scenario, 15 perf); resolution contract tests pass; `show` CLI usable. |
| **M9** Offline, performance, docs, tag `v0.1.0` | Done | Socket-blocking pytest plugin (`pytest-socket`, `--disable-socket`, `offline-wheel` CI job under `unshare -n`); performance budget tests for pack load and peak memory (batch suitability deferred to M15); the `docs/` skeleton (`DICTIONARY` generated, `RESOLUTION_POLICY`, `SAFETY`, `ADDING_A_TAXON` executed by test); Windows smoke job; release workflow; tag `v0.1.0`. | Every test passes with network blocked; performance budget met; Windows `windows-smoke` green; `release.yml` dry-run green; tag `v0.1.0`. |
| **M10** Climate catalog and contract | Done | The climate parameter catalog in `docs/design/climate_catalog_v1.csv` with its rationale; `docs/CLIMATE_CATALOG.md` generated from it; `agri-core lint-catalog` (license, safety, method-reference and test-reference checks); a stable `param_id` per parameter, mapped to a dictionary key for every pack-supplied value; a generated list of excluded parameters shipped with the package and used by `validate` to reject matching extension parameters. | `lint-catalog` passes on the catalog; the generated document and the shipped excluded list are current (a drift test fails when either is stale); `validate` rejects an extension parameter that matches an excluded row; contract tests pass; every `backlog` and `excluded` row records its reason. |
| **M11** Atmosphere, radiation and ET0 | Done | VPD, dew point, wet-bulb temperature, daylength and photoperiod, solar and net radiation, PAR, PPFD and DLI, wind conversions and height adjustment, temperature and pressure from elevation, ET0 (Penman–Monteith with a Hargreaves–Samani fallback). Methods documented with primary-literature references. | Golden tests (independently derived vectors) pass; every estimated input is reported as an assumption; each `implemented` catalog row has a method reference and a test. |
| **M12** Thermal time and climate indices | Done | GDD with documented methods, chilling, photothermal units, the generic index engine with its documented registry, bioclimatic variables from monthly values, 10-day and monthly aggregation. | Golden tests pass; a gap in a series gives `insufficient_input`; every registry entry has a reference and a test. |
| **M13** Thresholds and stages | Not started | Four-point trapezoid threshold checks and the stage resolver (planting age, GDD or photothermal units). Perennials are driven by caller-supplied events. | Phases resolve per archetype; perennials use caller-supplied events; threshold and stage values are read from the pack only. |
| **M14** Irrigation, fertilizer, media and water | Not started | Registry of irrigation modes (`container_band`, `field_etc`, `paddy_awd`), ETc from a stage-wise Kc curve (Kc values from the pack only), nutrient-to-product conversion with safety caps, growing-media recipes, water-quality limits and indices (SAR, RSC). | The M14 release passes against the sample pack and against the pinned `agri-knowledge` version; irrigation results match scenario fixtures. |
| **M15** Suitability and propagation | Not started | Single and batch site suitability, per-factor reasons, hazard flags, dated propagation plans. | Batch mode within the performance budget; scenario tests including an `unsuitable` case. |
| **M16** Exports and documentation | Not started | `tool_schemas.json`, `edge_thresholds.json` per site, `review_sheet.csv` per tier, quickstart notebook, `docs/`. | A release tag includes exports, generated from the same Pydantic models as the library, with a stable contract test. |
| **M17** Soil water balance | Not started | Pedotransfer estimates of field capacity, wilting point and available water; a daily soil-water balance with depletion and a water-stress coefficient (Ks) feeding the `field_etc` mode. | Golden tests pass; depletion fractions and other crop values are read from the pack only; a missing value gives `unknown` or `insufficient_input`. |
| **M18** Drought and season indices | Not started | SPI with a minimum-record check, an aridity index (precipitation over ET0), rainy-season onset and cessation from a registry of documented, configurable definitions. | Golden tests pass; a record shorter than the documented minimum gives `insufficient_input`; every definition in the registry carries a reference. |
| **M19** Vegetation-index band math | Not started | NDVI, EVI, SAVI, GNDVI, NDRE, NGRDI and PSRI from caller-supplied reflectance, with `ndwi_mcfeeters` and `ndmi` kept apart by name. No raster I/O and no imagery in this repository. | Golden tests pass; each index documents its bands and coefficients; LAI, FAPAR and canopy cover remain inputs. |

Milestones are plain integers. M17–M19 are additive modules that follow the exports milestone. Considered and deliberately not scheduled: hydrogeology (water table, baseflow, recharge), soil-erosion models, air-quality indices, non-PAR light spectra, satellite phenology and crop-growth rates. Each will be recorded with its reason in the climate catalog (M10).

## Development

```bash
git clone https://github.com/WoodinGlass/agri-agronomy-core.git
cd agri-agronomy-core
pip install -e ".[dev]"
pre-commit install

ruff check . && ruff format --check .
mypy
pytest
agri-core validate --pack sample
agri-core lint-sources --pack sample
```

Tooling: pytest, Hypothesis, pytest-cov, ruff, mypy (strict), nbmake, nbstripout, pre-commit, pip-audit, and pytest-socket. The full suite runs with network access blocked (`--disable-socket`). A `windows-smoke` CI job runs the non-perf suite on `windows-latest`, Python 3.11.

**Test kinds**

- `contract`: `Outcome`, dictionary, exported tool schemas and JSON Schemas stay stable. Includes the M8 resolution contract tests (`tests/contract/test_resolve_taxon.py`, `test_resolve_fact.py`, `test_resolution_schemas.py`, `test_unknown_code_registry.py`), the M8 review follow-up tests (`test_resolve_determinism.py`, `test_meta.py`, `test_resolution_policy_version.py`), and the M10 catalog tests (`test_climate_catalog.py`, `test_catalog_lint.py`, `test_catalog_drift.py`, `test_catalog_three_way.py`, `test_catalog_validate_integration.py`).
- `golden`: independently derived vectors (a hand derivation from the published equations, or the output of a permissively licensed implementation with its name and version recorded). First golden tests shipped with M11 (atmosphere, radiation and ET0; see `tests/contract/test_climate_golden*.py`). Independent vectors that predate the marker live in `tests/contract/test_pack_hash.py` (KAT) and `test_toml_writer.py`.
- `offline`: **not a per-test marker**. Network is blocked globally by `pytest-socket` via `--disable-socket` in `pyproject.toml` `addopts`; the entire suite runs with network disabled, and a `offline-wheel` CI job runs `agri-core validate --pack sample` under `unshare -n`.
- `perf`: 10 files / 15 tests. `resolve_taxon` (M8), built-pack load + peak memory (v0.1.0), CLI budgets for `build`/`validate`/`coverage`/`diff` (ADR-010), `coverage` scaling (ADR-003), `resolve_fact` + coverage guard (G7), multi-scale 1k/10k/100k (G14). Run with `--no-cov` (perf tests skip themselves when coverage is active — see `tests/perf/conftest.py`); exclude with `-m 'not perf'` on slow runners.
- `property`: Hypothesis checks such as unit round-trips, no negative amounts, monotonic behavior with area, and (from G11) fuzz for `resolve_taxon` input.
- `scenario`: end-to-end expectations, for example a taxon whose every suitability factor is `unsuitable` in the requested scope must return `unsuitable`.
- `unit`: functions in isolation.

**Test counts (v0.1.2 + M8 review follow-up + M10 + M11 + M12)**

- Total: **1832** tests collected by `pytest --collect-only`.
- By marker: 776 `unit`, 990 `contract`, 5 `property`, 2 `scenario`, 15 `perf`, 44 `golden`, 0 `offline`-marked (global via pytest-socket).
- Expected skips: 2 (dictionary-lock SemVer — needs ≥2 snapshots; files chmod — skipped as root).
- Expected xfail: 1 (G4 specificity marker — `test_incomparable_scope_arbitrary_tiebreak_documented`, fires when M9+ implements the partial order).

**Release gates (every release)**

- ruff and mypy (strict) are clean.
- Coverage is at least 90%, and 100% for `safety/`.
- CI is green on Python 3.11, 3.12, 3.13 and 3.14; `pip-audit` runs in CI.
- Runtime dependencies use permissive licenses (checked in CI).
- `agri-core validate --strict` passes on the sample pack, including the license gate.
- `agri-core lint-catalog` passes on the climate catalog (from M10).
- `dictionary.lock` matches the running dictionary (`contract_hash` verified).
- The pack and the wheel are reproducible: identical SHA-256 when built twice from the same inputs.
- `CHANGELOG.md` is updated.
- The GitHub Release contains the wheel, the sdist, the sample pack and `SHA256SUMS`; the built packs of `agri-knowledge` at the pinned version are attached when that version has shipped.

**Additional release gates from `v0.1.0`**

- Every test runs with network access blocked.
- The performance budget is met (see [Performance](#performance)).
- A `windows-smoke` job runs on `windows-latest` in parallel with the Python 3.11–3.14 matrix on Ubuntu.

**Additional release gates from `v0.2.0`**

- Notebooks execute (nbmake) and are committed without outputs (nbstripout).

## Performance

These targets are measured in CI and in Colab at v0.1.0 (unchanged in the v0.1.1 and v0.1.2 patches) on a synthetic pack (10k taxa, 30k names, 200k facts). They will be recalibrated once real `agri-knowledge` pack sizes are known. **Since v0.1.2**, the M8 review follow-up added `test_resolve_fact_perf.py` (G7) and `test_resolve_scaling.py` (G14, 1k/10k/100k) to `tests/perf/`.

CLI-level budgets (`build`, `validate`, `coverage`, `diff`) were
calibrated at v0.1.2 on Colab with a 1.5x margin; see
[ADR-010](docs/decisions/ADR-010-perf-budgets.md). They will be
tightened once real CI medians are available.

| Operation | Budget |
|---|---|
| Batch suitability, 5,000 taxa | ≤ 200 ms p95 (deferred to M15; suitability module not yet present) |
| Load a pack with 10,000 taxa (built SQLite) | ≤ 1 s |
| Peak memory during pack load | ≤ 200 MB |
| `resolve_taxon` p95 | ≤ 5 ms (measured ≈ 12 µs on a 10k-taxa pack in M8) |
| `resolve_fact` p95 (G7) | ≤ 75 µs per call; ≤ 450 ms per 5,000-call batch (min-of-3; see `tests/perf/test_resolve_fact_perf.py`) |
| Multi-scale scaling (G14) | `resolve_taxon` ratio 100k/1k ≤ 3.0×; `resolve_fact` ratio ≤ 4.0× (see `tests/perf/test_resolve_scaling.py`) |
| `agri-core pack build` on 10k source | ≤ 135 s (Colab min × 1.5; see [ADR-010](docs/decisions/ADR-010-perf-budgets.md)) |
| `agri-core validate --strict` on 10k source | ≤ 70 s (Colab min × 1.5; see ADR-010) |
| `agri-core coverage --json` on 10k built | ≤ 27 s (Colab min × 1.5; see ADR-010) |
| `agri-core diff --json` on 10k built (self-diff) | ≤ 36 s (Colab min × 1.5; see ADR-010) |

**How "peak memory" is measured.** The 200 MB budget refers to memory allocated *during* `load_knowledge_set`, measured with `tracemalloc`. It deliberately excludes the Python interpreter and third-party dependencies (`pydantic`, `jsonschema`, `pint`, `typer`, `pyyaml`), which together consume roughly 200 MB at import time in a Colab-class runtime. Including them would make the budget measure dependency bloat rather than the engine's own footprint, which is what this project controls. If you need a hard total cap, budget `absolute RSS ≤ 400 MB` as a smoke check.

**Built vs source pack.** The 1 s load budget is for a *built* pack (`pack.sqlite` + `pack.toml`). Loading from the CSV source tree is a development path and is roughly 10× slower; a separate source-pack budget ships with the perf test in a follow-up PR.

## Repository layout

```
agri-agronomy-core/
├─ dictionary/
│  ├─ parameters.core.yaml   # 31 core parameters at dictionary_version 1.0.0
│  ├─ dictionary.lock        # append-only: <version> <contract_hash>, one line per release
│  ├─ history/               # frozen snapshots per release (1.0.0.json, ...)
│  ├─ unit_registry.yaml     # custom units (pH, ppm, percent, degree_day) + pint aliases
│  └─ vocab/                 # closed sets: archetypes, phases_by_archetype, phase_sets,
│                            #   stages, systems, environments, uses, traits, organism_groups,
│                            #   climate_zones, growth_habits, establishment_states,
│                            #   yield_targets, scope_keys, modules, safety_classes
├─ docs/                     # PACK_FORMAT.md, REVIEW_GUIDE.md;
│                            #   ADDING_A_TAXON, DICTIONARY, RESOLUTION_POLICY, SAFETY (M9);
│                            #   CLIMATE_CATALOG (generated, M10); METHODS (from M11)
│  ├─ decisions/             # ADR-001 ... ADR-012 (ADR-008 reserved, after M15)
│  └─ design/                # plant_wishlist_v4.csv, plant_wishlist_v4_rationale.md,
│                            #   plant_wishlist_v4_migration.md,
│                            #   climate_catalog_v1.csv, climate_catalog_v1_rationale.md (M10)
├─ notebooks/                # Colab quickstart (from v0.2.0), executed in CI
├─ schema/                   # JSON Schemas: outcome, source, taxon, name, fact, hazard,
│                            #   parameter, dataset, manifest, finding, validation_report,
│                            #   taxon_outcome, fact_outcome, meta_info;
│                            #   plus unknown_code_registry.json (code registry, not a schema)
├─ scripts/                  # gen_schemas.py, gen_diff_golden.py, gen_dictionary_doc.py,
│                            #   gen_climate_catalog_doc.py (M10)
├─ src/agri_core/
│  ├─ _samples/              # synthetic Apache-2.0 sample pack
│  ├─ catalog/               # climate catalog loader, lint-catalog gate, excluded-parameter list (M10)
│  ├─ climate/               # atmosphere, radiation, ET0 (M11); thermal time and indices (M12);
│  │                         #   drought and season (M18)
│  ├─ export/                # bundle, tool schemas, edge thresholds, review sheet (M16)
│  ├─ fertilizer/            # nutrient to product, unit conversion (M14)
│  ├─ irrigation/            # registry of modes: container_band, field_etc, paddy_awd (M14)
│  ├─ media/                 # media mixes and water quality (M14)
│  ├─ models/                # Outcome, Result, Dictionary, ParameterDef, PhaseSet, ScopeKey,
│  │                         #   row models, canonical JSON, ids, units, refusals, notices, provenance
│  ├─ pack/                  # build, diff, license gate, load, migrate, scaffold, validate, verify,
│  │                         #   knowledge_set, loader, manifest, tables, sqlite_schema,
│  │                         #   name_index, normalize, errors, tiers, files
│  ├─ propagation/           # dated planner (M15)
│  ├─ registry/              # resolution.py (resolve_taxon, resolve_fact, meta, MetaInfo),
│  │                         #   sources.py, errors.py
│  ├─ safety/                # dose caps, label referral (M14)
│  ├─ soilwater/             # pedotransfer, daily soil-water balance (M17)
│  ├─ stages/                # stage resolver (M13)
│  ├─ suitability/           # scoring with reasons (M15)
│  ├─ thresholds/            # four-point trapezoid checks (M13)
│  ├─ vegetation/            # band-math indices (M19)
│  ├─ cli.py
│  └─ py.typed
├─ tests/
│  ├─ contract/              # Outcome, dictionary, exported schemas, resolution (and, from M10, catalog) stay stable
│  ├─ fixtures/              # synthetic data for behavior tests only
│  ├─ golden/                # independently derived vectors (first shipped M11)
│  ├─ offline/               # socket blocker (from v0.1.0)
│  ├─ perf/                  # performance budget (10 files / 15 tests)
│  ├─ property/              # Hypothesis checks
│  ├─ scenario/              # end-to-end expectations
│  └─ unit/
├─ .github/                  # CODEOWNERS, workflows
├─ CHANGELOG.md
├─ CONTRIBUTING.md
├─ SECURITY.md
├─ LICENSE                   # Apache-2.0
├─ NOTICE
├─ Makefile
├─ pyproject.toml
└─ requirements.lock         # pinned dev dependencies (pip-compile)
```

## License

| Part | License | File |
|---|---|---|
| Code, tests, schemas, dictionary and documentation | Apache License 2.0 | `LICENSE`, `NOTICE` |
| Sample pack in `src/agri_core/_samples/sample_pack/` (synthetic data, no third-party facts) | Apache License 2.0 | `src/agri_core/_samples/sample_pack/` |
| Real data packs and the facts in them | CC BY 4.0, as declared by the `agri-knowledge` repository; every source must meet the [Licensing policy](#licensing-policy) | `agri-knowledge` `LICENSE-DATA`, `ATTRIBUTION.md` and `<pack>/sources.csv` |

- **No third-party data in this repository.** The sample pack is synthetic. Real facts, including their licenses, live in `agri-knowledge` and each pack carries its own `sources.csv`.
- **Redistribution.** Redistributing the code, the documentation or the sample pack follows section 4 of the Apache License 2.0: keep the license and the notices, and mark the files you changed. Real packs are released by `agri-knowledge` under CC BY 4.0, with source credits in `ATTRIBUTION.md`, and remain subject to the licenses of their sources, which this project does not change.
- **Notices.** `NOTICE` lists attributions for third-party material used in tests or documentation, if any.
- **No warranty.** The software and data are provided "as is", without warranties of any kind. To the maximum extent permitted by law, the authors and contributors are not liable for any loss or damage, including crop loss, arising from their use. The license text contains the binding terms.
- **No affiliation or endorsement.** Names of organizations, publications and datasets are used only to identify sources. This project is not affiliated with, endorsed by or sponsored by them. The license does not grant rights to any trademark.
- **Contributions** are licensed under the Apache License 2.0, as set out in section 5 of the license (see [Contributing](#contributing)).
- **Dependencies.** Runtime dependencies use permissive licenses (MIT, BSD, Apache-2.0), and CI checks this. Development tools carry their own licenses and are not distributed with the package.

Copyright 2026 WoodinGlass and the agri-agronomy-core contributors.
