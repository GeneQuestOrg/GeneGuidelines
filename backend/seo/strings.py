"""Labels for server-rendered pages, read from the bundle the frontend build writes.

The source of truth is the locale catalogues in frontend-public/src/locales; `frontend-public/prerender/ssr-strings.mjs` copies the labels this module needs into `dist/_ssr-strings.json`, which ships to /app/static with the rest of the bundle. A missing or unreadable file is not an outage: every key has an English fallback below, and a locale missing a key falls back to English for that key only.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

STRINGS_FILE = "_ssr-strings.json"

# English fallbacks, used only when the bundle file is missing or lacks a key.
FALLBACK_EN: dict[str, str] = {
    "siteTitle": "GeneGuidelines — Living guidelines for rare genetic diseases",
    "siteDescription": "Living guidelines, specialists, and clinical trials for rare genetic diseases.",
    "titleSuffix": " · GeneGuidelines",
    "linkGuidelines": "What the guidelines say",
    "linkDiseases": "All diseases",
    "linkAllDoctors": "Doctor directory",
    "linkAbout": "Why we built this",
    "footerDesc": "Living guidelines for rare genetic diseases — an AI-drafted, source-cited summary of official guidelines and the literature, refreshed on demand. Not an official guideline; clinicians can rate and flag it.",
    "notListed": "Not yet in the public catalog — pending curation.",
    "factGene": "Gene",
    "factOmim": "OMIM",
    "factInheritance": "Inheritance",
    "factPrevalence": "Prevalence",
    "diseasesTitle": "Diseases",
    "guidelinesTitle": "{{disease}} — what the guidelines say",
    "versionNoGuideline": "no agreed guideline · level (c)",
    "noGuidelineTitle": "We don't have a guideline for this disease yet.",
    "noGuidelineBody": "There is no agreed clinical guideline for {{disease}}, and the literature we could gather is not enough to build anything honest from. We would rather tell you that plainly than show you generalities.",
    "sectionNoSourceNote": "No document on this disease's source shelf addresses this section. We would rather say so than fill the space with text drawn from elsewhere in the guideline.",
    "clinicalSummaryHeading": "Clinical summary, written for the doctor",
    "clinicalSummaryNote": "This text describes management in the language of clinicians and names medicines and procedures. It is not advice for you and not a plan for your child. It is here so that your doctor can read it and go to the sources.",
    "shelfTitle": "What this summary is based on",
    "basedOn": "Based on:",
    "pmidLabel": "PMID {{pmid}}",
    "doctorsTitle": "Find a specialist",
    "doctorsLead": "Factual signals, not our opinion.",
    "doctorsProvenance": "Profiles are built from public sources (PubMed, clinic websites) and family reports.",
    "doctorDiseases": "Diseases",
    "trialsTitle": "Clinical trials",
    "trialsLead": "Trials we have catalogued for these conditions, with their recruitment status and sites.",
    "trialsProvenance": "Trial records are catalogued from ClinicalTrials.gov and may lag the registry.",
    "trialsRegistryLink": "Open on ClinicalTrials.gov →",
    "trialsStatus": "Status",
    "trialsPhase": "Phase",
    "diseasesDescription": "Rare genetic diseases in the GeneGuidelines catalogue, each with a source-cited summary of the official guidelines and literature, doctors with documented experience and clinical trials.",
    "hubDescription": "{{disease}}: a source-cited summary of the official guidelines and literature, doctors with documented experience, clinical trials and foundations — gathered by the GeneQuest Foundation.",
    "guidelinesDescription": "What the guidelines and the literature say about {{disease}}, summarised by AI with a link to every source. Not an official guideline; nobody formally signs it off.",
    "doctorsForTitle": "Doctors for {{disease}}",
    "doctorsDescription": "Doctors with documented experience in {{disease}}, built from public sources (PubMed, clinic websites) and family reports.",
    "directoryDescription": "A directory of doctors with documented experience in rare genetic diseases, built from public sources (PubMed, clinic websites) and family reports.",
    "doctorsByDisease": "Doctors by disease",
    "doctorProfileDescription": "{{name}} — {{specialty}}, {{place}}. A profile built from public sources.",
    "doctorPrivacyNote": "Is this you? Write to kontakt@genequest.org and we will correct this entry or remove it and keep it out of future updates of the directory.",
    "trialsForTitle": "Clinical trials for {{disease}}",
    "trialsDescription": "Clinical trials catalogued for {{disease}} from ClinicalTrials.gov, with their recruitment status and sites.",
    "trialsDirectoryDescription": "Clinical trials catalogued for rare genetic diseases from ClinicalTrials.gov, with their recruitment status and sites.",
    "trialsByDisease": "Clinical trials by disease",
    "doctorsCount": "Doctors listed: {{count}}",
    "trialsCount": "Clinical trials catalogued: {{count}}",
    "shownOf": "Showing {{shown}} of {{total}}.",
    "noneYet": "Nothing is listed here yet.",
    "lastUpdated": "Last revised: {{date}}",
    "cited": "Cited:",
    "unknownTitle": "A disease without a page yet",
    "unknownBody": "We have no researched page for this disease yet. The catalogue grows when someone runs research for a disease.",
}

_cache: dict[str, Any] = {"key": None, "data": {}}
_PLACEHOLDER = re.compile(r"\{\{\s*(\w+)\s*\}\}")


def _load(static_dir: Path) -> dict[str, dict[str, str]]:
    """The bundle's label map, re-read only when the file changes (a deploy swaps the bundle)."""
    path = static_dir / STRINGS_FILE
    try:
        stat = path.stat()
    except OSError:
        return {}
    key = (str(path), stat.st_mtime_ns, stat.st_size)
    if _cache["key"] == key:
        return _cache["data"]
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        log.warning("seo: could not read %s; rendering with English fallbacks", path)
        data = {}
    if not isinstance(data, dict):
        data = {}
    _cache["key"] = key
    _cache["data"] = data
    return data


def labels(static_dir: Path, locale: str) -> dict[str, str]:
    """Every label for ``locale``: the fallbacks, overlaid with English from the bundle, overlaid with the locale's own."""
    data = _load(static_dir)
    merged = dict(FALLBACK_EN)
    for source in (data.get("en"), data.get(locale)):
        if isinstance(source, dict):
            merged.update({k: v for k, v in source.items() if isinstance(v, str) and v.strip()})
    return merged


def fill(template: str, **values: object) -> str:
    """Replace ``{{name}}`` placeholders the way i18next does; an unknown name is left out rather than shown raw."""
    return _PLACEHOLDER.sub(lambda m: str(values.get(m.group(1), "")), template)
