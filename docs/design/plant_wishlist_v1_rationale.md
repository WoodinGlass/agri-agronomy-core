# Plant wishlist v1 — rationale

Coverage matrix used as input for designing the core parameter dictionary (M1-1).

- Artifact: `plant_wishlist_v1.csv` (125 rows)
- Spec: v2.9
- Status: superseded by `agri-knowledge/packs/<version>/taxa.csv` at M1-2;
  kept as design rationale.

## Coverage

Seven cultivation categories requested by the project owner:

| Category | Representative count |
|---|---|
| Sayur (vegetables) | 24 |
| Buah (fruit) | 11 |
| Karnivora (carnivorous) | 7 |
| Hias (ornamental) | 15 |
| Purba (ancient) | 8 |
| Air/laut (aquatic/marine) | 18 |
| Iklim dingin (arctic/cold) | 10 |

Across dimensions:

- 13 archetypes: annual, biennial, herbaceous_perennial, woody_perennial,
  geophyte, aquatic, epiphyte, fungal, pteridophyte, gymnosperm, algae,
  lichen, bryophyte
- 7 uses: staple, vegetable, fruit, spice, fodder, ornamental, specialty
- 6 systems: field, container, greenhouse, flooded, substrate, marine
- 3 climates: tropical, subtropical, temperate
- 9 special_needs codes: chilling_hours, cool_water_required, vernalization,
  photoperiod_sensitive, humidity_min, water_tds_max, host_tree_symbiosis,
  nitrogen_fixation, shade_required

## Why this file exists

The dictionary must cover enough parameter space that most taxa added later
to `agri-knowledge` do not require an engine release (SemVer minor). Two taxa
with the same `(archetype, use, system, climate)` combination should be
addable without a dictionary change.

## What this file is NOT

- Not agronomic values (pH, temperature, Kc, dose)
- Not a source registry (citations, licenses)
- Not the runtime taxa list (`agri-knowledge` is the runtime source)

## special_needs → parameter implications

| Code | Implies parameter(s) |
|---|---|
| `chilling_hours` | `chilling_hours_min`, `chilling_temp_max` |
| `vernalization` | `vernalization_temp`, `vernalization_duration` |
| `photoperiod_sensitive` | `photoperiod_type`, `critical_day_length` |
| `humidity_min` | `rh_min` |
| `water_tds_max` | `water_tds_max` |
| `host_tree_symbiosis` | `host_tree_species`, `inoculation_method` |
| `nitrogen_fixation` | `n_fixation_rate`, `symbiont_species` |
| `shade_required` | `shade_percent` |
| `cool_water_required` | `water_temp_max_c` |

## archetype extensions (v2.5 → v2.9)

| Archetype | Why it is separate from the base 8 |
|---|---|
| `pteridophyte` | Ferns/horsetails/lycopods: spore reproduction, no flowers |
| `gymnosperm` | Conifers/cycads/ginkgo: cone reproduction, no flowers |
| `algae` | Not Plantae: marine/freshwater, fundamentally different biology |
| `lichen` | Symbiotic (fungus + alga/cyanobacterium), not a single organism |
| `bryophyte` | Mosses/liverworts: no vascular system, water-dependent reproduction |

## system extension (v2.7)

`marine` is separate from `flooded` because cultivation requires salinity,
tidal range, and marine substrate — parameters not shared with paddy/pond.

## Protected species policy

This wishlist excludes every taxon with a legal conservation status that
carries regulatory consequences, and replaces each 1:1 with a non-protected
equivalent so that archetype coverage stays intact.

### Removed (9 taxa, all CITES- or Indonesian-protected or IUCN CR/EN/VU)

| Taxon | Legal status | Replaced by |
|---|---|---|
| `nepenthes` | Permen LHK 106/2018; CITES App I (*N. rajah*, *N. khasiana*) / App II | `genlisea` |
| `cycas` | Permen LHK 106/2018; CITES App II | `podocarpus` |
| `cyathea` | Permen LHK 106/2018 (some species) | `nephrolepis` |
| `orchid` | CITES App I/II (Orchidaceae); Permen LHK for many genera | `hoya` |
| `dionaea` | CITES App II | `byblis` |
| `heliamphora` | IUCN assessed, endemic to Venezuelan tepuis | `drosophyllum` |
| `ginkgo` | IUCN EN (wild populations) | `pinus` |
| `araucaria` | IUCN VU (wild populations) | `cupressus` |
| `sequoia` | IUCN EN (wild populations) | `picea` |

### Retained: `vanilla`

*Vanilla planifolia* is listed under CITES Appendix II as part of
Orchidaceae, but the listing carries an explicit exemption for
artificially propagated pods and seeds. *Vanilla planifolia* is **not** in
Permen LHK 106/2018. Indonesia is one of the world's largest vanilla
producers, and its cultivation is a legal, mainstream agricultural activity.
It is retained as the only epiphyte with an unambiguous commercial pathway.

### Legal boundary

Recording a species name and its published parameters (from open sources
such as ICPS cultivation guides or peer-reviewed papers) does **not**
constitute possession, trade, or propagation of a physical protected plant.
UU 5/1990 regulates the plant, not information about the plant.

However, this wishlist goes further than the strict legal minimum: any taxon
that is CITES-listed, Permen LHK-listed, or IUCN-listed at CR/EN/VU is
removed entirely, both to eliminate legal ambiguity and to avoid reputational
risk. This is a design choice for a project that intends to be long-lived and
publicly readable.

### Non-protected replacements — verification

All replacement taxa are:

- not CITES-listed at any appendix;
- not in Permen LHK 106/2018;
- not IUCN CR/EN/VU (either LC or unassessed at species level);
- commercially cultivated at scale in Indonesia or globally.

The genus-level names (`pinus`, `cupressus`, `picea`, `hoya`) are placeholders
consistent with the wishlist convention. At M1-2, each must resolve to a
specific species such as *Pinus radiata*, *Cupressus sempervirens*,
*Picea abies*, or *Hoya carnosa* — all non-protected and commercially available.

This is not legal advice. Downstream users redistributing facts from
`agri-knowledge` for commercial purposes should verify CITES and national
rules for each species independently.

## Updating

- Add a row only when it introduces a new
  `(archetype, use, system, climate, special_needs)` combination, or when a
  project-required category has fewer than 2 representatives.
- To add a special_needs code, submit a proposal (see spec §6.3) with
  rationale; do not silently extend the closed set.
- After M1-2, this file is frozen. Additions happen in `agri-knowledge`.
