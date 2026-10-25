"""dictionary.lock + history snapshot contract."""

from __future__ import annotations

import json
import re
from itertools import pairwise
from pathlib import Path

import pytest
from packaging.version import Version

from agri_core.models.dictionary import (
    classify_change,
    contract_hash,
    load_bundle_from_root,
)

pytestmark = pytest.mark.contract

ROOT = Path(__file__).resolve().parents[2]
DICT = ROOT / "dictionary"
LOCK = DICT / "dictionary.lock"
HISTORY = DICT / "history"
LOCK_RE = re.compile(r"^(\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?) ([0-9a-f]{64})$")
SNAPSHOT_NAME_RE = re.compile(r"^\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?\.json$")


def _parse_lock(text: str) -> list[tuple[str, str]]:
    entries: list[tuple[str, str]] = []
    for line in text.rstrip("\n").split("\n"):
        if not line.strip():
            continue
        m = LOCK_RE.match(line)
        if m is None:
            raise AssertionError(f"lock line not matched: {line!r}")
        entries.append((m.group(1), m.group(2)))
    return entries


def _load_snapshot(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _all_snapshots() -> list[tuple[str, dict]]:
    pairs = [(_load_snapshot(p)["version"], _load_snapshot(p)) for p in HISTORY.glob("*.json")]
    return sorted(pairs, key=lambda p: Version(p[0]))


@pytest.fixture(scope="module")
def lock_entries() -> list[tuple[str, str]]:
    return _parse_lock(LOCK.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def current_bundle() -> dict:
    return load_bundle_from_root(DICT)


def test_lock_exists() -> None:
    assert LOCK.is_file()


def test_lock_well_formed(lock_entries: list[tuple[str, str]]) -> None:
    assert len(lock_entries) >= 1
    for version, h in lock_entries:
        Version(version)
        assert re.fullmatch(r"[0-9a-f]{64}", h)


def test_lock_no_extra_content() -> None:
    text = LOCK.read_text(encoding="utf-8")
    assert text.endswith("\n")
    body = text.rstrip("\n")
    assert "\n\n" not in body
    for line in body.split("\n"):
        assert LOCK_RE.match(line), f"lock line malformed: {line!r}"


def test_lock_versions_sorted(lock_entries: list[tuple[str, str]]) -> None:
    versions = [Version(v) for v, _ in lock_entries]
    assert versions == sorted(versions)


def test_lock_no_duplicate_versions(lock_entries: list[tuple[str, str]]) -> None:
    versions = [v for v, _ in lock_entries]
    assert len(versions) == len(set(versions))


def test_lock_last_is_current_version(
    lock_entries: list[tuple[str, str]], current_bundle: dict
) -> None:
    last_version, last_hash = lock_entries[-1]
    assert current_bundle["version"] == last_version
    assert contract_hash(current_bundle) == last_hash


def test_history_dir_exists() -> None:
    assert HISTORY.is_dir()


def test_history_contains_only_versioned_snapshots() -> None:
    for p in HISTORY.glob("*.json"):
        assert SNAPSHOT_NAME_RE.match(p.name), f"unexpected file in history/: {p.name!r}"


def test_every_lock_version_has_snapshot(lock_entries: list[tuple[str, str]]) -> None:
    for version, _ in lock_entries:
        assert (HISTORY / f"{version}.json").is_file(), f"missing snapshot {version}.json"


def test_every_snapshot_matches_lock_hash(lock_entries: list[tuple[str, str]]) -> None:
    lock = {v: h for v, h in lock_entries}
    for p in HISTORY.glob("*.json"):
        snap = _load_snapshot(p)
        v = snap["version"]
        assert v in lock, f"snapshot {p.name} version {v!r} not in lock"
        assert contract_hash(snap) == lock[v], f"snapshot {p.name} hash != lock"


def test_snapshot_latest_matches_current(current_bundle: dict) -> None:
    snaps = _all_snapshots()
    latest_version, latest = snaps[-1]
    assert latest_version == current_bundle["version"]
    assert contract_hash(latest) == contract_hash(current_bundle)


def test_introduced_in_matches_first_snapshot(
    lock_entries: list[tuple[str, str]], current_bundle: dict
) -> None:
    snaps = _all_snapshots()
    first: dict[str, str] = {}
    for version, snap in snaps:
        for key in snap["parameters"]:
            first.setdefault(key, version)
    for key, param in current_bundle["parameters"].items():
        assert key in first, f"{key} not in any snapshot"
        assert param["introduced_in"] == first[key], (
            f"{key}.introduced_in={param['introduced_in']!r} but first snapshot is {first[key]!r}"
        )


def test_semver_compat(lock_entries: list[tuple[str, str]]) -> None:
    snaps = _all_snapshots()
    if len(snaps) < 2:
        pytest.skip("need at least 2 snapshots to test SemVer compat")
    rank = {"PATCH": 0, "MINOR": 1, "MAJOR": 2}
    for (old_v, old), (new_v, new) in pairwise(snaps):
        required = classify_change(old, new)
        old_version, new_version = Version(old_v), Version(new_v)
        if new_version.major > old_version.major:
            declared = "MAJOR"
        elif new_version.minor > old_version.minor:
            declared = "MINOR"
        else:
            declared = "PATCH"
        assert rank[declared] >= rank[required], (
            f"{old_v} -> {new_v}: declared {declared}, classify requires {required}"
        )
