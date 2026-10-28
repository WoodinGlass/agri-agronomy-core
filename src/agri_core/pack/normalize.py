"""Name and scope-value normalization for resolution (M8)."""

from __future__ import annotations

import unicodedata

__all__ = ["normalize_name", "normalize_scope_value"]

_HYBRID_SIGN = "\u00d7"
_HYBRID_LIFT = "x"


def normalize_name(s: str) -> str:
    """Normalize a taxon name for matching.

    Pipeline:

    1. Unicode NFKC (decomposes full-width characters, ligatures,
       circled digits, etc. into their canonical form).
    2. Case folding via ``str.casefold`` (``ß`` -> ``ss``).
    3. Hybrid lift: U+00D7 MULTIPLICATION SIGN -> ASCII ``x``, so a
       query typed as ``Testus x hybridus`` matches a scientific name
       written with the multiplication sign.
    4. Whitespace collapse: any run of Unicode whitespace (including
       NO-BREAK SPACE U+00A0, tab, newline) becomes a single ASCII
       space; leading and trailing whitespace is stripped.

    Display always uses the original string; this function is
    matching-only. Two names that normalize to the same output are
    considered equal for resolution.
    """
    if not s:
        return ""
    s = unicodedata.normalize("NFKC", s)
    s = s.casefold()
    s = s.replace(_HYBRID_SIGN, _HYBRID_LIFT)
    return " ".join(s.split())


def normalize_scope_value(s: str) -> str:
    """Normalize a scope value for matching.

    Same pipeline as :func:`normalize_name` **without** the hybrid
    lift: scope values (``system``, ``environment``, ``variety``, ...)
    never contain the multiplication sign, and preserving it avoids
    any chance of a legitimate value being folded unexpectedly.
    """
    if not s:
        return ""
    s = unicodedata.normalize("NFKC", s)
    s = s.casefold()
    return " ".join(s.split())
