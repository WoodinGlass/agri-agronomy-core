"""Unicode guard: reject bidi, zero-width, and invisible characters.

Bidi override characters enable Trojan Source attacks (CVE-2021-42574):
code that reads one way in a diff and another way to a compiler. Zero-
width and invisible joiner characters let content smuggle text past
human review while a language model still reads it. Pack data is input
to LLM agents, so the loader rejects these codepoints before parsing.
"""

from __future__ import annotations

# Bidi control characters (Trojan Source attack surface).
_BIDI: frozenset[int] = frozenset(
    {
        0x202A,
        0x202B,
        0x202C,
        0x202D,
        0x202E,  # LRE/RLE/PDF/LRO/RLO
        0x2066,
        0x2067,
        0x2068,
        0x2069,  # LRI/RLI/FSI/PDI
    }
)

# Zero-width and invisible joiner characters (text smuggling).
_ZERO_WIDTH: frozenset[int] = frozenset(
    {
        0x200B,
        0x200C,
        0x200D,
        0x200E,
        0x200F,  # ZWSP/ZWNJ/ZWJ/LRM/RLM
        0xFEFF,  # BOM as zero-width
        0x2060,
        0x2061,
        0x2062,
        0x2063,
        0x2064,  # word joiner family
    }
)

# Other invisible / formatting characters that are not meaningful in pack text.
_OTHER: frozenset[int] = frozenset(
    {
        0x00AD,  # soft hyphen
        0x180E,  # Mongolian vowel separator
        *range(0xFE00, 0xFE10),  # variation selectors 1-16
    }
)

FORBIDDEN: frozenset[int] = _BIDI | _ZERO_WIDTH | _OTHER
"""All codepoints rejected by :func:`find_forbidden`."""


def find_forbidden(text: str) -> tuple[int, str] | None:
    """Return ``(codepoint, category)`` of the first forbidden character.

    Categories: ``"bidi-control"``, ``"zero-width"``, ``"invisible"``.
    Returns ``None`` if *text* is clean.
    """
    for ch in text:
        cp = ord(ch)
        if cp in _BIDI:
            return cp, "bidi-control"
        if cp in _ZERO_WIDTH:
            return cp, "zero-width"
        if cp in _OTHER:
            return cp, "invisible"
    return None


__all__ = ["FORBIDDEN", "find_forbidden"]
