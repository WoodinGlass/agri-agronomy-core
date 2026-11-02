"""Protection-domain scope guard (ADR-007): pure logic, no I/O.

Two tiers of forbidden tokens (ADR-007 sec.6):

**Global** -- applied to *every* parameter, every stage, key and enum
value. These are chemical-control markers that have no legitimate use
in a cultivation knowledge pack, e.g. ``fungicide_interval_days``.

**Domain-only** -- applied only to protection-domain parameters. These
are dose-like tokens that are legitimate in fertilizer or irrigation
parameters (``concentration``, ``pre_harvest_*``) but forbidden in the
protection domain.

The protection domain is ``stage == "protection"`` **or** the key holds
a protection token or the "plant protection" phrase.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from agri_core.models.parameter import ParameterDef

PROTECTION_STAGE: str = "protection"
"""Stage name for the protection domain.

Not in the current ``stages`` vocab; ADR-007 documents the MINOR bump
that will add it. Keys are matched by token in the interim."""

PROTECTION_TOKENS: frozenset[str] = frozenset(
    {"pest", "disease", "pathogen", "weed", "threat", "biocontrol"}
)

PROTECTION_PHRASES: tuple[tuple[str, ...], ...] = (("plant", "protection"),)

GLOBAL_TOKENS: frozenset[str] = frozenset({"adjuvant", "surfactant", "moa", "frac", "irac", "hrac"})

GLOBAL_TOKEN_SUFFIXES: tuple[str, ...] = ("cide",)

GLOBAL_PHRASES: tuple[tuple[str, ...], ...] = (
    ("tank", "mix"),
    ("active", "ingredient"),
    ("trade", "name"),
    ("mode", "of", "action"),
)

DOMAIN_TOKENS: frozenset[str] = frozenset(
    {
        "dose",
        "dosage",
        "dosing",
        "concentration",
        "spray",
        "drench",
        "formulation",
        "phi",
        "rei",
        "withholding",
        "treatment",
        "curative",
        "eradicant",
        "fumigant",
        "fumigation",
        "interval",
        "schedule",
    }
)

DOMAIN_PHRASES: tuple[tuple[str, ...], ...] = (
    ("application", "rate"),
    ("product", "name"),
    ("pre", "harvest"),
    ("re", "entry"),
    ("action", "threshold"),
    ("economic", "threshold"),
)

ALLOWED_UNITS: frozenset[str] = frozenset(
    {
        "centimeter",
        "day",
        "degree_Celsius",
        "degree_day",
        "kilopascal",
        "meter",
        "percent",
    }
)

_TOKEN_SEP = re.compile(r"[^a-z0-9]+")


def _tokens(s: str) -> list[str]:
    return [t for t in _TOKEN_SEP.sub("_", s.lower()).split("_") if t]


def _check(
    tokens: list[str],
    token_set: frozenset[str],
    phrases: tuple[tuple[str, ...], ...],
    *,
    suffixes: tuple[str, ...] = (),
) -> list[str]:
    reasons: list[str] = []
    for t in tokens:
        if t in token_set:
            reasons.append(f"forbidden token {t!r}")
        for suf in suffixes:
            if t.endswith(suf):
                reasons.append(f"forbidden token ending {suf!r}: {t!r}")
    for phrase in phrases:
        n = len(phrase)
        for i in range(len(tokens) - n + 1):
            if tuple(tokens[i : i + n]) == phrase:
                reasons.append("forbidden phrase " + " ".join(phrase))
    return reasons


def is_protection_domain(param: ParameterDef) -> bool:
    if param.stage == PROTECTION_STAGE:
        return True
    tokens = _tokens(param.key)
    if any(t in PROTECTION_TOKENS for t in tokens):
        return True
    for phrase in PROTECTION_PHRASES:
        n = len(phrase)
        for i in range(len(tokens) - n + 1):
            if tuple(tokens[i : i + n]) == phrase:
                return True
    return False


@dataclass(frozen=True)
class ProtectionViolation:
    parameter: str
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class HazardCodeViolation:
    hazard_code: str
    reasons: tuple[str, ...]


def find_protection_violations(
    parameters: dict[str, ParameterDef],
) -> list[ProtectionViolation]:
    out: list[ProtectionViolation] = []
    for key in sorted(parameters):
        p = parameters[key]
        reasons: list[str] = []

        reasons.extend(
            _check(_tokens(key), GLOBAL_TOKENS, GLOBAL_PHRASES, suffixes=GLOBAL_TOKEN_SUFFIXES)
        )
        for v in p.enum_values or ():
            for r in _check(
                _tokens(v), GLOBAL_TOKENS, GLOBAL_PHRASES, suffixes=GLOBAL_TOKEN_SUFFIXES
            ):
                reasons.append(f"enum value {v!r}: {r}")

        if is_protection_domain(p):
            if p.unit is not None and p.unit not in ALLOWED_UNITS:
                reasons.append(f"unit {p.unit!r} not in protection allowlist")
            reasons.extend(_check(_tokens(key), DOMAIN_TOKENS, DOMAIN_PHRASES))
            for v in p.enum_values or ():
                for r in _check(_tokens(v), DOMAIN_TOKENS, DOMAIN_PHRASES):
                    reasons.append(f"enum value {v!r}: {r}")
            if p.shape == "rule":
                reasons.append("shape='rule' (free-form payload)")
            if p.kind == "extension":
                reasons.append("kind='extension' bypasses engine review")
            if p.tier_required:
                reasons.append("tier_required=True")

        if reasons:
            out.append(ProtectionViolation(parameter=key, reasons=tuple(reasons)))
    return out


def find_hazard_code_violations(
    hazard_codes: list[str] | set[str] | tuple[str, ...],
) -> list[HazardCodeViolation]:
    out: list[HazardCodeViolation] = []
    for code in sorted(set(hazard_codes)):
        reasons: list[str] = []
        tokens = _tokens(code)
        reasons.extend(
            _check(tokens, GLOBAL_TOKENS, GLOBAL_PHRASES, suffixes=GLOBAL_TOKEN_SUFFIXES)
        )
        reasons.extend(_check(tokens, DOMAIN_TOKENS, DOMAIN_PHRASES))
        if reasons:
            out.append(HazardCodeViolation(hazard_code=code, reasons=tuple(reasons)))
    return out


__all__ = [
    "ALLOWED_UNITS",
    "DOMAIN_PHRASES",
    "DOMAIN_TOKENS",
    "GLOBAL_PHRASES",
    "GLOBAL_TOKENS",
    "GLOBAL_TOKEN_SUFFIXES",
    "PROTECTION_PHRASES",
    "PROTECTION_STAGE",
    "PROTECTION_TOKENS",
    "HazardCodeViolation",
    "ProtectionViolation",
    "find_hazard_code_violations",
    "find_protection_violations",
    "is_protection_domain",
]
