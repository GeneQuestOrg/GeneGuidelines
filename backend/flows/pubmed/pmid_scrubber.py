"""
Deterministic post-processor: removes hallucinated PMIDs from pm-5 output text.
Uses the retrieved PMID set from pm-1 as the allowlist.
"""
import re

from backend.flows.pubmed.pmid_verifier import PMID_SUSPICIOUS_THRESHOLD, extract_pmids_from_text

PMID_EXPLICIT_PATTERN = re.compile(r"\bPMID[:\s]+(\d{7,9})\b", re.IGNORECASE)
PMID_BARE_PATTERN = re.compile(r"\b(\d{7,9})\b")
MIN_VALID_PMID = 1_000_000  # real PMIDs are 7-9 digits, min ~1M range


def scrub_pmids(text: str, valid_pmids: set[str]) -> tuple[str, list[str]]:
    """
    Replace PMIDs not in valid_pmids (or clearly invalid) with [PMID UNVERIFIED].
    Returns (cleaned_text, list_of_removed_pmids).
    """
    removed: list[str] = []
    removed_seen: set[str] = set()

    invalid_pmids: set[str] = set()
    for pid in extract_pmids_from_text(text):
        pid_int = int(pid)
        if pid in valid_pmids and MIN_VALID_PMID <= pid_int <= PMID_SUSPICIOUS_THRESHOLD:
            continue
        invalid_pmids.add(pid)

    if not invalid_pmids:
        return text, removed

    def _mark_removed(pid: str) -> None:
        if pid not in removed_seen:
            removed_seen.add(pid)
            removed.append(pid)

    def _replace_explicit(match: re.Match[str]) -> str:
        pid = match.group(1)
        if pid not in invalid_pmids:
            return match.group(0)
        _mark_removed(pid)
        return "[PMID UNVERIFIED]"

    def _replace_bare(match: re.Match[str]) -> str:
        pid = match.group(1)
        if pid not in invalid_pmids:
            return match.group(0)
        _mark_removed(pid)
        return "[PMID UNVERIFIED]"

    cleaned = PMID_EXPLICIT_PATTERN.sub(_replace_explicit, text)
    cleaned = PMID_BARE_PATTERN.sub(_replace_bare, cleaned)
    return cleaned, removed
