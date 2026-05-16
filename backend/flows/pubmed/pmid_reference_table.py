"""
Builds a compact PMID reference table for injection into pm-4-* section prompts.
Format: one line per article — PMID | Author Year | Journal | Title (truncated)
"""
from __future__ import annotations

MAX_TITLE_CHARS = 80
MAX_TABLE_ENTRIES = 200


def _first_author_surname(authors_raw) -> str:
    if isinstance(authors_raw, list):
        raw = str(authors_raw[0]) if authors_raw else "Unknown"
    else:
        raw = str(authors_raw)
    clean = raw.strip()
    if not clean:
        return "Unknown"
    # Handle "LastName, FirstName" and "LastName FirstInitial"
    if "," in clean:
        return clean.split(",", 1)[0].strip() or "Unknown"
    return clean.split()[0]


def build_reference_table(articles: list[dict]) -> str:
    """
    Build a plain-text reference table from a list of article dicts.
    Returns a formatted string ready to inject into a prompt.
    """
    lines: list[str] = []
    seen: set[str] = set()

    for art in articles:  # iterate all, dedup by PMID
        pmid = str(art.get("pmid") or art.get("PMID") or art.get("id") or "").strip()
        if not pmid or pmid in seen:
            continue
        seen.add(pmid)

        title_raw = str(art.get("title") or art.get("Title") or "").strip()
        title = title_raw[:MAX_TITLE_CHARS] + ("…" if len(title_raw) > MAX_TITLE_CHARS else "")

        first_author = _first_author_surname(art.get("authors") or art.get("Authors") or [])

        year_raw = art.get("year") or art.get("pub_date") or art.get("PubDate") or ""
        year = str(year_raw)[:4] if year_raw else "????"

        journal_raw = str(art.get("journal") or art.get("Journal") or art.get("source") or "").strip()
        journal = journal_raw[:30] + ("…" if len(journal_raw) > 30 else "")

        lines.append(f"{pmid} | {first_author} {year} | {journal} | {title}")
        if len(lines) >= MAX_TABLE_ENTRIES:
            break

    if not lines:
        return "(no verified PMIDs available)"

    header = (
        f"VERIFIED PMIDs FOR CITATION ({len(lines)} articles):\n"
        "Format: PMID | Author Year | Journal | Title\n"
        + "-" * 60 + "\n"
    )
    return header + "\n".join(lines)
