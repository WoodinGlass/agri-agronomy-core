"""Resolution policy version drift test (ADR-004).

The resolution policy version lives in two places that must stay in
sync:

1. ``src/agri_core/__init__.py`` -- ``RESOLUTION_POLICY_VERSION``
   (runtime source of truth).
2. ``docs/decisions/ADR-004-resolution-policy.md`` §"resolution policy
   version" (normative contract).

A change to one without the other is drift.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from agri_core import RESOLUTION_POLICY_VERSION

pytestmark = pytest.mark.contract

_ADR_004 = "docs/decisions/ADR-004-resolution-policy.md"
_REPO_ROOT = Path(__file__).resolve().parents[2]
_HEADING_PREFIX = "## Decision — resolution policy version"


def _extract_section(text: str, heading_prefix: str) -> str:
    """Return the body of the section starting with *heading_prefix*.

    Fails loudly if the heading is absent or if no ``## `` terminator is
    found (never returns ``""`` silently).
    """
    lines = text.splitlines()
    start = None
    for i, line in enumerate(lines):
        if line.startswith(heading_prefix):
            start = i + 1
            break
    if start is None:
        pytest.fail(f"heading not found: {heading_prefix!r}")
    end = len(lines)
    for j in range(start, len(lines)):
        if lines[j].startswith("## "):
            end = j
            break
    return "\n".join(lines[start:end]).strip()


def test_version_format() -> None:
    """``RESOLUTION_POLICY_VERSION`` is strict semver (X.Y.Z)."""
    assert re.fullmatch(r"\d+\.\d+\.\d+", RESOLUTION_POLICY_VERSION), (
        f"RESOLUTION_POLICY_VERSION {RESOLUTION_POLICY_VERSION!r} is not strict semver X.Y.Z"
    )


def test_version_in_adr_004() -> None:
    """The ADR section records the same version as code."""
    adr = (_REPO_ROOT / _ADR_004).read_text(encoding="utf-8")
    section = _extract_section(adr, _HEADING_PREFIX)
    m = re.search(
        r'RESOLUTION_POLICY_VERSION\s*=\s*"(\d+\.\d+\.\d+)"',
        section,
    )
    assert m is not None, (
        "ADR-004 section must contain "
        '`RESOLUTION_POLICY_VERSION = "X.Y.Z"`. '
        f"Section text starts with: {section[:200]!r}"
    )
    adr_version = m.group(1)
    assert adr_version == RESOLUTION_POLICY_VERSION, (
        f"drift: code={RESOLUTION_POLICY_VERSION!r} ADR-004={adr_version!r}"
    )


def test_metainfo_has_resolution_policy_version() -> None:
    """``MetaInfo`` exposes the resolution policy version."""
    from agri_core.registry.resolution import MetaInfo

    assert "resolution_policy_version" in MetaInfo.model_fields


def test_provenance_has_resolution_policy_version() -> None:
    """``Provenance`` exposes the resolution policy version with a default."""
    from agri_core.models.provenance import Provenance

    assert "resolution_policy_version" in Provenance.model_fields
    p = Provenance()
    assert p.resolution_policy_version == RESOLUTION_POLICY_VERSION
