from __future__ import annotations

import logging
import re
from typing import Optional

import pycountry

from .country_continent_table import continent_for_iso_alpha2, load_iso_alpha2_to_continent
from .schemas import ParsedAffiliation

log = logging.getLogger(__name__)

_COUNTRY_ALIASES: dict[str, str] = {
    "USA": "United States",
    "U.S.A.": "United States",
    "U.S.A": "United States",
    "United States of America": "United States",
    "UK": "United Kingdom",
    "U.K.": "United Kingdom",
    "U.K": "United Kingdom",
    "Great Britain": "United Kingdom",
    "England": "United Kingdom",
    "Scotland": "United Kingdom",
    "Wales": "United Kingdom",
    "The Netherlands": "Netherlands",
    "Holland": "Netherlands",
    "Korea": "South Korea",
    "Republic of Korea": "South Korea",
    "Taiwan": "Taiwan, Province of China",
    "Peoples Republic of China": "China",
    "People's Republic of China": "China",
    "PRC": "China",
    "Czech Republic": "Czechia",
}

# Full ISO-2 → continent (UN-based CSV + small overrides). Public for diagnostics / tests.
COUNTRY_TO_CONTINENT: dict[str, str] = load_iso_alpha2_to_continent()

_USPS_STATE_TERRITORY_2: frozenset[str] = frozenset(
    {
        "AL",
        "AK",
        "AZ",
        "AR",
        "CA",
        "CO",
        "CT",
        "DE",
        "FL",
        "GA",
        "HI",
        "ID",
        "IL",
        "IN",
        "IA",
        "KS",
        "KY",
        "LA",
        "ME",
        "MD",
        "MA",
        "MI",
        "MN",
        "MS",
        "MO",
        "MT",
        "NE",
        "NV",
        "NH",
        "NJ",
        "NM",
        "NY",
        "NC",
        "ND",
        "OH",
        "OK",
        "OR",
        "PA",
        "RI",
        "SC",
        "SD",
        "TN",
        "TX",
        "UT",
        "VT",
        "VA",
        "WA",
        "WV",
        "WI",
        "WY",
        "DC",
        "AS",
        "GU",
        "MP",
        "PR",
        "VI",
    }
)

_POSTAL_LIKE = re.compile(r"^[\d\s\-]{5,}$")

# PubMed often appends ``. author@domain.tld`` to the affiliation line after the country.
_TRAILING_EMAIL_IN_AFFILIATION_TOKEN = re.compile(
    r"[\s.]+[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\s*\.?$",
    re.IGNORECASE,
)


def _clean_token_for_country_lookup(token: str) -> str:
    """Strip trailing email and punctuation so ``Italy.`` or ``USA. name@host`` resolve for pycountry."""
    t = (token or "").strip()
    if not t:
        return t
    t = _TRAILING_EMAIL_IN_AFFILIATION_TOKEN.sub("", t)
    return t.strip().rstrip(".,;:").strip()


def _looks_like_postal_token(token: str) -> bool:
    t = token.strip()
    return bool(t) and bool(_POSTAL_LIKE.fullmatch(t))


def _skip_token_for_country_scan(token: str, *, index_from_end: int) -> bool:
    """Avoid pycountry hits on ZIP lines; avoid US state abbreviations when not the last segment."""
    t = token.strip()
    if not t or len(t) == 1:
        return True
    if _looks_like_postal_token(t):
        return True
    if index_from_end > 1 and len(t) == 2 and t.isalpha() and t.upper() in _USPS_STATE_TERRITORY_2:
        return True
    return False


def _resolve_country_from_tail_tokens(tokens: list[str]) -> tuple[Optional[str], Optional[str]]:
    """Walk up to five comma segments from the end; return (alpha_2, official_name) or (None, None)."""
    max_scan = min(5, len(tokens))
    for i in range(1, max_scan + 1):
        raw_cand = tokens[-i]
        cleaned = _clean_token_for_country_lookup(raw_cand)
        if not cleaned or _skip_token_for_country_scan(cleaned, index_from_end=i):
            continue
        normalized = _COUNTRY_ALIASES.get(cleaned, cleaned)
        try:
            match = pycountry.countries.lookup(normalized)
            return match.alpha_2, match.name
        except LookupError:
            log.debug(
                "affiliation_parser: pycountry lookup failed for %r (segment %d from end)",
                normalized,
                i,
            )
    return None, None


def parse_affiliation(raw: str) -> ParsedAffiliation:
    """Parse a raw affiliation string into structured country/institution data."""
    stripped = (raw or "").strip()
    if not stripped:
        return ParsedAffiliation(raw="")

    tokens = [t.strip() for t in stripped.split(",") if t.strip()]
    if not tokens:
        return ParsedAffiliation(raw=stripped)

    institution: Optional[str] = tokens[0]
    city: Optional[str] = tokens[-2] if len(tokens) >= 3 else None

    country_code, country_name = _resolve_country_from_tail_tokens(tokens)
    continent = continent_for_iso_alpha2(country_code)

    return ParsedAffiliation(
        raw=stripped,
        institution=institution,
        city=city,
        country_name=country_name,
        country_code=country_code,
        continent=continent,
    )


def run(context: dict) -> dict:
    """Enrich articles[*].authors[*] with parsed_affiliation. Returns new context dict."""
    articles = context.get("articles", [])
    enriched_articles = []
    for article in articles:
        authors = article.get("authors", [])
        enriched_authors = []
        for author in authors:
            affiliations_raw: list[str] = author.get("affiliations_raw", [])
            parsed: Optional[ParsedAffiliation] = None
            for aff in affiliations_raw:
                candidate = parse_affiliation(aff)
                if candidate.country_code is not None:
                    parsed = candidate
                    break
            if parsed is None and affiliations_raw:
                parsed = parse_affiliation(affiliations_raw[0])
            new_author = {**author, "parsed_affiliation": parsed.model_dump() if parsed else None}
            enriched_authors.append(new_author)
        enriched_articles.append({**article, "authors": enriched_authors})
    return {**context, "articles": enriched_articles}
