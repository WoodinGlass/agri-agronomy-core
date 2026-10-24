"""Canonical unit IDs used across the dictionary.

One canonical spelling per unit. Parameters may only declare a ``unit`` from
``CANONICAL_UNITS`` (or ``None`` for enum/enum_set/bool/rule/unknown shapes).

Tests verify:
- every unit in ``PINT_CANONICAL_UNITS`` parses via pint and round-trips
  through ``str(ureg.Unit(u))`` modulo whitespace
- every unit in ``CUSTOM_CANONICAL_UNITS`` is declared in
  ``dictionary/unit_registry.yaml``
"""

from __future__ import annotations

PINT_CANONICAL_UNITS: frozenset[str] = frozenset(
    {
        "degree_Celsius",
        "decisiemens/meter",
        "millimeter/day",
        "kilogram/hectare",
        "1/hectare",
        "mole/meter**2/day",
        "kilopascal",
        "centimeter",
        "meter",
        "day",
        "dimensionless",
    }
)

CUSTOM_CANONICAL_UNITS: frozenset[str] = frozenset(
    {
        "pH",
        "ppm",
        "percent",
        "degree_day",
    }
)

CANONICAL_UNITS: frozenset[str] = PINT_CANONICAL_UNITS | CUSTOM_CANONICAL_UNITS
