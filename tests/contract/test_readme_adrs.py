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


# ---- ADR-NNN §M section reference gate (added D1, M21 Phase G4) ----


_ADR_SECTION_REF = re.compile(r"ADR-(\d+)\s*((?:§\d+(?:\s*,\s*§\d+)*))")
_ADR_SECTION_NUM = re.compile(r"§(\d+)")
_ADR_HEADING = re.compile(r"^### (\d+)\.", re.MULTILINE)


def _adr_files_by_num() -> dict[str, Path]:
    out: dict[str, Path] = {}
    for p in ADR_DIR.glob("ADR-*.md"):
        m = _ADR_FILE_NUM.search(p.name)
        if m:
            out[m.group(1)] = p
    return out


def _section_nums_in(adr_path: Path) -> set[str]:
    return set(_ADR_HEADING.findall(adr_path.read_text(encoding="utf-8")))


def _all_section_refs() -> list[tuple[Path, int, str, list[str]]]:
    """Yield (source_file, line, adr_num, [section_nums]) for every ref."""
    adr_files_by_num = _adr_files_by_num()
    refs: list[tuple[Path, int, str, list[str]]] = []
    files = [
        *list((ROOT / "docs").rglob("*.md")),
        ROOT / "CHANGELOG.md",
        ROOT / "README.md",
    ]
    for f in files:
        if f.name == "ADR-019-rust-native-kernel.md":
            # Skip self-references inside ADR-019 (§4, §5 appear in prose
            # describing the amendment itself, not as external pointers).
            continue
        try:
            text = f.read_text(encoding="utf-8")
        except OSError:
            continue
        for i, line in enumerate(text.splitlines(), start=1):
            for m in _ADR_SECTION_REF.finditer(line):
                adr_num = m.group(1)
                if adr_num not in adr_files_by_num:
                    continue
                secs = _ADR_SECTION_NUM.findall(m.group(2))
                refs.append((f, i, adr_num, secs))
    return refs


def test_adr_section_refs_point_to_existing_headings() -> None:
    """Every `ADR-NNN §M` or `ADR-NNN §M, §N` in docs/README/CHANGELOG
    must point to an existing `### M.` heading in that ADR file.

    Retroactive gate added D1 (M21 Phase G4). Closes the class of error
    that produced d0610a1's "Documented in ADR-019 §10" claim while §10
    did not exist.
    """
    adr_files = _adr_files_by_num()
    failures: list[str] = []
    for src, line_no, adr_num, secs in _all_section_refs():
        existing = _section_nums_in(adr_files[adr_num])
        missing = [s for s in secs if s not in existing]
        if missing:
            rel = src.relative_to(ROOT)
            existing_str = ", ".join(f"§{s}" for s in sorted(existing)) or "none"
            failures.append(
                f"{rel}:{line_no} references ADR-{adr_num} "
                f"§{', §'.join(missing)} but ADR-{adr_num} has no "
                f"such section(s) (existing: {existing_str})"
            )
    assert not failures, "ADR section references point to missing headings:\n" + "\n".join(failures)


def test_adr_019_sections_contiguous() -> None:
    """ADR-019 numbered subsections must be contiguous 1..N with no gaps.

    Guards against silently skipping a section (the A1b claim referenced
    §10 while only §1-§9 existed). New sections must extend the tail, not
    insert gaps.
    """
    nums = _section_nums_in(ADR_DIR / "ADR-019-rust-native-kernel.md")
    if not nums:
        pytest.skip("ADR-019 has no numbered subsections yet")
    ints = sorted(int(n) for n in nums)
    assert ints == list(range(1, ints[-1] + 1)), (
        f"ADR-019 numbered sections are not contiguous: got {ints}, "
        f"expected 1..{ints[-1]} with no gaps"
    )
