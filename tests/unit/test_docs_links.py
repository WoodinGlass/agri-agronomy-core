"""Relative-link check for docs/*.md and README.md (M9 PR-C).

Every relative Markdown link must resolve to an existing file. Anchors on
README.md are additionally checked against the headings in that file;
anchor checks for other files are skipped because headings there may
contain punctuation (backticks, dots) whose GitHub slugification is
non-obvious and not part of this release's contract.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_REPO_ROOT = Path(__file__).resolve().parents[2]


def _iter_markdown() -> list[Path]:
    files = sorted((_REPO_ROOT / "docs").rglob("*.md"))
    files.append(_REPO_ROOT / "README.md")
    return files


def _relative_links(md_path: Path) -> list[str]:
    """Extract link targets from ``[text](target)`` occurrences.

    Walks the text with ``str.find`` instead of a regex so that backslashes
    in the Markdown source cannot trigger syntax warnings when this module
    is imported. Handles the common forms ``[text](path)``,
    ``[text](path "title")`` and inline ``![alt](path)``.
    """
    text = md_path.read_text(encoding="utf-8")
    links: list[str] = []
    i = 0
    while True:
        open_bracket = text.find("[", i)
        if open_bracket < 0:
            break
        close_bracket = text.find("](", open_bracket + 1)
        if close_bracket < 0:
            break
        close_paren = text.find(")", close_bracket + 2)
        if close_paren < 0:
            break
        raw = text[close_bracket + 2 : close_paren].strip()
        target = raw.split()[0] if raw else ""
        if target:
            links.append(target)
        i = close_paren + 1
    return links


def _slug(heading_text: str) -> str:
    """Approximate the GitHub slug for a single heading.

    Keeps alphanumerics, spaces and hyphens; everything else (backticks,
    dots, punctuation) is removed. Spaces collapse to hyphens.
    """
    kept = "".join(c if (c.isalnum() or c == " " or c == "-") else "" for c in heading_text)
    return "-".join(kept.strip().lower().split())


def _headings(md_path: Path) -> set[str]:
    slugs: set[str] = set()
    for raw in md_path.read_text(encoding="utf-8").splitlines():
        stripped = raw.strip()
        if not stripped.startswith("#"):
            continue
        # Drop the leading #s and one optional space.
        hash_count = 0
        while hash_count < len(stripped) and stripped[hash_count] == "#":
            hash_count += 1
        if hash_count == 0 or hash_count > 6:
            continue
        heading_text = stripped[hash_count:].strip()
        if heading_text:
            slugs.add(_slug(heading_text))
    return slugs


def test_all_relative_links_resolve() -> None:
    broken: list[str] = []
    for md in _iter_markdown():
        for target in _relative_links(md):
            if target.startswith(("http://", "https://", "mailto:", "tel:")):
                continue
            path_part = target.split("#")[0]
            if not path_part:
                continue
            resolved = (md.parent / path_part).resolve()
            if not resolved.exists():
                broken.append(f"{md.relative_to(_REPO_ROOT)}: {target}")
    assert not broken, "broken relative links:\n  " + "\n  ".join(broken)


def test_readme_anchors_resolve() -> None:
    """Every link that points at README.md#anchor must match a heading."""
    readme = (_REPO_ROOT / "README.md").resolve()
    readme_slugs = _headings(_REPO_ROOT / "README.md")
    assert readme_slugs, "no headings found in README.md"

    broken: list[str] = []
    for md in _iter_markdown():
        for target in _relative_links(md):
            if target.startswith(("http://", "https://", "mailto:", "tel:")):
                continue
            path_part, sep, anchor = target.partition("#")
            if not sep or not anchor:
                continue
            resolved_path = (md.parent / path_part).resolve() if path_part else md.resolve()
            if resolved_path != readme:
                continue
            if anchor not in readme_slugs:
                broken.append(f"{md.relative_to(_REPO_ROOT)}: #{anchor}")
    assert not broken, "broken README anchors:\n  " + "\n  ".join(broken)
