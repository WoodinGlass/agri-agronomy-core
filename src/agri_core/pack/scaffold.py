"""Scaffold a new taxon into an existing source pack (M6-5).

Creates one new row in ``taxa.csv`` and a header-only
``facts/<taxon_id>.csv``. The taxon ID is opaque Crockford base32
(``T`` + 9 chars), generated randomly and never reused within the pack.
Does NOT touch ``pack.toml`` — if the pack declares a ``content_hash``,
it becomes stale after scaffold; re-lock with ``agri-core pack lock``.
"""

from __future__ import annotations

import contextlib
import os
import re
import secrets
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from importlib.resources import files as pkg_files
from pathlib import Path
from typing import Any

import yaml

from agri_core.models.ids import CROCKFORD_ALPHABET, TAXON_ID_PATTERN
from agri_core.pack.errors import PackError
from agri_core.pack.files import read_pack_bytes
from agri_core.pack.loader import parse_manifest_bytes
from agri_core.pack.tables import TABLES, read_table, write_table
from agri_core.pack.validate import validate_pack

__all__ = [
    "ScaffoldResult",
    "infer_organism_group",
    "scaffold_taxon",
]

_ID_RETRIES: int = 10
_TAXON_ID_RE = re.compile(TAXON_ID_PATTERN)


@dataclass(frozen=True)
class ScaffoldResult:
    """Outcome of a ``scaffold_taxon`` call."""

    source: Path
    taxon_id: str
    facts_path: Path
    content_hash_stale: bool


def _load_vocab(name: str) -> dict[str, Any]:
    """Load a vocab YAML from package data, falling back to repo source tree."""
    try:
        p = pkg_files("agri_core") / "_dictionary" / "vocab" / f"{name}.yaml"
        if p.is_file():
            data = yaml.safe_load(p.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                raise PackError(f"vocabulary {name!r} is not a mapping")
            return data
    except (FileNotFoundError, OSError, ModuleNotFoundError):
        pass
    repo_root = Path(__file__).resolve().parents[3]
    p = repo_root / "dictionary" / "vocab" / f"{name}.yaml"
    if not p.is_file():
        raise PackError(f"vocabulary {name!r} not found at {p}")
    data = yaml.safe_load(p.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise PackError(f"vocabulary {name!r} is not a mapping")
    return data


def _vocab_keys(name: str, top_key: str) -> frozenset[str]:
    data = _load_vocab(name)
    section = data.get(top_key)
    if not isinstance(section, dict):
        raise PackError(f"vocabulary {name!r}.{top_key} is not a mapping")
    return frozenset(str(k) for k in section)


def infer_organism_group(archetype: str) -> str:
    """Return the single organism group whose ``allowed_archetypes`` contains *archetype*."""
    data = _load_vocab("organism_groups")
    groups_raw = data.get("organism_groups")
    if not isinstance(groups_raw, dict):
        raise PackError("organism_groups.yaml: 'organism_groups' must be a mapping")
    matches: list[str] = []
    for group, spec in groups_raw.items():
        if not isinstance(spec, dict):
            continue
        allowed = spec.get("allowed_archetypes") or ()
        if archetype in allowed:
            matches.append(str(group))
    if len(matches) != 1:
        raise PackError(
            f"archetype {archetype!r} matches {len(matches)} organism groups "
            f"({sorted(matches)}); expected exactly 1"
        )
    return matches[0]


def _generate_taxon_id(existing: frozenset[str]) -> str:
    for _ in range(_ID_RETRIES):
        candidate = "T" + "".join(secrets.choice(CROCKFORD_ALPHABET) for _ in range(9))
        if candidate not in existing:
            return candidate
    raise PackError(
        f"cannot generate unique taxon_id after {_ID_RETRIES} attempts "
        f"(existing taxa: {len(existing)})"
    )


def _resolve_source_ids(srcs: Sequence[str] | None, files: Mapping[str, bytes]) -> tuple[str, ...]:
    """Resolve source ids: caller-provided, or first id in sources.csv."""
    if srcs is not None:
        return tuple(srcs)
    return (_default_source_id(files),)


def _default_source_id(files: Mapping[str, bytes]) -> str:
    """Return the first id from sources.csv (required when --src is not given)."""
    table = read_table(TABLES["sources"], files["sources.csv"], source_name="sources.csv")
    if not table.rows:
        raise PackError(
            "sources.csv is empty; scaffold needs at least one source id. "
            "Add a row, or use a pack that already has sources."
        )
    first = table.rows[0]
    sid = first.get("id")
    if not isinstance(sid, str) or not sid:
        raise PackError("sources.csv first row has no 'id' column value")
    return sid


def scaffold_taxon(
    source: Path,
    *,
    scientific_name: str,
    archetype: str,
    rank: str = "species",
    uses: Sequence[str],
    srcs: Sequence[str] | None = None,
) -> ScaffoldResult:
    """Scaffold one new taxon into *source*.

    - Validates the pack first; a broken pack is not mutated.
    - Writes ``taxa.csv`` (sorted by ``taxon_id``) and ``facts/<id>.csv``
      (header-only) atomically per file.
    - Does not touch ``pack.toml``; a declared ``content_hash`` will
      become stale, and is reported via ``ScaffoldResult.content_hash_stale``.

    Raises ``PackError`` for structural errors and ``OSError`` for
    filesystem errors during the atomic writes.
    """
    source = Path(source)
    if not scientific_name.strip():
        raise PackError("scientific_name must be a non-empty string")
    if not uses:
        raise PackError("uses must contain at least one value (row model requires >=1)")

    valid_archetypes = _vocab_keys("archetypes", "archetypes")
    if archetype not in valid_archetypes:
        raise PackError(
            f"archetype {archetype!r} not in vocabulary; expected one of {sorted(valid_archetypes)}"
        )
    organism_group = infer_organism_group(archetype)

    # Validate-first (raises PackError subclasses on broken packs).
    files = read_pack_bytes(source)
    validate_pack(files, allow_synthetic=True)
    manifest = parse_manifest_bytes(files["pack.toml"])

    taxa_path = source / "taxa.csv"
    existing_table = read_table(TABLES["taxa"], files["taxa.csv"], source_name="taxa.csv")
    existing_ids = frozenset(
        str(row["taxon_id"]) for row in existing_table.rows if row.get("taxon_id")
    )

    source_ids = _resolve_source_ids(srcs, files)

    taxon_id = _generate_taxon_id(existing_ids)
    new_row: dict[str, Any] = {
        "taxon_id": taxon_id,
        "rank": rank,
        "scientific_name": scientific_name,
        "accepted_name": None,
        "organism_group": organism_group,
        "archetype": archetype,
        "uses": list(uses),
        "traits": [],
        "parent_id": None,
        "external_ids": None,
        "src": list(source_ids),
        "dataset_id": None,
    }

    all_rows = [*list(existing_table.rows), new_row]
    new_taxa_bytes = write_table(TABLES["taxa"], all_rows)

    facts_dir = source / "facts"
    if facts_dir.exists() and not facts_dir.is_dir():
        raise PackError(f"{facts_dir} is not a directory")
    facts_target = facts_dir / f"{taxon_id}.csv"
    new_facts_bytes = write_table(TABLES["facts"], [])

    facts_dir.mkdir(exist_ok=True)
    facts_tmp = facts_dir / f"{taxon_id}.csv.tmp"
    taxa_tmp = source / "taxa.csv.tmp"
    try:
        facts_tmp.write_bytes(new_facts_bytes)
        taxa_tmp.write_bytes(new_taxa_bytes)
        os.replace(facts_tmp, facts_target)
        os.replace(taxa_tmp, taxa_path)
    except OSError:
        for t in (facts_tmp, taxa_tmp):
            with contextlib.suppress(OSError):
                t.unlink(missing_ok=True)
        raise

    return ScaffoldResult(
        source=source,
        taxon_id=taxon_id,
        facts_path=facts_target,
        content_hash_stale=manifest.content_hash is not None,
    )
