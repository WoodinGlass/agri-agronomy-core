"""Atmosphere, radiation and ET0 calculators (M11).

Every public function returns :data:`agri_core.models.Outcome`. Functions
that cannot read a pack return empty ``provenance`` and ``evidence == []``.
"""

from __future__ import annotations

from agri_core.climate.elevation import (
    pressure_from_elevation,
    temp_from_elevation,
)
from agri_core.climate.et0 import et0, et0_hargreaves_samani, et0_penman_monteith
from agri_core.climate.par import dli, ppfd
from agri_core.climate.psychrometry import dew_point, vpd, wet_bulb
from agri_core.climate.radiation import net_radiation, solar_radiation
from agri_core.climate.solar import (
    clearness_index,
    daylength,
    extraterrestrial_radiation,
)
from agri_core.climate.wind import (
    wind_direction_from_uv,
    wind_height_adjust,
    wind_run,
    wind_speed_from_uv,
)

__all__ = [
    "clearness_index",
    "daylength",
    "dew_point",
    "dli",
    "et0",
    "et0_hargreaves_samani",
    "et0_penman_monteith",
    "extraterrestrial_radiation",
    "net_radiation",
    "ppfd",
    "pressure_from_elevation",
    "solar_radiation",
    "temp_from_elevation",
    "vpd",
    "wet_bulb",
    "wind_direction_from_uv",
    "wind_height_adjust",
    "wind_run",
    "wind_speed_from_uv",
]
