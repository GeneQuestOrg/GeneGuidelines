"""disease_index local_slug linking — the fix for on-demand-researched diseases
showing "research" (hasLocalRecord=false) in the autocomplete even though they
already have a catalog page. `finalize_bootstrapped_disease` calls
`link_local_slug` to point the Orphanet-sourced index row at the new catalog
slug, matching by exact canonical name OR OMIM.
"""

from __future__ import annotations

import unittest

from backend.disease_index.models import DiseaseAlias, DiseaseIndexEntry
from backend.disease_index.repository import (
    InMemoryDiseaseIndexRepo,
    normalize_term,
)


def _entry(primary_id, name, *, omim=(), local_slug=None):
    norm = normalize_term(name)
    return DiseaseIndexEntry(
        primary_id=primary_id,
        source="orphanet",
        canonical_name=name,
        canonical_name_norm=norm,
        category="genetic",
        is_in_scope=True,
        inheritance=None,
        summary="",
        omim_codes=tuple(omim),
        gene_symbols=(),
        aliases=(DiseaseAlias(alias=name, alias_norm=norm, kind="canonical"),),
        local_slug=local_slug,
    )


class LinkLocalSlugTests(unittest.TestCase):
    def test_links_by_exact_canonical_name(self) -> None:
        repo = InMemoryDiseaseIndexRepo([_entry("ORPHA:1", "Fibrous Dysplasia")])
        n = repo.link_local_slug(local_slug="fd", canonical_name="Fibrous Dysplasia")
        self.assertEqual(n, 1)
        self.assertEqual(repo.get_by_primary_id("ORPHA:1").local_slug, "fd")

    def test_links_by_omim_when_name_differs(self) -> None:
        repo = InMemoryDiseaseIndexRepo([_entry("ORPHA:2", "Full canonical name", omim=("617051",))])
        n = repo.link_local_slug(
            local_slug="pus3-disease", omim="617051", canonical_name="a slightly different name"
        )
        self.assertEqual(n, 1)
        self.assertEqual(repo.get_by_primary_id("ORPHA:2").local_slug, "pus3-disease")

    def test_omim_token_is_quote_anchored(self) -> None:
        # "6170" must not match an entry whose only OMIM is "617051".
        repo = InMemoryDiseaseIndexRepo([_entry("ORPHA:3", "X", omim=("617051",))])
        self.assertEqual(repo.link_local_slug(local_slug="s", omim="6170"), 0)

    def test_does_not_clobber_existing_link(self) -> None:
        repo = InMemoryDiseaseIndexRepo(
            [_entry("ORPHA:4", "Marfan syndrome", omim=("154700",), local_slug="marfan-syndrome")]
        )
        n = repo.link_local_slug(local_slug="hijack", canonical_name="Marfan syndrome")
        self.assertEqual(n, 0)
        self.assertEqual(repo.get_by_primary_id("ORPHA:4").local_slug, "marfan-syndrome")

    def test_no_match_returns_zero(self) -> None:
        repo = InMemoryDiseaseIndexRepo([_entry("ORPHA:5", "Something else")])
        self.assertEqual(
            repo.link_local_slug(local_slug="s", omim="000000", canonical_name="Unrelated disease"),
            0,
        )

    def test_empty_criteria_is_a_noop(self) -> None:
        repo = InMemoryDiseaseIndexRepo([_entry("ORPHA:6", "Anything")])
        self.assertEqual(repo.link_local_slug(local_slug="s"), 0)


if __name__ == "__main__":
    unittest.main()
