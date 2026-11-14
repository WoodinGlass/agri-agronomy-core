"""Generate ``tool_schemas.json`` -- strict-compatible function-calling schemas.

M16. Generates input schemas for LLM agent tools from the same Pydantic
models as the library, so tools and code cannot drift.

Design notes (ADR-021, planned):
- **Input only.** Tool-calling APIs define the *input* schema; ``Outcome``
  remains in ``schema/outcome.schema.json`` and is referenced from each
  tool description rather than embedded. This avoids the "outcome
  variants must be preserved in tool schema" trap.
- **Strict subset.** OpenAI strict and Anthropic strict only accept a
  narrow JSON Schema subset. Anything outside it is rejected at tool
  registration. See ``test_tool_schemas.py`` for the enforced subset.
- **Range info in prose.** Numeric bounds (``minimum``/``maximum``) and
  string bounds (``minLength``/``maxLength``) are not allowed; they go
  into the ``description`` text as plain English.
- **Host-only parameters.** ``pack``, ``min_status``, ``require_commercial``
  are injected by the host and never appear in the schema, so the LLM
  cannot lower the status floor or skip the commercial-use guard.
- **Tool = task, not signature.** A tool is a question the LLM can ask,
  not a mirror of a Python function. Split irrigation into one tool per
  mode; keep staging as one tool with an explicit ``mode`` argument and
  nullable mode-specific fields.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

__all__ = [
    "TOOL_SCHEMAS_VERSION",
    "generate_tool_schemas",
    "get_tool_schemas",
    "write_tool_schemas",
]

#: Independent SemVer for the tool-schema contract. Bumped by hand.
TOOL_SCHEMAS_VERSION = "1.0.0"

REPO_ROOT = Path(__file__).resolve().parents[3]
SCHEMA_DIR = REPO_ROOT / "schema"
TARGET = SCHEMA_DIR / "tool_schemas.json"


# ---------------------------------------------------------------------------
# Schema building blocks (strict-compatible)
# ---------------------------------------------------------------------------


def _nullable(kind: str, *, description: str) -> dict[str, Any]:
    """Return ``anyOf([{type: kind}, {type: null}])`` with a description.

    Strict mode requires every property to be ``required``; nullable
    properties model "optional" at the type level.
    """
    return {
        "anyOf": [{"type": kind}, {"type": "null"}],
        "description": description,
    }


def _string(description: str) -> dict[str, Any]:
    return {"type": "string", "description": description}


def _string_nullable(description: str) -> dict[str, Any]:
    return _nullable("string", description=description)


def _number(description: str) -> dict[str, Any]:
    return {"type": "number", "description": description}


def _integer(description: str) -> dict[str, Any]:
    return {"type": "integer", "description": description}


def _boolean(description: str) -> dict[str, Any]:
    return {"type": "boolean", "description": description}


def _enum(values: list[str], description: str) -> dict[str, Any]:
    return {"type": "string", "enum": values, "description": description}


def _array_of_strings(description: str) -> dict[str, Any]:
    return {"type": "array", "items": {"type": "string"}, "description": description}


def _object(
    properties: dict[str, dict[str, Any]],
    *,
    description: str = "",
) -> dict[str, Any]:
    """Return an object schema with every property required."""
    schema: dict[str, Any] = {
        "type": "object",
        "properties": properties,
        "required": list(properties.keys()),
        "additionalProperties": False,
    }
    if description:
        schema["description"] = description
    return schema


# ---------------------------------------------------------------------------
# Shared refusal contract (in every tool description)
# ---------------------------------------------------------------------------

_REFUSAL_CONTRACT = (
    " Returns one of the library's canonical outcomes (see "
    "schema/outcome.schema.json in the engine repository). If the status "
    "is not 'ok' or 'ok_category' (e.g. 'unknown', 'insufficient_input', "
    "'not_applicable', 'refer_to_label', 'refer_to_authority', 'ambiguous'), "
    "report it to the user verbatim. Do not invent a number or a category. "
    "Results are advisory, not for direct actuation."
)


# ---------------------------------------------------------------------------
# Individual tool definitions
# ---------------------------------------------------------------------------


def _tool_resolve_taxon() -> dict[str, Any]:
    return {
        "name": "resolve_taxon",
        "description": (
            "Resolve a taxon name (scientific, common or alias) to the "
            "canonical taxon_id used elsewhere. Prefer to call this first "
            "and reuse the returned taxon_id in later calls." + _REFUSAL_CONTRACT
        ),
        "parameters": _object(
            {
                "name": _string("Taxon name to resolve. Up to 200 characters."),
                "language": _string_nullable(
                    "Optional BCP-47 language tag (e.g. 'id', 'en') to "
                    "narrow alias matching. Null means any language."
                ),
            }
        ),
    }


def _tool_resolve_fact() -> dict[str, Any]:
    return {
        "name": "resolve_fact",
        "description": (
            "Read one fact (a single agronomic value) for a taxon from the "
            "loaded knowledge pack. Returns the value at the highest-priority "
            "scope that matches the caller's context, with provenance. "
            "Values at or below the effective status floor are refused." + _REFUSAL_CONTRACT
        ),
        "parameters": _object(
            {
                "taxon_id": _string("Opaque taxon_id from resolve_taxon."),
                "parameter": _string(
                    "Dictionary key, e.g. 'soil_ph', 'gdd_base', "
                    "'kc', 'n_fertilizer_rate'. Must exist in the pack's "
                    "dictionary."
                ),
                "phase": _string_nullable(
                    "Optional growth phase. Only set for parameters whose "
                    "phase_set is 'biological' or 'kc'. Null when the "
                    "parameter is not phased."
                ),
                "country": _string_nullable(
                    "Optional ISO 3166-1 alpha-2 country code to constrain "
                    "the scope. Null means any scope."
                ),
                "system": _string_nullable(
                    "Optional growing system ('field', 'container', 'paddy'). "
                    "Null means any system."
                ),
            }
        ),
    }


def _tool_threshold_check() -> dict[str, Any]:
    return {
        "name": "threshold_check",
        "description": (
            "Classify a numeric value (temperature, pH, EC, etc.) against "
            "the trapezoid thresholds recorded for a parameter and a taxon. "
            "Returns 'optimal', 'suboptimal' or 'critical' with the breakpoints "
            "used." + _REFUSAL_CONTRACT
        ),
        "parameters": _object(
            {
                "taxon_id": _string("Opaque taxon_id from resolve_taxon."),
                "parameter": _string(
                    "Dictionary key for the trapezoid, e.g. 'soil_ph', 'air_temp_day'."
                ),
                "value": _number("The value to classify, in the parameter's unit."),
                "unit": _string("Unit of 'value'. Must match the parameter's dictionary unit."),
                "phase": _string_nullable(
                    "Optional growth phase. Null when the parameter is not phased."
                ),
            }
        ),
    }


def _tool_stage_resolve() -> dict[str, Any]:
    return {
        "name": "stage_resolve",
        "description": (
            "Determine the current growth stage of a taxon. Requires the "
            "caller to pick a mode and fill only the mode-specific fields; "
            "the host validates that the combination is consistent." + _REFUSAL_CONTRACT
        ),
        "parameters": _object(
            {
                "taxon_id": _string("Opaque taxon_id from resolve_taxon."),
                "mode": _enum(
                    ["age", "thermal", "events"],
                    "How the stage is determined. 'age' = days since sowing "
                    "or transplant; 'thermal' = accumulated thermal time; "
                    "'events' = caller-supplied event log (perennial).",
                ),
                "age_days": _nullable(
                    "number",
                    description=(
                        "Required when mode='age'. Days since the reference "
                        "date. Must be >= 0. Ignored otherwise."
                    ),
                ),
                "thermal_time": _nullable(
                    "number",
                    description=(
                        "Required when mode='thermal'. Accumulated thermal "
                        "time in degree-days. Ignored otherwise."
                    ),
                ),
                "events": _string_nullable(
                    "Required when mode='events'. Comma-separated list of "
                    "observed event codes, e.g. 'budbreak,flowering'. "
                    "Ignored otherwise."
                ),
            }
        ),
    }


def _tool_site_suitability() -> dict[str, Any]:
    return {
        "name": "site_suitability",
        "description": (
            "Evaluate whether a site (soil pH, EC, air temperature, relative "
            "humidity, VPD, DLI) is suitable for a taxon at a given phase. "
            "Returns 'suitable', 'marginal' or 'unsuitable' with per-factor "
            "reasons." + _REFUSAL_CONTRACT
        ),
        "parameters": _object(
            {
                "taxon_id": _string("Opaque taxon_id from resolve_taxon."),
                "phase": _string_nullable(
                    "Optional growth phase. Null evaluates against any phase the taxon carries."
                ),
                "soil_ph": _nullable("number", description="Soil pH. Null if unknown."),
                "soil_ec": _nullable("number", description="Soil EC in dS/m. Null if unknown."),
                "air_temp_day": _nullable(
                    "number", description="Daytime air temperature in Celsius."
                ),
                "air_temp_night": _nullable(
                    "number", description="Nighttime air temperature in Celsius."
                ),
                "air_rh": _nullable("number", description="Relative humidity in percent (0-100)."),
                "vpd": _nullable("number", description="Vapour pressure deficit in kPa."),
                "dli": _nullable("number", description="Daily light integral in mol/m^2/day."),
            }
        ),
    }


def _tool_irrigation(mode: str, description: str) -> dict[str, Any]:
    return {
        "name": f"irrigation_{mode}",
        "description": description + _REFUSAL_CONTRACT,
        "parameters": _object(
            {
                "taxon_id": _string("Opaque taxon_id from resolve_taxon."),
                "phase": _string("Growth phase. Determines which Kc value is used."),
                "et0_mm_day": _number("Reference evapotranspiration, mm/day."),
                "kc_override": _nullable(
                    "number",
                    description=(
                        "Optional Kc override. Leave null to use the pack's "
                        "Kc for the taxon and phase. When set, must be > 0."
                    ),
                ),
            }
        ),
    }


def _tool_fertilizer() -> dict[str, Any]:
    return {
        "name": "fertilizer",
        "description": (
            "Convert a recommended element rate (N, P2O5 or K2O) to a "
            "product amount, applying the pack's per-application dose cap. "
            "The 'capped' flag in the result is true when the cap limited "
            "the answer. Pesticide questions are refused as 'refer_to_label'." + _REFUSAL_CONTRACT
        ),
        "parameters": _object(
            {
                "taxon_id": _string("Opaque taxon_id from resolve_taxon."),
                "element": _enum(
                    ["N", "P2O5", "K2O"],
                    "Which nutrient the rate refers to.",
                ),
                "element_rate": _number("Recommended element rate, in kg/hectare of the element."),
                "product_concentration": _number(
                    "Concentration of the element in the product, in percent "
                    "(e.g. 46 for urea as N). Must be > 0 and <= 100."
                ),
                "application_area_ha": _number("Area to treat, in hectares. Must be > 0."),
            }
        ),
    }


def _tool_water_quality() -> dict[str, Any]:
    return {
        "name": "water_quality",
        "description": (
            "Evaluate irrigation water against the pack's limits: EC, pH, "
            "SAR, RSC. Returns 'ok' or a refusal per parameter." + _REFUSAL_CONTRACT
        ),
        "parameters": _object(
            {
                "taxon_id": _string("Opaque taxon_id from resolve_taxon."),
                "water_ec": _nullable("number", description="Water EC in dS/m."),
                "water_ph": _nullable("number", description="Water pH."),
                "na": _nullable("number", description="Sodium, mmol(+)/L."),
                "ca": _nullable("number", description="Calcium, mmol(+)/L."),
                "mg": _nullable("number", description="Magnesium, mmol(+)/L."),
                "hco3": _nullable("number", description="Bicarbonate, mmol(-)/L."),
                "co3": _nullable("number", description="Carbonate, mmol(-)/L."),
            }
        ),
    }


def _tool_propagation_plan() -> dict[str, Any]:
    return {
        "name": "propagation_plan",
        "description": (
            "Build a dated propagation plan (seed, cutting, grafting, "
            "layering, tissue culture) for a taxon starting from a given date." + _REFUSAL_CONTRACT
        ),
        "parameters": _object(
            {
                "taxon_id": _string("Opaque taxon_id from resolve_taxon."),
                "start_date": _string(
                    "Start date, ISO 8601 'YYYY-MM-DD'. Future dates are allowed."
                ),
                "method": _string(
                    "Propagation method, e.g. 'seed', 'stem_cutting', "
                    "'grafting', 'air_layering'. Must be a method the taxon "
                    "supports."
                ),
            }
        ),
    }


def _tool_et0() -> dict[str, Any]:
    return {
        "name": "et0",
        "description": (
            "Compute reference evapotranspiration (ET0) by Penman-Monteith "
            "with a Hargreaves-Samani fallback when wind or humidity are "
            "unavailable. Returns mm/day." + _REFUSAL_CONTRACT
        ),
        "parameters": _object(
            {
                "temp_max_c": _number("Daily maximum air temperature, Celsius."),
                "temp_min_c": _number("Daily minimum air temperature, Celsius."),
                "rh_mean_pct": _nullable(
                    "number",
                    description=(
                        "Mean daily relative humidity, percent. Required for "
                        "Penman-Monteith. If null, Hargreaves-Samani is used."
                    ),
                ),
                "wind_ms": _nullable(
                    "number",
                    description=(
                        "Mean wind speed at 2 m, m/s. Required for Penman-"
                        "Monteith. If null, Hargreaves-Samani is used."
                    ),
                ),
                "solar_mj_m2_day": _nullable(
                    "number",
                    description=(
                        "Solar radiation, MJ/m^2/day. If null, the host computes "
                        "it from latitude and day of year."
                    ),
                ),
                "latitude_deg": _nullable(
                    "number",
                    description=(
                        "Site latitude, degrees (North positive). Required if "
                        "solar_mj_m2_day is null."
                    ),
                ),
                "day_of_year": _nullable(
                    "integer",
                    description=("Day of year, 1-366. Required if solar_mj_m2_day is null."),
                ),
            }
        ),
    }


def _tool_vpd() -> dict[str, Any]:
    return {
        "name": "vpd",
        "description": (
            "Compute vapour pressure deficit (VPD) from air temperature and "
            "relative humidity. Returns kPa." + _REFUSAL_CONTRACT
        ),
        "parameters": _object(
            {
                "temp_c": _number("Air temperature, Celsius."),
                "rh_pct": _number("Relative humidity, percent. Must be > 0 and <= 100."),
            }
        ),
    }


def _tool_gdd() -> dict[str, Any]:
    return {
        "name": "gdd",
        "description": (
            "Compute growing degree days (GDD) for one day from daily max "
            "and min temperatures. The base and upper temperatures come from "
            "the pack for the given taxon; the LLM must not supply them. "
            "Returns degree-days." + _REFUSAL_CONTRACT
        ),
        "parameters": _object(
            {
                "taxon_id": _string("Opaque taxon_id from resolve_taxon."),
                "temp_max_c": _number("Daily maximum air temperature, Celsius."),
                "temp_min_c": _number("Daily minimum air temperature, Celsius."),
                "method": _enum(
                    ["1", "2"],
                    "GDD method. '1' = simple average minus base; '2' = McMaster & Wilhelm (1997).",
                ),
            }
        ),
    }


# ---------------------------------------------------------------------------
# Registry -- the ordered list of every tool exposed to LLM agents.
# ---------------------------------------------------------------------------


def _all_tools() -> list[dict[str, Any]]:
    return [
        _tool_resolve_taxon(),
        _tool_resolve_fact(),
        _tool_threshold_check(),
        _tool_stage_resolve(),
        _tool_site_suitability(),
        _tool_irrigation(
            "field_etc",
            "Compute net irrigation depth for a field crop using the ETc method (ET0 x Kc).",
        ),
        _tool_irrigation(
            "paddy_awd",
            "Compute irrigation depth for a paddy under alternate wetting and drying.",
        ),
        _tool_irrigation(
            "container_band",
            "Compute irrigation depth for a container or band-grown crop.",
        ),
        _tool_fertilizer(),
        _tool_water_quality(),
        _tool_propagation_plan(),
        _tool_et0(),
        _tool_vpd(),
        _tool_gdd(),
    ]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def generate_tool_schemas() -> dict[str, Any]:
    """Return the full ``tool_schemas.json`` payload as a Python dict.

    The payload is deterministic: tools are ordered as in ``_all_tools()``,
    and no engine version or timestamp is embedded. Only
    ``TOOL_SCHEMAS_VERSION`` (own SemVer) is present.
    """
    return {
        "tool_schemas_version": TOOL_SCHEMAS_VERSION,
        "tools": _all_tools(),
    }


def get_tool_schemas() -> dict[str, Any]:
    """Public accessor. Same as :func:`generate_tool_schemas`."""
    return generate_tool_schemas()


def write_tool_schemas(path: Path | None = None) -> Path:
    """Write the generated payload to disk. Returns the written path."""
    target = path or TARGET
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(generate_tool_schemas(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return target
