"""License allowlist drift test (ADR-005, post-#115).

The allowlist of commercial-use license IDs lives in three places that
must stay in sync:

1. ``src/agri_core/registry/sources.py`` — the runtime source of truth
   (``_ALLOWED_LICENSES`` for sources, ``_ALLOWED_LICENSES_DATASET`` for
   datasets, which excludes ``LicenseRef-PublicDomain``).
2. ``docs/decisions/ADR-005-license-allowlist.md`` §Decision — the
   normative contract.
3. ``CONTRIBUTING.md`` §Data source license policy — what contributors
   are told to follow.

A change to any of them without the other two is drift, and drift in a
license gate is a silent policy violation. This file makes "add, remove
or rename an allowlist ID" fail unless all three move together.

Section-scoped, not file-wide: ADR-005 §Context mentions example IDs
(``MIT OR Apache-2.0``) that are not themselves allowlist entries.
File-wide substring checks would pass even if §Decision were emptied;
this test extracts the exact section.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from agri_core.registry.sources import _ALLOWED_LICENSES, _ALLOWED_LICENSES_DATASET

pytestmark = pytest.mark.contract

_ADR_005 = "docs/decisions/ADR-005-license-allowlist.md"
_CONTRIBUTING = "CONTRIBUTING.md"
_REPO_ROOT = Path(__file__).resolve().parents[2]


def _extract_section(text: str, heading: str) -> str:
    """Return the body of ``heading`` up to the next ``##`` heading.

    Fails loudly if the heading is absent, so a renamed heading is caught
    by the test rather than silently reducing coverage.
    """
    lines = text.splitlines()
    start = None
    for i, line in enumerate(lines):
        if line.strip() == heading:
            start = i + 1
            break
    if start is None:
        pytest.fail(
            f"heading not found: {heading!r}. If the heading was renamed, "
            f"update this test together with the document."
        )
    end = len(lines)
    for j in range(start, len(lines)):
        if lines[j].startswith("## "):
            end = j
            break
    return "\n".join(lines[start:end])


def _read(relpath: str) -> str:
    return (_REPO_ROOT / relpath).read_text(encoding="utf-8")


def test_allowed_licenses_shape() -> None:
    """``_ALLOWED_LICENSES`` is a frozenset of exactly 8 IDs."""
    assert isinstance(_ALLOWED_LICENSES, frozenset)
    assert len(_ALLOWED_LICENSES) == 8, (
        f"expected 8 allowlist IDs, found {len(_ALLOWED_LICENSES)}: "
        f"{sorted(_ALLOWED_LICENSES)}. Update ADR-005 and CONTRIBUTING "
        f"in the same change."
    )


def test_allowed_licenses_dataset_invariant() -> None:
    """The dataset allowlist is the source allowlist minus PD."""
    assert _ALLOWED_LICENSES - {"LicenseRef-PublicDomain"} == _ALLOWED_LICENSES_DATASET
    assert len(_ALLOWED_LICENSES_DATASET) == 7


def test_adr_005_decision_lists_every_allowed_license() -> None:
    """Every runtime allowlist ID appears in ADR-005 §Decision."""
    section = _extract_section(_read(_ADR_005), "## Decision")
    missing = sorted(lic for lic in _ALLOWED_LICENSES if lic not in section)
    assert not missing, (
        f"ADR-005 §Decision is missing allowlist IDs: {missing}. "
        f"Add them to §Decision, not §Context."
    )


def test_contributing_lists_every_allowed_license() -> None:
    """Every runtime allowlist ID appears in CONTRIBUTING §Data source license policy."""
    section = _extract_section(_read(_CONTRIBUTING), "## Data source license policy")
    missing = sorted(lic for lic in _ALLOWED_LICENSES if lic not in section)
    assert not missing, (
        f"CONTRIBUTING.md §Data source license policy is missing allowlist IDs: {missing}. "
        f"Add them alongside the other IDs."
    )
