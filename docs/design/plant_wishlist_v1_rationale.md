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

Six taxa in this list are IUCN-listed or CITES-listed but have a clear
commercial horticultural pathway: `ginkgo`, `nepenthes`, `dionaea`,
`cyathea`, `araucaria`, `cycas`.

Species without a realistic commercial cultivation pathway are excluded:
`wollemi_pine` (~60 wild individuals), `welwitschia` (CITES App II,
protected range states). These move to `taxa_candidates.csv` with note
"protected species, no commercial cultivation pathway".

## Updating

- Add a row only when it introduces a new
  `(archetype, use, system, climate, special_needs)` combination, or when a
  project-required category has fewer than 2 representatives.
- To add a special_needs code, submit a proposal (see spec §6.3) with
  rationale; do not silently extend the closed set.
- After M1-2, this file is frozen. Additions happen in `agri-knowledge`.
