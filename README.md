# agri-agronomy-core

> Offline, deterministic crop profiles and agronomy calculators. Every number carries a source, a unit and a review status.

[![CI](https://github.com/WoodinGlass/agri-agronomy-core/actions/workflows/ci.yml/badge.svg)](https://github.com/WoodinGlass/agri-agronomy-core/actions/workflows/ci.yml)![Status](https://img.shields.io/badge/status-pre--release-orange)![Python](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12-blue)![Code license](https://img.shields.io/badge/code-Apache--2.0-blue)![Profiles license](https://img.shields.io/badge/profiles-CC%20BY%204.0-lightgrey)[![Open in Colab](https://colab.research.google.com/assets/colab-badge.svg)!](https://colab.research.google.com/github/WoodinGlass/agri-agronomy-core/blob/main/notebooks/01_quickstart.ipynb)

> **Pre-release.** Interfaces, the profile schema and values may change until `v0.1.0` is tagged. This project provides reference data and calculations only. It is not professional agronomic advice. Read [Safety and limitations](#safety-and-limitations) before relying on any output.

## What this is

`agri-agronomy-core` is a pure-Python library with two parts:

1. **Crop profiles.** Curated, versioned YAML files that describe a crop across six stages: site and media selection, seeding, planting, care, harvest and propagation. Every value carries its unit, the conditions it applies to (its scope), a source, an evidence grade and a review status.
2. **A calculation engine.** Deterministic functions that read those profiles and compute climate indices, threshold checks, irrigation, fertilizer amounts, growing-media recipes, site suitability and propagation plans.

It is meant to be the single source of agronomic numbers inside larger systems such as farm apps, IoT gateways, LLM agents and evaluation suites. Doses, water volumes and thresholds come from cited, reviewed data and tested code, never from a model's guess.

It runs fully offline: no network access, database, server, API key or GPU.

Every result states what was computed, with which method, from which sources and under which assumptions. When the library cannot answer, it says so instead of guessing.

## What this is not

- **Not a substitute for an agronomist, extension service, product label or local law.** It supports decisions; it does not make them.
- **Not a pesticide tool.** It never calculates pesticide, herbicide or fungicide doses. Such requests return `REFER_TO_LABEL`.
- **Not a controller.** It does not operate pumps, valves, dosing units or any other actuator. It returns values and plans for people or systems that have their own safeguards.
- **Not a server, database or user interface.** There is no HTTP API, storage or web editor, only a Python package and a command-line tool.
- **Not a sensor pipeline.** It does not read, clean or store sensor streams. Callers pass values in, with explicit units.
- **Not machine learning.** It contains no models and performs no training or inference.
- **Not a crop recommender, diagnostic tool or yield forecaster.** It evaluates the crop you name. It does not rank crops, identify pests or diseases, or predict yield.
- **Not a compliance tool.** It does not encode national or regional rules on fertilizers, water use or plant protection.
- **Not an encyclopedia.** Coverage is limited to the listed profiles, and `unknown` is a valid answer.

## Design principles

1. **Numbers come from data and tested code, never from a language model.** Downstream systems may explain a result, but they should not invent one.
2. **Refuse rather than guess.** Missing input raises `InsufficientInput` and names what is missing. Missing data gives `unknown`. An inapplicable question gives `NotApplicable` with a reason. There are no silent defaults.
3. **Provenance on every value.** Each profile value cites a source in `profiles/sources.csv` and carries an evidence grade.
4. **Status gates.** Values move from `draft` to `reviewed` to `approved`, and calculators only use values at or above the minimum status the caller accepts.
5. **Pure and repeatable.** No I/O and no hidden clock: dates are arguments. The same input always gives the same output.
6. **Scoped, not global.** No single pH, temperature or dose fits every crop, region and growing system. Values declare where they apply, and the library answers `unknown` outside that scope.
7. **Conservative by default.** Fertilizer amounts have per-application caps, pesticides are never computed, and conversions that need an explicit factor (such as EC to ppm) refuse to run without one.

## Features

| # | Area | What it does | Target |
|---|------|--------------|--------|
| 1 | Registry | Loads and validates profiles. Resolves crop names and aliases in several languages (`resolve_crop("tomato")`). `meta()` reports the library version and a content hash of all profiles. | v0.1.0 |
| 2 | Climate | Vapor pressure deficit (VPD), growing degree days (GDD), daily light integral (DLI) and reference evapotranspiration (ET0: FAO-56 Penman–Monteith, with a Hargreaves–Samani fallback). Temperature estimate from elevation. | v0.1.0 |
| 3 | Thresholds and stages | Four-point trapezoid checks that return `optimal`, `suboptimal` or `critical`. Stage resolver from planting age and GDD (perennials from dated events supplied by the caller). | v0.1.0 |
| 4 | Irrigation | Three modes: `field_etc` (ET0 × Kc), `paddy_awd` (alternate wetting and drying for rice) and `container_band` (moisture band for containerized media). With no standard Kc the answer is `NotApplicable`; a Kc is never invented. | v0.1.0 |
| 5 | Fertilizer | Nutrient to product to kg/ha, g/plant, g/m² and ppm/EC, with per-stage splits, soil-test adjustment and per-application caps. Interpretation tables are tagged with the region and method they apply to. | v0.1.0 |
| 6 | Media and water | Volume ratios to liters per component, plus water-quality limits (for example a TDS limit for carnivorous plants) taken from cited sources. | v0.1.0 |
| 7 | Suitability | `suitable`, `marginal`, `unsuitable` or `unknown`, with a reason per factor and what would have to change. | v0.2.0 |
| 8 | Propagation planner | Dated plans: steps, materials, durations, success indicators and when to separate. | v0.2.0 |
| 9 | Exports | `bundle.json`, `tool_schemas.json`, `edge_thresholds.json`, `review_sheet.csv`. | v0.2.0 |
| 10 | Command line | `validate`, `lint-sources`, `show`, `calc`, `diff` and `export`, added milestone by milestone. | v0.1.0+ |

`v0.1.0` includes tomato and rice only. `v0.2.0` completes the first six profiles.

## Quick start

### Install

Releases are distributed as git tags. Pin one:

```bash
pip install "git+https://github.com/WoodinGlass/agri-agronomy-core@v0.1.0"
```

`v0.1.0` is not tagged yet. Until it is, replace `@v0.1.0` with `@main` in this and the Colab snippet, for development use only.

Requires Python 3.10 or newer (tested on 3.10, 3.11 and 3.12). Runtime dependencies: Pydantic v2, jsonschema, PyYAML, pint and Typer. Pure Python, CPU only.

### Google Colab

Open the quickstart notebook with the badge above, or install in any Colab cell:

```python
!pip install -q "git+https://github.com/WoodinGlass/agri-agronomy-core@v0.1.0"
```

No API key or GPU is needed. The quickstart notebook is executed in CI, so it is verified to run.

### Python (preview)

The snippet shows the intended `v0.1` interface that the contract tests are written against. Names may change until `v0.1.0` is tagged.

```python
from agri_core import registry
from agri_core.climate import vpd

crop = registry.resolve_crop("tomato")    # also "tomat" or "Solanum lycopersicum"
print(crop.id)
print(registry.meta())                    # library version + profile content hash

r = vpd(temp_c=28.0, rh_pct=65.0)
print(r.value, r.unit)                    # about 1.32 kPa
print(r.method, r.assumptions, r.warnings)
```

### Command line

```bash
agri-core --help
agri-core validate        # schema, source, unit and ordering checks on all profiles
agri-core lint-sources    # check sources.csv and every `src` reference
agri-core show tomato     # print a profile
```

## Output contract

Every calculation returns a `Result`:

| Field | Meaning |
|---|---|
| `value` | The computed value |
| `unit` | Explicit unit. The library never guesses units |
| `method` | How it was computed (for example which ET0 method) |
| `provenance` | Where the numbers came from: profile, version and source IDs |
| `evidence` | Evidence grade(s) of the profile values used |
| `assumptions` | Every assumed or defaulted condition, stated explicitly |
| `warnings` | Fallback methods, out-of-range inputs, near-threshold results |
| `capped` | `true` if a safety cap limited the result |

When the library cannot produce a result, it says why:

| Situation | Response |
|---|---|
| A required input is missing | `InsufficientInput(missing=[...])` |
| The profile has no value for the requested conditions | `unknown`, with a reason |
| The question does not apply (for example no standard Kc, or a propagation method the crop does not use) | `NotApplicable`, with a reason |
| Pesticides | `REFER_TO_LABEL` |
| A unit conversion needs an explicit factor (EC to ppm: 0.5, 0.64 or 0.7) | Rejected until the factor is given |

## Profile format

Profiles are YAML files validated against a JSON Schema. The example below is illustrative and contains no agronomic data.

```yaml
id: tomato
names: [tomato, tomat, Solanum lycopersicum]   # aliases in any language
archetype: annual                               # annual | perennial
irrigation_mode: field_etc                      # field_etc | paddy_awd | container_band
stages:
  site_media:
    soil_ph:
      pts: [null, null, null, null]             # abs_min, opt_min, opt_max, abs_max
      unit: pH
      scope:
        elevation_m: [null, null]
        variety: all
      src: [S014]                               # IDs in profiles/sources.csv
      evidence: B                               # A (guideline or peer-reviewed) to D (anecdotal)
      status: draft                             # draft | reviewed | approved
      reviewed_by: null
    soil_ec:
      unknown: true
      reason: no reliable source found for this scope
```

- **Stages:** `site_media` → `seeding` → `planting` → `care` → `harvest` → `propagation` (optional per crop).
- **Thresholds:** a value between `opt_min` and `opt_max` is `optimal`, between an absolute and an optimal bound is `suboptimal`, and outside the absolute bounds is `critical`. The four-point style follows FAO's EcoCrop; no EcoCrop data is copied.
- **Unknown values:** a value with no reliable source is written as `unknown: true` with a `reason`, never left as a bare `null`.
- **Status:** `draft` means entered but not yet checked against its source. `reviewed` means a maintainer matched it to the cited source. `approved` means a domain expert signed it off. Callers choose the minimum status they accept, and the default is `approved`. `draft` values are never returned by calculators. `v0.1.0` ships `reviewed` profiles only, so it is meant for development and pilots; `approved` values arrive with `v0.2.0`.
- **Evidence grades:** A to D, where A is strongest. The full rubric is in `docs/REVIEW_GUIDE.md`.
- **CI checks:** the build fails when a `src` ID is missing from `sources.csv`, points are out of order, a unit is unknown, `commercial_use` contradicts `license`, or an `approved` profile still contains `null`.

## What data goes into a profile

Collect one crop at a time. Every value needs a number (the four trapezoid points where they apply), a unit, a scope (elevation, variety, growing system), a source ID and an evidence grade. If no reliable source exists, write `unknown: true` with a reason instead of estimating.

| Area | What to collect | Mainly used by |
|---|---|---|
| Site and media | soil pH, EC, texture and drainage (or medium type), soil temperature, suitable elevation range | thresholds, suitability |
| Seeding | germination temperature and duration, seedbed medium, seedling age at transplanting | thresholds, stage resolver |
| Planting | spacing or plants per hectare, depth, planting window | fertilizer unit conversion (kg/ha to g/plant), stage resolver |
| Care: climate | air temperature, relative humidity or VPD, light or DLI | thresholds, suitability |
| Care: water | Kc per stage, stage lengths, root depth (`field_etc`); alternate wetting and drying rules (`paddy_awd`); moisture band (`container_band`) | irrigation |
| Care: nutrients | N, P₂O₅ and K₂O requirement per stage | fertilizer |
| Phenology | base and upper temperature for GDD, stage durations in days or GDD | stage resolver |
| Harvest | maturity indicators (age, GDD, physical signs), storage temperature and humidity | thresholds, stage resolver |
| Propagation | method, steps, materials, durations, success indicators, best timing | propagation planner |

Reference tables are collected once, not per crop:

- **Fertilizer products:** nutrient content of common products (for example urea, ammonium sulfate, superphosphates, potassium chloride, calcium nitrate and common NPK grades) and per-application limits, in `profiles/fertilizers.yaml`.
- **Growing media:** recipes as component ratios, in `profiles/media/`.
- **Water quality:** limits for EC, TDS and pH where a crop is sensitive (for example carnivorous plants).
- **Soil-test interpretation:** published tables, each tagged with the region and method it applies to.
- **Sources:** one row per source in `profiles/sources.csv`.
- **Test vectors:** numerical results of published worked examples (for example FAO-56), with citations, in `tests/golden/`.

For `v0.1.0`, collect everything above for tomato and rice except propagation.

Where to look:

- FAO-56 for crop coefficients, ET0 methods and worked examples.
- National and regional agricultural research and extension publications, including university extension services.
- IRRI Rice Knowledge Bank for rice.
- Peer-reviewed open-access papers and reviews, especially for high-value and specialty crops.
- Grower and hobbyist communities (bonsai, carnivorous plants) are acceptable, but grade the evidence low (C or D).

Prefer openly licensed sources and record every license. See [Data sources and provenance](#data-sources-and-provenance).

A spreadsheet with one row per value (crop, stage, parameter, unit, four points, scope, source ID, evidence grade, note) is an easy way to collect; convert it to YAML afterwards.

Not collected here: sensor readings, historical weather, plant images, market prices and LLM training data. Calculators take their inputs as arguments.

## Coverage

First release line (six profiles):

| Profile | Archetype | Notes |
|---|---|---|
| Rice | annual | `paddy_awd` irrigation mode |
| Tomato | annual | `field_etc` irrigation mode |
| Mango | perennial | Propagation: air layering, budding |
| Vanilla | perennial | `container_band` irrigation; propagation: stem cuttings |
| Nepenthes | perennial | `container_band` irrigation; propagation: cuttings, seed |
| Black truffle | perennial | Suitability profile. Expected `unsuitable` at warm, low-elevation tropical sites, so it tests that the library can say no |

The propagation planner returns `NotApplicable` for rice, tomato and black truffle.

Planned next: maize, chili pepper, broccoli, potato, lettuce, grape, apple, watermelon, melon, blueberry, lychee, wasabi and bonsai (per species, with a technique module for pruning, wiring and repotting). Carnivorous plants are split by genus: Nepenthes first, then Dionaea, Drosera and Sarracenia.

**International by design.** Profiles are not tied to a country. Each value declares its scope (elevation, variety, growing system) and its source, so the same crop can carry different values for different conditions. Crop names carry aliases in several languages, and new aliases are welcome. Region-specific material, such as soil-test interpretation tables, is tagged with the region and method it applies to.

## Exports

- `bundle.json`: all profiles, the sources table (including `commercial_use`) and metadata in one versioned file.
- `tool_schemas.json`: function-calling schemas for LLM agents, generated from the same Pydantic models as the library so tools and code cannot drift apart.
- `edge_thresholds.json`: compact thresholds for gateways and devices that must keep working offline.
- `review_sheet.csv`: one row per value, so domain experts can review in a spreadsheet without using GitHub.

## Safety and limitations

- **Reference data, not advice.** Values may be incomplete, out of date, or wrong for your site, variety, climate, soil, water or growing system. Check with a local agronomist or extension service before acting.
- **Local rules and labels come first.** Rules on fertilizers, water use and plant protection differ between countries and regions. This library does not encode them.
- **Pesticides are out of scope.** Follow the product label and local regulations.
- **Caps are a backstop.** Per-application fertilizer caps are conservative upper bounds. They do not replace regional nutrient-management rules. Check the `capped` field.
- **Status matters.** Use `approved` values for decisions affecting real crops. Use `reviewed` values only in development and pilots with human oversight. Never use `draft` values.
- **Inputs decide quality.** The library checks types and units, but it cannot detect a faulty sensor or a wrong measurement.
- **No automatic actuation.** Do not connect outputs directly to pumps, valves or dosing units without independent interlocks (limits, timeouts, manual override) and human approval.
- **`unknown`, `NotApplicable` and `unsuitable` are real answers.** Do not work around them.
- **No warranty.** See [License](#license).

## Data sources and provenance

**Facts and citations only.**

- Every profile value is an individual fact (a number, a range or a rule), written in our own words and structure, with a citation.
- We do not copy passages, tables or figures from sources, and we do not bulk-import third-party datasets or databases.
- `profiles/sources.csv` has one row per source: ID, URL, license, `commercial_use`, access date and citation details.
- `commercial_use` is `yes`, `no` or `unclear`. It records what the source's own license permits, as read by a maintainer, and defaults to `unclear`, including for sources with no stated license. It is a convenience for filtering, not legal advice or a guarantee.
- `agri-core lint-sources` fails when `commercial_use` is `yes` but the `license` column names a non-commercial license (such as CC BY-NC). It also prints a warning for every value whose sources are all `no` or `unclear`. Warnings do not fail CI, because many authoritative sources are non-commercial or unclear. The check cannot see which source a fact was actually taken from, so a source marked `yes` must really contain the fact it is cited for.
- Prefer sources with open licenses. For restricted sources, record individual facts with a citation and nothing more.
- Source licenses vary, and some are non-commercial or otherwise restricted. The license is recorded so you can assess it before commercial use. Copyright and database-right rules differ by jurisdiction, and this is not legal advice.
- Golden tests use published numerical examples (such as the FAO-56 worked examples) as test vectors, with citations. No text from those publications is copied.
- Reviewers are identified by ID, and names appear only with consent. Profiles and exports contain no personal data.
- Organizations and publications are named only to identify sources. There is no affiliation or endorsement.

## Repository layout

```
agri-agronomy-core/
├─ profiles/
│  ├─ crops/            # one YAML profile per crop
│  ├─ propagation/      # air layering, budding, cuttings, division
│  ├─ media/            # growing-media recipes
│  ├─ fertilizers.yaml  # nutrient content of fertilizer products
│  └─ sources.csv       # ID, URL, license, commercial_use, access date
├─ schema/              # JSON Schemas: profile, source, result
├─ src/agri_core/
│  ├─ models/           # Result and error types
│  ├─ registry/         # load, resolve_crop, content hash
│  ├─ climate/          # VPD, GDD, DLI, ET0
│  ├─ thresholds/       # four-point trapezoid checks
│  ├─ stages/           # stage resolver
│  ├─ irrigation/       # field_etc, paddy_awd, container_band
│  ├─ fertilizer/       # nutrient to product, unit conversion
│  ├─ media/            # media mixes and water quality
│  ├─ suitability/      # scoring with reasons
│  ├─ propagation/      # dated planner
│  ├─ safety/           # dose caps, label referral
│  ├─ export/           # bundle, tool schemas, edge thresholds, review sheet
│  └─ cli.py
├─ tests/
│  ├─ unit/
│  ├─ property/
│  ├─ contract/
│  ├─ scenario/
│  ├─ golden/           # validated against published worked examples
│  └─ fixtures/         # synthetic data for behavior tests only
├─ notebooks/           # Colab quickstart, executed in CI
├─ docs/                # REVIEW_GUIDE.md, architecture decision records
├─ .github/             # CODEOWNERS, workflows
├─ LICENSE              # Apache-2.0 (code)
├─ LICENSE-DATA         # CC BY 4.0 (profiles/)
├─ CHANGELOG.md
├─ Makefile
└─ pyproject.toml
```

## Development

```bash
git clone https://github.com/WoodinGlass/agri-agronomy-core.git
cd agri-agronomy-core
pip install -e ".[dev]"
pre-commit install

ruff check . && ruff format --check .
mypy
pytest
agri-core validate && agri-core lint-sources
```

Tooling: pytest, Hypothesis, pytest-cov, ruff, mypy (strict), nbmake, nbstripout, pre-commit and pip-audit.

**Test kinds**

- `unit`: functions in isolation.
- `property`: Hypothesis checks such as unit round-trips, no negative amounts, and monotonic behavior with area.
- `contract`: `Result` and exported tool schemas stay stable.
- `scenario`: end-to-end expectations, for example black truffle at a warm lowland tropical site must be `unsuitable`.
- `golden`: results validated against published worked examples.

**Release gates (every release)**

- ruff and mypy (strict) are clean.
- Coverage is at least 90%, and 100% for `safety/`.
- CI is green on Python 3.10, 3.11 and 3.12, and `pip-audit` runs in CI.
- Notebooks execute (nbmake) and are committed without outputs (nbstripout).
- Profile checks pass (see [Profile format](#profile-format)).
- The GitHub Release contains the wheel, the bundle and hashes, and `CHANGELOG.md` is updated.

**Working in Google Colab.** Clone the repository, run `pip install -e ".[dev]"` and `pytest`, then push with a GitHub token stored in Colab Secrets. YAML profiles can also be edited directly in the GitHub web editor.

## Contributing

Contributions are welcome, especially:

- corrections to values, with a citation
- new values with sources, evidence grades and an honest scope
- crop name aliases in other languages
- tests and golden vectors from published worked examples
- expert review of `draft` and `reviewed` values

Rules:

1. **Facts and citations only.** Do not paste text, tables or figures from sources, and do not bulk-import datasets. Pull requests that do will be declined.
2. **Every new value needs** a `src` (added to `sources.csv` with URL, license, `commercial_use` and access date), an `evidence` grade, a `scope`, and the status `draft`. See [What data goes into a profile](#what-data-goes-into-a-profile).
3. **Unknown stays unknown.** If you cannot find a reliable source, write `unknown: true` with a reason.
4. **Everything is in English:** code, schema keys, identifiers and documentation. Local-language crop names go in `names`.
5. **Code changes need tests.** Changes under `safety/` also need 100% coverage and maintainer review.
6. **Licensing.** By submitting a contribution you confirm that you have the right to contribute it and that it is licensed under the same terms as the files it changes (Apache-2.0 for code, CC BY 4.0 for `profiles/`).

Domain experts can review through `review_sheet.csv` without a GitHub account, and the maintainer records the outcome. Code owners for `profiles/` are listed in `.github/CODEOWNERS`.

## Security

- **Vulnerabilities** in code or dependencies: use GitHub's private vulnerability reporting (Security tab, then "Report a vulnerability") instead of a public issue.
- **Harmful data errors** (an unsafe cap, a wrong unit, a threshold off by an order of magnitude): open an issue labeled `data-error` with a citation. If you believe there is immediate risk, report it privately as above.
- The library makes no network calls and handles no personal data.

## Versioning and releases

- Semantic Versioning applies to code and public contracts: `Result`, the JSON Schemas and the exported tool schemas.
- Every change to a profile value is listed in `CHANGELOG.md` and changes the content hash returned by `meta()`. Downstream systems should re-run their own checks when that hash changes.
- Pin a tag. `main` may change without notice.
- Releases are git tags and GitHub Releases (wheel, bundle, hashes). They are not published on PyPI.

## Citing

If you use the profiles in research or in a product, cite this repository with the release tag you used, and cite the original sources listed in `profiles/sources.csv` for the values you rely on.

## Milestones

| Milestone | Scope | Done when |
|---|---|---|
| **M0** Foundation | Repository, `pyproject.toml`, CI, pre-commit, `Result` model, JSON Schemas, `sources.csv` linter | CI is green on the empty but valid package |
| **M1** Schema and first profiles | `profile.schema.json`, tomato and rice as `draft` with full sources, registry, `agri-core validate` | Both profiles validate in CI |
| **M2** Climate and thresholds | VPD, GDD, DLI, ET0 with fallback, temperature from elevation, threshold checks, stage resolver | FAO-56 golden tests pass |
| **M3** Water, nutrients and media | Irrigation modes, fertilizer with safety caps, media and water, property tests, maintainer review of tomato and rice | Tag `v0.1.0` |
| **M4** Remaining first-release profiles | Mango, vanilla, Nepenthes, black truffle, suitability, scenario tests | Black truffle at a warm lowland tropical site returns `unsuitable` |
| **M5** Propagation and expert review (runs alongside M4 and M6) | Propagation planner, review-sheet export, expert approval | All six profiles are `approved` |
| **M6** Exports and docs | Bundle, tool schemas, edge thresholds, quickstart notebook, documentation | Tag `v0.2.0` |
| **v0.3+** | Activity calendar, varieties, the remaining 13 profiles | Not yet scheduled |

**Release criteria**

- `v0.1.0`: tomato and rice at `reviewed`, features 1 to 6 working, and every release gate passing.
- `v0.2.0`: six profiles `approved` by at least one expert each, every `src` with its license recorded, and every release gate passing.

## License

| Part | License | File |
|---|---|---|
| Code, tests, schemas, tooling and documentation (everything outside `profiles/`) | Apache License 2.0 | `LICENSE` |
| Profile files (`profiles/`): this project's curated values, structure and annotations | Creative Commons Attribution 4.0 International (CC BY 4.0) | `LICENSE-DATA` |
| Third-party sources cited by the profiles | Their own licenses, which this project does not change | `profiles/sources.csv` |

- **What the profile license covers.** CC BY 4.0 covers only this project's original contribution: the selection, curation, structure, annotations, evidence grades and review statuses. It also licenses database rights where they exist. It does not cover or relicense third-party material. Facts are cited to their sources, and each source keeps its own license, recorded in `profiles/sources.csv`. If you use the data commercially, check the license of every source behind the values you rely on. The `commercial_use` column can help you filter, but it is a maintainer's reading of each license, not legal advice.
- **Attribution.** When you redistribute the profiles, including exports such as `bundle.json`, credit "agri-agronomy-core contributors", link to this repository and indicate any changes you made.
- **No warranty.** The software and data are provided "as is", without warranties of any kind. To the maximum extent permitted by law, the authors and contributors are not liable for any loss or damage, including crop loss, arising from their use. The license texts contain the binding terms.
- **No affiliation or endorsement.** Names of organizations, publications and datasets are used only to identify sources. This project is not affiliated with, endorsed by or sponsored by them. Neither license grants rights to any trademark.
- **Contributions** are licensed under the same terms (see [Contributing](#contributing)).
- **Dependencies** carry their own licenses.

Copyright 2026 WoodinGlass and the agri-agronomy-core contributors.
