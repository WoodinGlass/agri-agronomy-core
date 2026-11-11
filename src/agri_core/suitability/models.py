"""Suitability input models (M15, ADR-016)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class Site(BaseModel):
    """Caller-supplied site values for one suitability evaluation.

    One field per site-facing parameter (soil_ph, soil_ec, air_temp_day,
    air_temp_night, air_rh, vpd, dli). Values may be None; a None value
    makes ``site_suitability`` refuse with ``InsufficientInput`` listing
    every missing field. ``extra="forbid"`` catches typos.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    soil_ph: float | None = None
    soil_ec: float | None = None
    air_temp_day: float | None = None
    air_temp_night: float | None = None
    air_rh: float | None = None
    vpd: float | None = None
    dli: float | None = None


__all__ = ["Site"]
