"""ADR index consistency in README §Decision records."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.contract

ROOT = Path(__file__).resolve().parents[2]
README = ROOT / "README.md"
ADR_DIR = ROOT / "docs" / "decisions"

_ADR_LINK = re.compile(r"\[ADR-(\d+)\]\(docs/decisions/ADR-\d+-[^)]+\.md\)")
_ADR_FILE_NUM = re.compile(r"ADR-(\d+)")


@pytest.fixture(scope="module")
def readme_text() -> str:
    return README.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def decision_section(readme_text: str) -> str:
    m = re.search(
        r"### Decision records\n(.*?)(?=\n### |\n## |\Z)",
        readme_text,
        re.DOTALL,
    )
    assert m, "README has no '### Decision records' section"
    return m.group(1)


def _linked_adrs(section: str) -> set[str]:
    return set(_ADR_LINK.findall(section))


def _adr_file_nums() -> set[str]:
    nums: set[str] = set()
    for p in ADR_DIR.glob("ADR-*.md"):
        m = _ADR_FILE_NUM.search(p.name)
        if m:
            nums.add(m.group(1))
    return nums


def test_decision_records_section_exists(decision_section: str) -> None:
    assert decision_section.strip(), "§Decision records section is empty"


def test_every_adr_file_is_referenced(decision_section: str) -> None:
    missing = _adr_file_nums() - _linked_adrs(decision_section)
    assert not missing, (
        f"ADR files not linked in README §Decision records: {sorted('ADR-' + m for m in missing)}"
    )


def test_every_link_has_file(decision_section: str) -> None:
    orphan = _linked_adrs(decision_section) - _adr_file_nums()
    assert not orphan, (
        f"ADR links in README with no file under docs/decisions/: "
        f"{sorted('ADR-' + m for m in orphan)}"
    )


def test_no_duplicate_adr_references(decision_section: str) -> None:
    refs = _ADR_LINK.findall(decision_section)
    dupes = {r for r in refs if refs.count(r) > 1}
    assert not dupes, f"duplicate ADR references: {sorted('ADR-' + d for d in dupes)}"


def test_each_link_has_description(decision_section: str) -> None:
    for line in decision_section.splitlines():
        if not line.strip().startswith("- "):
            continue
        if not _ADR_LINK.search(line):
            continue
        assert " — " in line, f"ADR entry missing ' — description': {line!r}"
        _, _, desc = line.partition(" — ")
        assert desc.strip(), f"empty description after ' — ': {line!r}"


def test_section_placement(readme_text: str) -> None:
    """§Decision records sits between §Versioning and releases and §Milestones."""
    vr = readme_text.find("## Versioning and releases")
    dr = readme_text.find("### Decision records")
    ms = readme_text.find("## Milestones")
    assert vr != -1, "missing §Versioning and releases"
    assert dr != -1, "missing §Decision records"
    assert ms != -1, "missing §Milestones"
    assert vr < dr < ms, f"expected Versioning ({vr}) < Decision records ({dr}) < Milestones ({ms})"


def test_adr_008_gap_documented(decision_section: str) -> None:
    """If ADR-008 file is missing, the gap must be explained in prose."""
    if "8" in _adr_file_nums():
        return
    assert "ADR-008" in decision_section, (
        "ADR-008 file missing but §Decision records doesn't explain the gap"
    )
