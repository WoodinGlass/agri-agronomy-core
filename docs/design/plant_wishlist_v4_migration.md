# Plant wishlist v4 migration

Snapshot: `docs/design/plant_wishlist_v4.csv`
SHA-256: `67981f9bcb7dda02262834c2fbdf7d2789bcca40e67d92b13c07abea61910354`
Rows: 125

This snapshot is frozen as design rationale. The runtime contract does not
depend on this file. Migration produces `tests/fixtures/wishlist_derived.csv`,
which is what coverage tests read.

## Lossless rule

One fixture row exists for every snapshot row (125 -> 125).
No row is dropped. A row may only be removed if it is out of scope, and the
reason must be recorded in the "Excluded taxa" section below. Currently no
row is excluded.

## Code mapping (use)

| v4 use | v5 use | Rule |
|---|---|---|
| vegetable | vegetable | auto |
| fruit | fruit | auto |
| staple | staple | auto |
| fodder | forage | auto |
| ornamental | ornamental | auto |
| spice | spice | auto |
| edible_fungus | edible_fungus | auto |
| specialty | per-taxon table | manual |

## Code mapping (system + environment)

| v4 system | v5 system | v5 environment | Rule |
|---|---|---|---|
| field | field | unknown | auto |
| container | container | unknown | auto |
| flooded | flooded | unknown | auto |
| marine | marine | unknown | auto |
| greenhouse | unknown | protected | manual |
| substrate | per-taxon table | unknown | manual |

`substrate` is split per taxon:

- `soilless`: hydroponic, aeroponic, or inert medium.
- `fungal_bed`: log, bag, or mushroom bed.
- `container`: organic medium in a pot (sphagnum, bark, peat tray).

## Code mapping (traits)

| v4 special_needs | v5 trait |
|---|---|
| chilling_hours | chill_requirement |
| vernalization | vernalization |
| photoperiod_sensitive | photoperiod_sensitive |
| host_tree_symbiosis | symbiont_required |
| nitrogen_fixation | nitrogen_fixing |
| shade_required | shade_required |
| cool_water_required | cool_water_required |
| humidity_min | removed (uses `rh` parameter) |
| water_tds_max | removed (uses `water_ec_max`) |

## Per-taxon manual decisions

Rows below have `needs_review = true` and `reviewed_by` empty in the fixture.
They are NOT counted in coverage until `reviewed_by` is filled in. The
mappings below are initial best guesses by migration; they are not locked
and may be changed by a reviewer.

### `use = specialty`

| Taxon | Initial v5 use | Note |
|---|---|---|
| oyster_mushroom | edible_fungus | confirm or override |
| truffle | edible_fungus | confirm or override |
| pinus | ornamental | confirm or override |
| papyrus | ornamental | confirm or override |
| gracilaria | vegetable | confirm or override |
| porphyra | vegetable | confirm or override |
| umbilicaria | edible_fungus | confirm or override |
| sphagnum | unknown | confirm or override |

### `system = substrate`

| Taxon | Initial v5 system | Note |
|---|---|---|
| oyster_mushroom | fungal_bed | confirm or override |
| truffle | unknown | confirm or override |
| button_mushroom | fungal_bed | confirm or override |
| arctic_cottongrass | container | confirm or override |
| cloudberry | container | confirm or override |
| cladonia | unknown | confirm or override |
| umbilicaria | unknown | confirm or override |
| sphagnum | container | confirm or override |

## Excluded taxa

None at the time of writing. To exclude a row, add it here with a reason
that states why it is out of scope, not merely "not a category".

## Migration counters

- Snapshot rows: 125
- Fixture rows: 125
- Auto rows: 112
- Manual rows pending review: 13
- Reviewed manual rows: 0
- Rows counted in coverage now: 112
