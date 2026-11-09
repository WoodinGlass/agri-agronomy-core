"""Dose-cap enforcement.

Pure helper called by fertilizer calculators. The caller resolves the
cap (a safety-critical fact) from the pack; this function only applies
it. It never invents a cap.

Contract:
- ``requested <= cap`` -> ``(requested, False)``
- ``requested > cap``  -> ``(cap, True)``
- ``requested < 0``    -> raises ``ValueError``
- ``cap <= 0``         -> raises ``ValueError`` (a zero cap would
  refuse every application; that is a data error, not a runtime state)

The caller is responsible for surfacing ``capped=True`` as
``Result.capped`` and attaching a stable warning code.
"""

from __future__ import annotations

__all__ = ["apply_dose_cap"]


def apply_dose_cap(*, requested: float, cap: float) -> tuple[float, bool]:
    """Clamp *requested* to *cap*.

    Returns ``(effective, capped)``: ``requested`` when it is at or
    below the cap, ``cap`` otherwise, together with a boolean that
    is ``True`` only when the value was limited.

    Raises:
        ValueError: if ``requested`` is negative, or if ``cap`` is not
            strictly positive.
    """
    if requested < 0.0:
        raise ValueError(f"requested must be >= 0, got {requested}")
    if cap <= 0.0:
        raise ValueError(f"cap must be > 0, got {cap}")
    if requested <= cap:
        return (requested, False)
    return (cap, True)
