"""NCBI's own index of GeneReviews chapters: accession, title, genes and OMIM numbers.

NCBI publishes it as three small tab- or pipe-separated files under https://ftp.ncbi.nlm.nih.gov/pub/GeneReviews/ (about 0.5 MB together, refreshed with the book). They answer two questions the Bookshelf search cannot:

- **Which disease a chapter is about.** A Bookshelf search hit is often a section record ("Clinical Characteristics") of a chapter that only mentions the searched gene in a differential-diagnosis table. That is how the shelf of the ultra-rare PUS3 syndrome came to hold the GeneReviews chapters on Schinzel-Giedion syndrome (SETBP1) and Lenz-Majewski dysplasia (PTDSS1). The genes and OMIM numbers here settle it.
- **Whether an NBK accession is a GeneReviews chapter at all**, and its real title.

Read over HTTPS from the FTP host, which serves files to automated clients (the Bookshelf web pages do not; see ``bookshelf_fulltext``). Cached in the process for a day; a failed fetch returns an empty index, so callers fall back to weaker evidence rather than fail.
"""

from __future__ import annotations

import logging
import threading
import time
import urllib.request
from dataclasses import dataclass

log = logging.getLogger(__name__)

BASE_URL = "https://ftp.ncbi.nlm.nih.gov/pub/GeneReviews/"
TITLES_FILE = "GRtitle_shortname_NBKid.txt"
GENES_FILE = "GRshortname_NBKid_genesymbol_dzname.txt"
OMIM_FILE = "NBKid_shortname_OMIM.txt"
_USER_AGENT = "GeneQuestFoundation/1.0 (https://genequest.org)"
_TTL_SEC = 24 * 3600
_lock = threading.Lock()
_cache: dict[str, object] = {"at": 0.0, "index": {}}


@dataclass(frozen=True)
class GeneReviewsChapter:
    accession: str
    shortname: str
    title: str
    pmid: str
    genes: tuple[str, ...] = ()
    omim: tuple[str, ...] = ()


def parse_index(titles: str, genes: str, omim: str) -> dict[str, GeneReviewsChapter]:
    """accession → chapter, from the three NCBI files' text."""
    base: dict[str, dict] = {}
    for line in titles.splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) < 3 or not parts[2].startswith("NBK"):
            continue
        base[parts[2]] = {"shortname": parts[0], "title": parts[1], "pmid": parts[3].strip() if len(parts) > 3 else "", "genes": set(), "omim": set()}
    for line in genes.splitlines():
        parts = line.split("|")
        if len(parts) >= 3 and parts[1] in base and parts[2].strip() and parts[2].strip().upper() != "NOT APPLICABLE":
            base[parts[1]]["genes"].add(parts[2].strip().upper())
    for line in omim.splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) >= 3 and parts[0] in base and parts[2].strip().isdigit():
            base[parts[0]]["omim"].add(parts[2].strip())
    return {
        acc: GeneReviewsChapter(accession=acc, shortname=v["shortname"], title=v["title"], pmid=v["pmid"], genes=tuple(sorted(v["genes"])), omim=tuple(sorted(v["omim"])))
        for acc, v in base.items()
    }


def _get(name: str, timeout: float) -> str:
    request = urllib.request.Request(BASE_URL + name, headers={"User-Agent": _USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read().decode("utf-8", "replace")


def load_index(timeout: float = 30.0, *, force: bool = False) -> dict[str, GeneReviewsChapter]:
    """The GeneReviews index, cached for a day. Empty when NCBI cannot be reached."""
    with _lock:
        if not force and _cache["index"] and time.monotonic() - float(_cache["at"]) < _TTL_SEC:
            return dict(_cache["index"])  # type: ignore[arg-type]
    try:
        index = parse_index(_get(TITLES_FILE, timeout), _get(GENES_FILE, timeout), _get(OMIM_FILE, timeout))
    except Exception as exc:  # noqa: BLE001 - an index we cannot read means weaker evidence, never a failed run
        log.warning("genereviews_index: could not load the NCBI GeneReviews index: %s", exc)
        return {}
    with _lock:
        _cache["index"], _cache["at"] = index, time.monotonic()
    return dict(index)
