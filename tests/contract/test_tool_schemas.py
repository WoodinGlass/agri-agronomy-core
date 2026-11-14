"""Contract tests for the tool schemas export (M16).

Locks the strict-compatible subset required by OpenAI and Anthropic tool-
calling APIs. Every tool is validated against Draft 2020-12, no forbidden
keywords leak in, no host-only parameter leaks in, and the committed
``schema/tool_schemas.json`` matches the generator byte-for-byte.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from agri_core.export.tool_schemas import (
    TOOL_SCHEMAS_VERSION,
    generate_tool_schemas,
)

pytestmark = pytest.mark.contract

REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = REPO_ROOT / "schema" / "tool_schemas.json"

EXPECTED_TOOLS = {
    "resolve_taxon",
    "resolve_fact",
    "threshold_check",
    "stage_resolve",
    "site_suitability",
    "irrigation_field_etc",
    "irrigation_paddy_awd",
    "irrigation_container_band",
    "fertilizer",
    "water_quality",
    "propagation_plan",
    "et0",
    "vpd",
    "gdd",
}

#: Keywords rejected by OpenAI strict or Anthropic strict tool-calling.
FORBIDDEN_KEYWORDS = frozenset({
    "oneOf",
    "allOf",
    "discriminator",
    "minimum",
    "maximum",
    "exclusiveMinimum",
    "exclusiveMaximum",
    "minLength",
    "maxLength",
    "pattern",
    "format",
    "$ref",
    "$defs",
    "const",
})

#: Parameters the host injects; the LLM must not be able to set them.
HOST_ONLY = frozenset({"pack", "min_status", "require_commercial"})


@pytest.fixture(scope="module")
def schema() -> dict[str, Any]:
    assert SCHEMA_PATH.is_file(), (
        f"{SCHEMA_PATH} is missing. Regenerate it with "
        "`python -m agri_core.cli export --pack sample "
        "--format tool_schemas --out schema`."
    )
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def _walk(obj: Any, path: str = "") -> list[tuple[str, str]]:
    """Yield ``(key, path)`` for every dict key in the tree."""
    found: list[tuple[str, str]] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            found.append((k, path or "<root>"))
            found.extend(_walk(v, f"{path}.{k}"))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            found.extend(_walk(v, f"{path}[{i}]"))
    return found


# ---- structure ----------------------------------------------------------


def test_schema_file_exists() -> None:
    assert SCHEMA_PATH.is_file()


def test_version_matches_module(schema: dict[str, Any]) -> None:
    assert schema["tool_schemas_version"] == TOOL_SCHEMAS_VERSION


def test_exactly_expected_tools(schema: dict[str, Any]) -> None:
    names = {t["name"] for t in schema["tools"]}
    assert names == EXPECTED_TOOLS, (
        f"tool set mismatch: missing={EXPECTED_TOOLS - names} "
        f"extra={names - EXPECTED_TOOLS}"
    )


def test_tool_count_is_14(schema: dict[str, Any]) -> None:
    assert len(schema["tools"]) == 14


def test_every_tool_has_required_fields(schema: dict[str, Any]) -> None:
    for tool in schema["tools"]:
        assert "name" in tool
        assert "description" in tool
        assert "parameters" in tool
        assert isinstance(tool["description"], str)
        assert tool["description"], "empty description"
        assert "parameters" in tool


def test_tool_names_match_regex(schema: dict[str, Any]) -> None:
    import re
    pattern = re.compile(r"^[a-z][a-z0-9_]{0,62}$")
    for tool in schema["tools"]:
        assert pattern.match(tool["name"]), f"bad name: {tool['name']!r}"


# ---- strict subset ------------------------------------------------------


def test_no_forbidden_keywords(schema: dict[str, Any]) -> None:
    for tool in schema["tools"]:
        for key, path in _walk(tool, tool["name"]):
            assert key not in FORBIDDEN_KEYWORDS, (
                f"forbidden keyword {key!r} at {path} in {tool['name']!r}"
            )


def test_additional_properties_false(schema: dict[str, Any]) -> None:
    for tool in schema["tools"]:
        params = tool["parameters"]
        assert params.get("type") == "object", (
            f"{tool['name']}: parameters.type must be 'object'"
        )
        assert params.get("additionalProperties") is False, (
            f"{tool['name']}: additionalProperties must be false"
        )


def test_required_equals_properties(schema: dict[str, Any]) -> None:
    for tool in schema["tools"]:
        params = tool["parameters"]
        prop_keys = set(params["properties"].keys())
        required = set(params["required"])
        assert prop_keys == required, (
            f"{tool['name']}: required={required - prop_keys} "
            f"missing_in_required={prop_keys - required}"
        )


def test_all_properties_have_description(schema: dict[str, Any]) -> None:
    for tool in schema["tools"]:
        props = tool["parameters"]["properties"]
        for prop_name, prop in props.items():
            assert "description" in prop, (
                f"{tool['name']}.{prop_name}: missing description"
            )
            assert isinstance(prop["description"], str)
            assert prop["description"], (
                f"{tool['name']}.{prop_name}: empty description"
            )


# ---- security: no host-only leaks ---------------------------------------


def test_no_host_only_parameters(schema: dict[str, Any]) -> None:
    for tool in schema["tools"]:
        props = set(tool["parameters"]["properties"].keys())
        leak = props & HOST_ONLY
        assert not leak, (
            f"{tool['name']}: leaks host-only parameters {sorted(leak)}"
        )


def test_gdd_has_no_taxon_specific_rates(schema: dict[str, Any]) -> None:
    gdd = next(t for t in schema["tools"] if t["name"] == "gdd")
    props = gdd["parameters"]["properties"]
    assert "taxon_id" in props, "gdd must accept taxon_id"
    assert "base_c" not in props, "gdd must not accept LLM-supplied base_c"
    assert "upper_c" not in props, "gdd must not accept LLM-supplied upper_c"


def test_no_status_enum_in_input(schema: dict[str, Any]) -> None:
    """Tool schemas are input only; no ``status`` field should appear."""
    for tool in schema["tools"]:
        props = tool["parameters"]["properties"]
        if "status" in props:
            raise AssertionError(
                f"{tool['name']}: 'status' must not be an input parameter"
            )


# ---- JSON Schema 2020-12 validity ---------------------------------------


def test_draft_2020_12_validator(schema: dict[str, Any]) -> None:
    jsonschema = pytest.importorskip("jsonschema")
    validator_cls = jsonschema.Draft202012Validator
    for tool in schema["tools"]:
        validator_cls.check_schema(tool["parameters"])


# ---- drift --------------------------------------------------------------


def test_committed_schema_matches_generator(schema: dict[str, Any]) -> None:
    regenerated = generate_tool_schemas()
    assert schema == regenerated, (
        "schema/tool_schemas.json is out of date. Regenerate it with "
        "`python -m agri_core.cli export --pack sample "
        "--format tool_schemas --out schema` and commit the result."
    )
