"""Threshold checks (M13).

Four-point trapezoid classification. Trapezoid values come from the
pack only; nothing is invented.
"""

from __future__ import annotations

from agri_core.thresholds.check import evaluate_trapezoid, threshold_check

__all__ = ["evaluate_trapezoid", "threshold_check"]
