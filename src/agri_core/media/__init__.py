"""Media and water-quality calculators (M14).

SAR, RSC, and a categorical water-quality limit check. No thresholds
are hardcoded; every limit comes from the pack.
"""

from __future__ import annotations

from agri_core.media.water_quality import (
    check_water_quality,
    compute_rsc,
    compute_sar,
)

__all__ = [
    "check_water_quality",
    "compute_rsc",
    "compute_sar",
]
