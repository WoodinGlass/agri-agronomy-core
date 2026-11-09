"""Safety helpers (M14).

Dose caps and label referral. Every module here must reach 100%
coverage (CONTRIBUTING.md).
"""

from __future__ import annotations

from agri_core.safety.dose_cap import apply_dose_cap

__all__ = ["apply_dose_cap"]
