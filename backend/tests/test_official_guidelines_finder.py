"""Official-guidelines finder: gene-aware PubMed search + graceful gene resolution.

Ultra-rare diseases find ~0 consensus papers by NAME, so the causative gene is OR'd into
the esearch query (mirrors the doctor-finder gene work). No network / DB: urlopen and the
row resolver are monkeypatched.
"""
from __future__ import annotations

import asyncio
import unittest
from unittest.mock import patch
from urllib.parse import unquote_plus

from backend.services import official_guidelines_finder as og


class _FakeResp:
    def __init__(self, payload: bytes) -> None:
        self._payload = payload

    def __enter__(self) -> _FakeResp:
        return self

    def __exit__(self, *_a: object) -> bool:
        return False

    def read(self) -> bytes:
        return self._payload


def _capturing_urlopen(captured: list[str], payload: bytes = b'{"esearchresult":{"idlist":[]}}'):
    def _fake(req, timeout=None):  # noqa: ANN001
        captured.append(getattr(req, "full_url", str(req)))
        return _FakeResp(payload)

    return _fake


# ── esearch query construction ──────────────────────────────────────────────


def test_pubmed_query_ors_gene(monkeypatch) -> None:
    captured: list[str] = []
    monkeypatch.setattr(og.urllib.request, "urlopen", _capturing_urlopen(captured))
    og._pubmed_search("Ultra Rare Disease", "GNAS")
    q = unquote_plus(captured[0])
    assert '"GNAS"[Title/Abstract]' in q  # gene OR'd in (Title/Abstract scoped)
    assert '"Ultra Rare Disease"[Title/Abstract]' in q  # disease name kept
    assert " OR " in q  # OR (broaden), not AND (narrow)
    assert "Review[ptyp]" in q  # existing consensus/review filter preserved
    assert "[Gene]" not in q  # no invalid PubMed field


def test_pubmed_query_omits_gene_when_absent_or_short(monkeypatch) -> None:
    captured: list[str] = []
    monkeypatch.setattr(og.urllib.request, "urlopen", _capturing_urlopen(captured))
    og._pubmed_search("Fibrous Dysplasia")  # no gene
    og._pubmed_search("Fibrous Dysplasia", "X")  # too short (<3 chars)
    q0, q1 = unquote_plus(captured[0]), unquote_plus(captured[1])
    # Disease block is the bare name phrase — no gene OR'd between two Title/Abstract phrases.
    assert "GNAS" not in q0 and '[Title/Abstract] OR "' not in q0
    assert '"X"[Title/Abstract]' not in q1


# ── ranking prompt names the gene so gene-titled guidelines aren't dismissed ──


def test_rank_prompt_names_gene(monkeypatch) -> None:
    seen: dict = {}

    async def _fake_run(*, system_prompt, user_prompt, result_type, primary_spec, max_tokens):  # noqa: ANN001
        seen["user_prompt"] = user_prompt
        return (
            result_type(best_pmid="1", title="t", authors="a", year=2020, journal="J", confidence=0.9),
            "spec",
        )

    monkeypatch.setattr(og, "_resolve_gemma_model_spec", lambda: "spec")
    monkeypatch.setattr(
        "backend.services._model_resolver.run_structured_with_ollama_fallback", _fake_run
    )
    candidates = [{"pmid": "1", "title": "t", "authors": "a", "journal": "J", "year": 2020}]
    asyncio.run(og._rank_with_gemma("Ultra Rare Disease", candidates, "GNAS"))
    assert "(causative gene: GNAS)" in seen["user_prompt"]


# ── gene resolution + graceful threading ──────────────────────────────────────


class OfficialGuidelineGeneResolutionTests(unittest.IsolatedAsyncioTestCase):
    async def test_threads_resolved_gene_into_search(self) -> None:
        seen: dict = {}
        with patch.object(og, "SqlaDiseaseRepo") as repo_cls:
            repo_cls.return_value.get.return_value = object()  # disease row exists
            with patch.object(og, "_resolve_gene_for_slug", return_value="GNAS"):
                with patch.object(
                    og,
                    "_pubmed_search",
                    side_effect=lambda name, gene=None: seen.update(gene=gene) or [],
                ):
                    with patch.object(og, "_log_run"):
                        result = await og.find_official_guideline_for_disease("some-slug", "Some Disease")
        self.assertEqual(seen["gene"], "GNAS")
        self.assertIsNone(result)  # no PMIDs → None (graceful)


# ── shared resolver: content_db.get_disease_gene ─────────────────────────────


def test_get_disease_gene_reads_row_and_degrades_gracefully(monkeypatch) -> None:
    from backend import content_db

    monkeypatch.setattr(content_db, "get_disease_by_slug", lambda slug, **k: {"gene": "GNAS"})
    assert content_db.get_disease_gene("fibrous-dysplasia") == "GNAS"

    assert content_db.get_disease_gene("") == ""  # empty slug → "" (no lookup)

    monkeypatch.setattr(content_db, "get_disease_by_slug", lambda slug, **k: None)
    assert content_db.get_disease_gene("unknown") == ""  # no row → ""

    monkeypatch.setattr(content_db, "get_disease_by_slug", lambda slug, **k: {"gene": ""})
    assert content_db.get_disease_gene("no-gene") == ""  # row without gene → ""

    def _boom(slug, **k):
        raise RuntimeError("db down")

    monkeypatch.setattr(content_db, "get_disease_by_slug", _boom)
    assert content_db.get_disease_gene("x") == ""  # lookup error swallowed → ""


if __name__ == "__main__":
    unittest.main()
