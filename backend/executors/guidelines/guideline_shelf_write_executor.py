"""Executor for the ``guideline_shelf_write`` node — the shelf-builder's tail.

Maps the classified shelf documents (``GuidelineShelfOutput`` from the classify
node) onto the GL-4 ``guideline_source_documents`` shape and replaces the disease's
shelf via ``repo.replace_source_documents``. Terminal, idempotent.

The synthesis engine reads this shelf, so the ``docId`` set written here is the
authoritative provenance vocabulary the synthesis cites against. docId = PMID when
present, else the Bookshelf id.
"""
from __future__ import annotations

import asyncio
import logging
import re

from ..base import NodeExecutor, NodeInput, NodeOutput

log = logging.getLogger(__name__)

# kind → default display role when the model didn't supply one.
_ROLE_BY_KIND = {
    "base_consensus": "Base consensus",
    "update": "Update",
    "subtopic": "Subtopic",
    "reference_compendium": "Reference compendium",
    "other": "Reference",
}

# A 4-digit year, optionally with a trailing range/suffix the FE can render.
_YEAR_RE = re.compile(r"^(19|20)\d{2}([-–/]\d{2,4})?$")
# Curated non-year labels the FE renders verbatim (GeneReviews etc.).
_YEAR_LABELS = {"continuously updated", "n/a"}


def _clean_year(raw: str) -> str:
    """Keep a 4-digit year or a known label; blank junk like ``2015/02/26 00:00``.

    PubMed/Bookshelf metadata occasionally arrives as a full timestamp. The FE
    expects either a plain year or a short label, so drop anything else rather
    than persisting a timestamp that renders as noise.
    """
    raw = (raw or "").strip()
    if not raw:
        return ""
    if raw.lower() in _YEAR_LABELS:
        return raw
    if _YEAR_RE.match(raw):
        return raw
    # Salvage a leading 4-digit year out of a longer string (e.g. a timestamp).
    m = re.match(r"^(19|20)\d{2}", raw)
    return m.group(0) if m else ""


def _clean_journal(raw: str) -> str:
    """Drop an obviously-junk one-word journal token (e.g. ``gene``).

    A single short lowercase token is almost always a truncated/garbled source
    label, not a real journal name; blank it rather than persisting junk.
    """
    raw = (raw or "").strip()
    if not raw:
        return ""
    if " " not in raw and raw.islower() and len(raw) <= 6:
        return ""
    return raw


class GuidelineShelfWriteExecutor(NodeExecutor):
    """Persist the classified shelf into guideline_source_documents."""

    def __init__(self, repo=None) -> None:
        self._repo = repo  # injectable for tests

    @classmethod
    def node_type(cls) -> str:
        return "guideline_shelf_write"

    def _get_repo(self):
        if self._repo is not None:
            return self._repo
        from ...guidelines.repository import SqlaGuidelinesRepo

        return SqlaGuidelinesRepo()

    async def execute(self, input: NodeInput) -> NodeOutput:
        initial = input.initial_data or input.context.get("initial") or {}
        context = input.context or {}
        slug = str(initial.get("disease_slug") or "").strip().lower()
        if not slug:
            return NodeOutput(data={"ok": False, "error": "disease_slug missing in flow context."})

        classified = _find_classified_docs(context)
        considered = _find_considered(context)
        if not classified:
            return NodeOutput(data={"ok": False, "error": "no classified shelf docs in context."})

        docs: list[dict] = []
        seen_ids: set[str] = set()
        kinds: dict[str, int] = {}
        for d in classified:
            if not isinstance(d, dict):
                continue
            pmid = str(d.get("pmid") or "").strip()
            bookshelf = str(d.get("bookshelf") or "").strip()
            doc_id = pmid or bookshelf
            if not doc_id or doc_id in seen_ids:
                continue
            seen_ids.add(doc_id)
            kind = str(d.get("kind") or "other").strip().lower()
            kinds[kind] = kinds.get(kind, 0) + 1
            docs.append(
                {
                    "id": doc_id,
                    "role": str(d.get("role") or "").strip() or _ROLE_BY_KIND.get(kind, "Reference"),
                    "title": str(d.get("title") or "").strip(),
                    "authors": str(d.get("authors") or "").strip(),
                    "journal": _clean_journal(str(d.get("journal") or "")),
                    # Bookshelf entries (GeneReviews / StatPearls) are living
                    # references with no fixed year — label them accordingly
                    # rather than "n/a". PMID entries fall back to "n/a" and get
                    # a real year backfilled from PubMed esummary below.
                    "year": _clean_year(str(d.get("year") or ""))
                    or ("continuously updated" if bookshelf else "n/a"),
                    "scope": str(d.get("scope") or "").strip(),
                    "covers": list(d.get("covers") or []),
                    "pmid": pmid or None,
                    "bookshelf": bookshelf or None,
                    "freeFullText": False,
                    "isNew": kind == "update",
                    "updatesNote": str(d.get("updates_note") or "").strip() or None,
                }
            )

        if not docs:
            return NodeOutput(data={"ok": False, "error": "no shelf docs had a usable identifier."})

        # Backfill authors/year/journal from PubMed by PMID. The classify node
        # returns role/title/pmid but drops bibliographic metadata, so tiles
        # rendered "· n/a" with no author even though the same PMIDs carry full
        # metadata in the bibliography. Best-effort, off the event loop.
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, _enrich_docs_from_pubmed, docs)

        # A rebuild must not silently lose a document. See _merge_with_existing.
        try:
            repo = self._get_repo()
            docs, kept_ids = _merge_with_existing(repo, slug, docs, considered)
            repo.replace_source_documents(slug, docs)
            # Store why each rejected candidate was rejected. Best-effort: the audit
            # snapshot is valuable, but never worth failing a shelf write over.
            try:
                repo.replace_considered(slug, [c for c in considered if isinstance(c, dict)])
            except Exception as exc:  # noqa: BLE001
                log.warning("guideline_shelf_write: considered snapshot failed: %s", exc)
        except Exception as exc:  # noqa: BLE001 — a write failure must fail the node
            log.warning("guideline_shelf_write: replace failed for %s: %s", slug, exc)
            return NodeOutput(data={"ok": False, "error": f"shelf write failed: {exc}"})

        return NodeOutput(
            data={
                "ok": True,
                "slug": slug,
                "docCount": len(docs),
                "kinds": kinds,
                "keptFromPreviousShelf": sorted(kept_ids),
            }
        )


# Reasons that justify dropping a document that a previous run (or a human) had
# already put on the shelf. Anything else — "narrow", "other", or no reason at all —
# is not enough, and the document stays.
_JUSTIFIED_REMOVAL = {"superseded", "duplicate", "off-topic"}


def _merge_with_existing(
    repo, slug: str, docs: list[dict], considered: object
) -> tuple[list[dict], set[str]]:
    """Carry forward shelf documents this run did not re-select without a reason.

    The rebuild is a full replace driven by one stochastic classification, and it
    has silently dropped good documents twice: once the paediatric review and the
    2012 craniofacial guidelines, once the 2023 NIH craniofacial review. Nobody
    noticed until a human read the resulting synthesis.

    So removal now needs a stated, specific reason. A document already on the shelf
    is carried forward unless this run's ``considered`` list names it with a
    category in :data:`_JUSTIFIED_REMOVAL`. The classifier keeps full authority to
    supersede and de-duplicate; it just cannot drop something by forgetting it.

    Best-effort: if the previous shelf cannot be read, the run proceeds as a plain
    replace rather than failing.
    """
    try:
        existing = repo.list_source_documents(slug)
    except Exception as exc:  # noqa: BLE001 — never block a rebuild on this
        log.warning("guideline_shelf_write: could not read the existing shelf: %s", exc)
        return docs, set()

    new_ids = {str(d.get("id")) for d in docs}
    dropped_reason: dict[str, str] = {}
    for item in considered or []:
        if not isinstance(item, dict):
            continue
        ident = str(item.get("pmid") or item.get("bookshelf") or "").strip()
        if ident:
            dropped_reason[ident] = str(item.get("category") or "").strip().lower()

    kept: set[str] = set()
    for d in existing:
        doc_id = str(d.doc_id)
        if doc_id in new_ids:
            continue
        if dropped_reason.get(doc_id) in _JUSTIFIED_REMOVAL:
            log.info(
                "guideline_shelf_write: %s dropped from %s shelf (%s)",
                doc_id,
                slug,
                dropped_reason[doc_id],
            )
            continue
        kept.add(doc_id)
        docs.append(
            {
                "id": doc_id,
                "role": d.role,
                "title": d.title,
                "authors": d.authors,
                "journal": d.journal,
                "year": d.year,
                "scope": d.scope,
                "covers": list(d.covers or []),
                "pmid": d.pmid,
                "bookshelf": d.bookshelf,
                "freeFullText": d.free_full_text,
                "isNew": False,
                "updatesNote": d.updates_note,
            }
        )
    if kept:
        log.info(
            "guideline_shelf_write: carried %d document(s) forward on the %s shelf: %s",
            len(kept),
            slug,
            ", ".join(sorted(kept)),
        )
    return docs, kept


def _enrich_docs_from_pubmed(docs: list[dict]) -> None:
    """Fill blank authors/year/journal from PubMed esummary, keyed by PMID.

    The classify node preserves only role/title/pmid, so shelf tiles rendered
    "· n/a" with no author. We already hold the PMIDs, so fetch the same
    esummary the bibliography uses and backfill in place. Soft-fails: on any
    error (or missing record) each doc keeps its existing value. Mutates ``docs``.
    """
    pmids = [str(d.get("pmid")) for d in docs if d.get("pmid")]
    if not pmids:
        return
    try:
        from ...services.official_guidelines_finder import _pubmed_metadata

        meta = {str(m.get("pmid")): m for m in _pubmed_metadata(pmids)}
    except Exception as exc:  # noqa: BLE001 — enrichment is best-effort
        log.warning("guideline_shelf_write: PubMed enrichment skipped: %s", exc)
        return
    for d in docs:
        m = meta.get(str(d.get("pmid") or ""))
        if not m:
            continue
        if not d.get("authors"):
            d["authors"] = str(m.get("authors") or "").strip()
        year = m.get("year")
        if (not d.get("year") or d.get("year") == "n/a") and isinstance(year, int) and year > 0:
            d["year"] = str(year)
        if not d.get("journal"):
            d["journal"] = _clean_journal(str(m.get("journal") or ""))


def _find_considered(context: dict) -> list:
    """The classify node's rejected candidates, with the reason each was left off."""
    primary = context.get("gsb-classify")
    if isinstance(primary, dict) and isinstance(primary.get("considered"), list):
        return primary["considered"]
    for out in context.values():
        if isinstance(out, dict) and isinstance(out.get("considered"), list):
            return out["considered"]
    return []


def _find_classified_docs(context: dict) -> list:
    """Locate the classify node output (``{docs: [...]}``) in the flow context."""
    primary = context.get("gsb-classify")
    if isinstance(primary, dict) and isinstance(primary.get("docs"), list):
        return primary["docs"]
    # Fallback: any node output carrying a docs list.
    for out in context.values():
        if isinstance(out, dict) and isinstance(out.get("docs"), list):
            return out["docs"]
    return []
