"""Fertilizer calculators (M14).

Nutrient-to-product conversion with dose-cap enforcement. Every cap comes
from the pack (safety-critical fact); missing cap refuses.
"""

from __future__ import annotations

from agri_core.fertilizer.nutrient import (
    fertilize_k2o,
    fertilize_n,
    fertilize_p2o5,
)

__all__ = [
    "fertilize_k2o",
    "fertilize_n",
    "fertilize_p2o5",
]
