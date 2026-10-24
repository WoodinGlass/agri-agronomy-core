"""Name and Taxon row model tests."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from agri_core.models.name import NameRow
from agri_core.models.taxon import TaxonRow

pytestmark = pytest.mark.unit


# --- NameRow ---


def _name(**kw):
    d = dict(
        taxon_id="T012345678",
        name="Solanum lycopersicum",
        language="la",
        script="Latn",
        kind="scientific",
        preferred=True,
        src=["S001"],
        dataset_id=None,
    )
    d.update(kw)
    return d


def test_name_minimal_valid() -> None:
    row = NameRow(**_name())
    assert row.kind == "scientific"
    assert row.preferred is True


@pytest.mark.parametrize("lang", ["en", "id", "und", "zh-Hans", "en-US", "zh-Hans-CN", "fil"])
def test_name_language_valid(lang: str) -> None:
    NameRow(**_name(language=lang))


@pytest.mark.parametrize("lang", ["EN", "en_US", "", "e", "-en", "en-"])
def test_name_language_invalid(lang: str) -> None:
    with pytest.raises(ValidationError):
        NameRow(**_name(language=lang))


@pytest.mark.parametrize("script", ["Latn", "Arab", "Zyyy", "Hani", "Cyrl"])
def test_name_script_valid(script: str) -> None:
    NameRow(**_name(script=script))


@pytest.mark.parametrize("script", ["latn", "LATIN", "Lat", "Latin1", ""])
def test_name_script_invalid(script: str) -> None:
    with pytest.raises(ValidationError):
        NameRow(**_name(script=script))


@pytest.mark.parametrize("kind", ["common", "scientific", "synonym", "trade"])
def test_name_kind_valid(kind: str) -> None:
    NameRow(**_name(kind=kind))


def test_name_kind_invalid() -> None:
    with pytest.raises(ValidationError):
        NameRow(**_name(kind="cultivar"))


def test_name_empty_string_rejected() -> None:
    with pytest.raises(ValidationError):
        NameRow(**_name(name=""))


def test_name_preferred_defaults_false() -> None:
    row = NameRow(**_name(preferred=False))
    assert row.preferred is False


def test_name_requires_src_or_dataset() -> None:
    with pytest.raises(ValidationError, match="at least one of src or dataset_id"):
        NameRow(**_name(src=None, dataset_id=None))


def test_name_dataset_only() -> None:
    row = NameRow(**_name(src=None, dataset_id="D012345678"))
    assert row.dataset_id == "D012345678"


def test_name_frozen() -> None:
    row = NameRow(**_name())
    with pytest.raises((ValidationError, TypeError)):
        row.name = "other"  # type: ignore[misc]


def test_name_extra_forbidden() -> None:
    with pytest.raises(ValidationError):
        NameRow(**_name(extra="boom"))


# --- TaxonRow ---


def _taxon(**kw):
    d = dict(
        taxon_id="T012345678",
        rank="species",
        scientific_name="Solanum lycopersicum",
        accepted_name=None,
        organism_group="vascular_plant",
        archetype="annual",
        uses=["vegetable"],
        traits=[],
        parent_id=None,
        external_ids=None,
        src=["S001"],
        dataset_id=None,
    )
    d.update(kw)
    return d


def test_taxon_minimal_valid() -> None:
    row = TaxonRow(**_taxon())
    assert row.rank == "species"
    assert row.uses == ["vegetable"]
    assert row.traits == []


@pytest.mark.parametrize("rank", ["species", "hybrid", "cultivar_group", "genus"])
def test_taxon_rank_valid(rank: str) -> None:
    TaxonRow(**_taxon(rank=rank))


def test_taxon_rank_invalid() -> None:
    with pytest.raises(ValidationError):
        TaxonRow(**_taxon(rank="subspecies"))


def test_taxon_empty_scientific_name_rejected() -> None:
    with pytest.raises(ValidationError):
        TaxonRow(**_taxon(scientific_name=""))


def test_taxon_accepted_name_none_ok() -> None:
    row = TaxonRow(**_taxon(accepted_name=None))
    assert row.accepted_name is None


def test_taxon_accepted_name_non_empty_ok() -> None:
    row = TaxonRow(**_taxon(accepted_name="Lycopersicon esculentum"))
    assert row.accepted_name == "Lycopersicon esculentum"


def test_taxon_accepted_name_empty_rejected() -> None:
    with pytest.raises(ValidationError, match="accepted_name must be non-empty"):
        TaxonRow(**_taxon(accepted_name=""))


def test_taxon_uses_requires_at_least_one() -> None:
    with pytest.raises(ValidationError):
        TaxonRow(**_taxon(uses=[]))


def test_taxon_uses_rejects_empty_string() -> None:
    with pytest.raises(ValidationError):
        TaxonRow(**_taxon(uses=[""]))


def test_taxon_traits_default_empty() -> None:
    row = TaxonRow(**_taxon())
    assert row.traits == []


def test_taxon_traits_accepts_list() -> None:
    row = TaxonRow(**_taxon(traits=["chill_requirement", "support_required"]))
    assert len(row.traits) == 2


def test_taxon_traits_rejects_duplicates() -> None:
    with pytest.raises(ValidationError, match="duplicates"):
        TaxonRow(**_taxon(traits=["chill_requirement", "chill_requirement"]))


def test_taxon_parent_id_none_ok() -> None:
    TaxonRow(**_taxon(parent_id=None))


def test_taxon_parent_id_different_ok() -> None:
    row = TaxonRow(**_taxon(parent_id="T000000001"))
    assert row.parent_id == "T000000001"


def test_taxon_parent_id_self_rejected() -> None:
    with pytest.raises(ValidationError, match="parent_id must not equal taxon_id"):
        TaxonRow(**_taxon(parent_id="T012345678"))


def test_taxon_external_ids_dict() -> None:
    row = TaxonRow(**_taxon(external_ids={"gbif": "12345", "powo": "67890"}))
    assert row.external_ids == {"gbif": "12345", "powo": "67890"}


def test_taxon_external_ids_none_ok() -> None:
    TaxonRow(**_taxon(external_ids=None))


def test_taxon_requires_src_or_dataset() -> None:
    with pytest.raises(ValidationError, match="at least one of src or dataset_id"):
        TaxonRow(**_taxon(src=None, dataset_id=None))


def test_taxon_dataset_only() -> None:
    row = TaxonRow(**_taxon(src=None, dataset_id="D012345678"))
    assert row.dataset_id == "D012345678"


def test_taxon_frozen() -> None:
    row = TaxonRow(**_taxon())
    with pytest.raises((ValidationError, TypeError)):
        row.rank = "genus"  # type: ignore[misc]


def test_taxon_extra_forbidden() -> None:
    with pytest.raises(ValidationError):
        TaxonRow(**_taxon(extra="boom"))


def test_taxon_empty_organism_group_rejected() -> None:
    with pytest.raises(ValidationError):
        TaxonRow(**_taxon(organism_group=""))


def test_taxon_empty_archetype_rejected() -> None:
    with pytest.raises(ValidationError):
        TaxonRow(**_taxon(archetype=""))
