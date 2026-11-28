"""The readable version of each public page, built from the same data the React view renders.

Every function returns a :class:`Page` whose body is already escaped HTML. Labels come from the locale catalogues (strings.py), content from the services (data.py). Nothing here invents content: where the database has nothing, the page says so in the app's own words.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from typing import Any

from pydantic import ValidationError

from ..content.models import Disease
from ..content.trials_models import Trial
from ..content_models import PublicDoctorResponse
from ..guidelines.models import GuidelineSynthesis, SourceDocument
from .document import Page, esc, shorten, with_locale
from .strings import fill

Labels = Mapping[str, str]
MAX_DOCTORS = 50
_PMID = re.compile(r"^(?:pmid:?\s*)?(\d{5,9})$", re.I)


def _p(text: str) -> str:
    return f"<p>{esc(text)}</p>"


def _note(text: str) -> str:
    return f'<p class="ggp-note">{esc(text)}</p>'


def _a(path: str, label: str, locale: str) -> str:
    return f'<a href="{esc(with_locale(path, locale))}">{esc(label)}</a>'


def _nav(links: Iterable[tuple[str, str]], locale: str) -> str:
    return f'<nav class="ggp-links">{" · ".join(_a(path, label, locale) for path, label in links)}</nav>'


def _site_links(L: Labels, locale: str, *extra: tuple[str, str]) -> str:
    return _nav([*extra, ("/diseases", L["linkDiseases"]), ("/doctors", L["linkAllDoctors"]), ("/about", L["linkAbout"])], locale)


def _titled(title: str, L: Labels) -> str:
    return f"{title}{L['titleSuffix']}"


def _condition(disease: Disease) -> dict[str, Any]:
    about: dict[str, Any] = {"@type": "MedicalCondition", "name": disease.name}
    omim = (disease.omim or "").strip().lstrip("#")
    if omim:
        about["code"] = {"@type": "MedicalCode", "codeValue": omim, "codingSystem": "OMIM"}
    return {"about": about}


def diseases_index(diseases: list[Disease], L: Labels, locale: str) -> Page:
    items = "\n".join(
        f'<li><p class="ggp-q">{_a(f"/diseases/{d.slug}", d.name, locale)}</p>{_p(shorten(d.summary, 240))}</li>'
        for d in diseases
    )
    body = "\n".join(
        [f"<h1>{esc(L['diseasesTitle'])}</h1>", _p(L["diseasesDescription"]), f'<ul class="ggp-rows">{items}</ul>', _note(L["footerDesc"]), _site_links(L, locale)]
    )
    return Page(path="/diseases", title=_titled(L["diseasesTitle"], L), description=L["diseasesDescription"], body=body)


def unknown_disease(path: str, L: Labels, locale: str) -> Page:
    """A slug we have no row for. The app shows a "not yet researched" stub there, so the page answers 200, but nothing about it is worth indexing."""
    body = "\n".join([f"<h1>{esc(L['unknownTitle'])}</h1>", _p(L["unknownBody"]), _site_links(L, locale)])
    return Page(path=path, title=_titled(L["unknownTitle"], L), description=L["unknownBody"], body=body, noindex=True)


def _guideline_points(block: Mapping[str, Any] | None, L: Labels, locale: str) -> str:
    """The generated diagnosis block, in the page's language, with its fixed AI notice, each quote's source link and credit, and its source note. Empty when there is no published block."""
    if not block or not block.get("points"):
        return ""
    pl = locale == "pl"
    items = []
    for p in block["points"]:
        link = f'<a href="{esc(p.get("doc_url") or "")}">{esc(p.get("doc_citation") or p.get("doc_title") or "")}</a>' if p.get("doc_url") else esc(p.get("doc_citation") or "")
        credit = f" {esc(p['credit'])}" if p.get("credit") else ""
        items.append(
            "<li>"
            + _p(p["summary_pl"] if pl else p["summary_en"])
            + _p(p["question_pl"] if pl else p["question_en"])
            + f'<blockquote cite="{esc(p.get("doc_url") or "")}"><p>{esc(p["quote"])}</p></blockquote>'
            + f'<p class="ggp-note">{link}{credit}</p>'
            + "</li>"
        )
    return (
        '<section class="ggp-points">'
        + f"<h2>{esc(block['title_pl'] if pl else block['title_en'])}</h2>"
        + _note(block["notice_pl"] if pl else block["notice_en"])
        + f"<ol>{''.join(items)}</ol>"
        + _note(block["source_pl"] if pl else block["source_en"])
        + "</section>"
    )


def disease_hub(d: Disease, L: Labels, locale: str, points: Mapping[str, Any] | None = None) -> Page:
    facts = [(L["factGene"], d.gene), (L["factOmim"], d.omim), (L["factInheritance"], d.inheritance), (L["factPrevalence"], d.prevalence_text)]
    dl = "".join(f"<dt>{esc(k)}</dt><dd>{esc(v)}</dd>" for k, v in facts if str(v or "").strip())
    parts = [f'<p class="ggp-note">{esc(d.name_short)}</p>' if d.name_short and d.name_short != d.name else "", f"<h1>{esc(d.name)}</h1>"]
    if not d.listed:
        parts.append(_note(L["notListed"]))
    parts += [
        _p(d.summary) if d.summary else "",
        f'<dl class="ggp-facts">{dl}</dl>' if dl else "",
        _p(fill(L["doctorsCount"], count=d.doctors_count)),
        _p(fill(L["trialsCount"], count=d.trials_count)),
        _guideline_points(points, L, locale),
        _nav(
            [
                (f"/diseases/{d.slug}/guidelines", L["linkGuidelines"]),
                (f"/doctors?disease={d.slug}", fill(L["doctorsForTitle"], disease=d.name)),
                (f"/trials?disease={d.slug}", fill(L["trialsForTitle"], disease=d.name)),
            ],
            locale,
        ),
        _note(L["footerDesc"]),
        _site_links(L, locale),
    ]
    description = shorten(d.summary) if d.summary else fill(L["hubDescription"], disease=d.name)
    return Page(
        path=f"/diseases/{d.slug}",
        title=_titled(d.name, L),
        description=description,
        body="\n".join(p for p in parts if p),
        noindex=not d.listed,
        og_type="article",
        json_ld_extra=_condition(d),
    )


def _doc_link(doc: SourceDocument) -> str | None:
    if doc.pmid:
        return f"https://pubmed.ncbi.nlm.nih.gov/{doc.pmid}/"
    if doc.pmcid:
        return f"https://www.ncbi.nlm.nih.gov/pmc/articles/{doc.pmcid}/"
    if doc.bookshelf:
        return f"https://www.ncbi.nlm.nih.gov/books/{doc.bookshelf}/"
    return None


def _citation(value: Any, docs: Mapping[str, SourceDocument], L: Labels) -> str:
    raw = value.get("sourceId") or value.get("source_id") if isinstance(value, dict) else value
    text = str(raw or "").strip()
    if not text:
        return ""
    pmid = _PMID.match(text)
    if pmid:
        return f'<a href="https://pubmed.ncbi.nlm.nih.gov/{pmid.group(1)}/">{esc(fill(L["pmidLabel"], pmid=pmid.group(1)))}</a>'
    doc = docs.get(text)
    if doc is not None:
        link = _doc_link(doc)
        return f'<a href="{esc(link)}">{esc(doc.title)}</a>' if link else esc(doc.title)
    return esc(text)


def _paragraph(para: Mapping[str, Any], docs: Mapping[str, SourceDocument], L: Labels) -> str:
    out = [_p(str(para.get("text") or ""))]
    cites = [c for c in (_citation(v, docs, L) for v in para.get("citations") or []) if c]
    source = para.get("source") if isinstance(para.get("source"), dict) else {}
    doc = docs.get(str(source.get("doc") or ""))
    basis = " · ".join(x for x in (esc(doc.title) if doc else "", esc(source.get("loc") or "")) if x)
    if cites or basis:
        line = f"{esc(L['cited'])} {', '.join(cites)}" if cites else ""
        out.append(f'<p class="ggp-note">{" — ".join(x for x in (line, basis) if x)}</p>')
    return "".join(out)


def _sections(sections: list[dict[str, Any]], docs: Mapping[str, SourceDocument], L: Labels) -> list[str]:
    out: list[str] = []
    for section in sections or []:
        if not isinstance(section, dict):
            continue
        out.append(f"<h2>{esc(section.get('title') or '')}</h2>")
        if section.get("intro"):
            out.append(_p(str(section["intro"])))
        paragraphs = [p for p in section.get("paragraphs") or [] if isinstance(p, dict) and str(p.get("text") or "").strip()]
        if section.get("noSource") or not paragraphs:
            out.append(_note(L["sectionNoSourceNote"]))
        out += [_paragraph(p, docs, L) for p in paragraphs]
    return out


def _shelf(docs: list[SourceDocument], L: Labels) -> list[str]:
    if not docs:
        return []
    rows = []
    for doc in docs:
        meta = ", ".join(x for x in (doc.authors, doc.journal, doc.year) if x)
        link = _doc_link(doc)
        title = f'<a href="{esc(link)}">{esc(doc.title)}</a>' if link else esc(doc.title)
        rows.append(f'<li><p class="ggp-q">{title}</p>{_p(meta) if meta else ""}</li>')
    return [f"<h2>{esc(L['shelfTitle'])}</h2>", f'<ul class="ggp-rows">{"".join(rows)}</ul>']


def guidelines_page(d: Disease, synthesis: GuidelineSynthesis | None, docs: list[SourceDocument], L: Labels, locale: str) -> Page:
    title = fill(L["guidelinesTitle"], disease=d.name)
    path = f"/diseases/{d.slug}/guidelines"
    back = (f"/diseases/{d.slug}", d.name)
    if synthesis is None:
        # Level (c), or a synthesis withheld by the evidence gate: the app's own honest message, and nothing to index.
        body = "\n".join(
            [_note(L["versionNoGuideline"]), f"<h1>{esc(title)}</h1>", f"<h2>{esc(L['noGuidelineTitle'])}</h2>", _p(fill(L["noGuidelineBody"], disease=d.name)), _site_links(L, locale, back)]
        )
        return Page(path=path, title=_titled(title, L), description=fill(L["noGuidelineBody"], disease=d.name), body=body, noindex=True, json_ld_extra=_condition(d))
    by_id = {doc.doc_id: doc for doc in docs}
    parts = [
        _note(synthesis.version) if synthesis.version else "",
        f"<h1>{esc(title)}</h1>",
        # One disclaimer, not two: the synthesis carries its own; the site-wide sentence stands in only when it is empty.
        _note(synthesis.synth_disclaimer or L["footerDesc"]),
        _note(f"{L['basedOn']} {synthesis.based_on}") if synthesis.based_on else "",
        _note(fill(L["lastUpdated"], date=synthesis.last_updated)) if synthesis.last_updated else "",
        # The summary is written for clinicians. A crawler, a link preview or a language model reading this copy passes it on to a parent, so the copy says whose text it is, as the page does (the app keeps it closed under this label).
        _note(f"{L['clinicalSummaryHeading']}. {L['clinicalSummaryNote']}"),
        *_sections(synthesis.sections, by_id, L),
        *_shelf(docs, L),
        _site_links(L, locale, back),
    ]
    return Page(
        path=path,
        title=_titled(title, L),
        description=fill(L["guidelinesDescription"], disease=d.name),
        body="\n".join(p for p in parts if p),
        noindex=not d.listed,
        og_type="article",
        json_ld_extra=_condition(d),
    )


# The only doctor fields a server-rendered page reads. Anything else a row carries — contact details, an e-mail — never reaches the model, let alone the page.
_DOCTOR_FIELDS = ("slug", "name", "specialty", "institution", "city", "country", "diseases", "pubmedRole", "score")


def public_doctor(row: Mapping[str, Any]) -> PublicDoctorResponse | None:
    """The rendered fields, validated by the public API's own model; a row that would not pass the API is not shown."""
    try:
        return PublicDoctorResponse.model_validate({k: row[k] for k in _DOCTOR_FIELDS if k in row})
    except ValidationError:
        return None


def _place(doc: PublicDoctorResponse) -> str:
    return ", ".join(x for x in (doc.institution, doc.city, doc.country) if x)


def doctors_for_disease(d: Disease, rows: list[dict[str, Any]], L: Labels, locale: str) -> Page:
    doctors = sorted((x for x in map(public_doctor, rows) if x is not None), key=lambda x: (-x.score, x.name))
    shown = doctors[:MAX_DOCTORS]
    items = "\n".join(
        f'<li><p class="ggp-q">{_a(f"/doctor/{x.slug}", x.name, locale)}</p>{_p(" · ".join(y for y in (x.specialty, _place(x)) if y))}</li>' for x in shown
    )
    title = fill(L["doctorsForTitle"], disease=d.name)
    parts = [
        f"<h1>{esc(title)}</h1>",
        _p(L["doctorsLead"]),
        _p(fill(L["shownOf"], shown=len(shown), total=len(doctors))) if doctors else _p(L["noneYet"]),
        f'<ul class="ggp-rows">{items}</ul>' if items else "",
        _note(L["doctorsProvenance"]),
        _site_links(L, locale, (f"/diseases/{d.slug}", d.name)),
    ]
    return Page(
        path=f"/doctors?disease={d.slug}",
        title=_titled(title, L),
        description=fill(L["doctorsDescription"], disease=d.name),
        body="\n".join(p for p in parts if p),
        noindex=not d.listed or not doctors,
    )


def doctors_directory(diseases: list[Disease], L: Labels, locale: str) -> Page:
    items = "\n".join(
        f'<li>{_a(f"/doctors?disease={d.slug}", fill(L["doctorsForTitle"], disease=d.name), locale)} — {esc(fill(L["doctorsCount"], count=d.doctors_count))}</li>' for d in diseases
    )
    body = "\n".join(
        [f"<h1>{esc(L['doctorsTitle'])}</h1>", _p(L["doctorsLead"]), f"<h2>{esc(L['doctorsByDisease'])}</h2>", f'<ul class="ggp-rows">{items}</ul>', _note(L["doctorsProvenance"]), _site_links(L, locale)]
    )
    return Page(path="/doctors", title=_titled(L["doctorsTitle"], L), description=L["directoryDescription"], body=body)


def doctor_profile(row: Mapping[str, Any], L: Labels, locale: str, names: Mapping[str, str] | None = None) -> Page | None:
    """Readable, but never indexed: profiles are added on legitimate interest with an opt-out (ADR 009), and a search engine should not be the place a doctor first meets theirs."""
    doc = public_doctor(row)
    if doc is None:
        return None
    diseases = "".join(f"<li>{_a(f'/diseases/{slug}', (names or {}).get(slug, slug), locale)}</li>" for slug in doc.diseases)
    parts = [
        f"<h1>{esc(doc.name)}</h1>",
        _p(doc.specialty) if doc.specialty else "",
        _p(_place(doc)) if _place(doc) else "",
        f"<h2>{esc(L['doctorDiseases'])}</h2><ul>{diseases}</ul>" if diseases else "",
        _note(L["doctorsProvenance"]),
        _note(L["doctorPrivacyNote"]),
        _site_links(L, locale),
    ]
    description = fill(L["doctorProfileDescription"], name=doc.name, specialty=doc.specialty, place=_place(doc))
    return Page(path=f"/doctor/{doc.slug}", title=_titled(doc.name, L), description=description, body="\n".join(p for p in parts if p), noindex=True, og_type="profile")


def _trial(trial: Trial, L: Labels) -> str:
    facts = " · ".join(
        x for x in (f"{L['trialsPhase']}: {trial.phase}" if trial.phase else "", f"{L['trialsStatus']}: {trial.status}" if trial.status else "", trial.sponsor, ", ".join(y for y in (trial.city, trial.country) if y)) if x
    )
    link = f'<a href="https://clinicaltrials.gov/study/{esc(trial.nct)}">{esc(L["trialsRegistryLink"])}</a>' if trial.nct else ""
    return f'<li><p class="ggp-q">{esc(trial.title)}</p>{_p(facts) if facts else ""}{f"<p>{link}</p>" if link else ""}</li>'


def trials_for_disease(d: Disease, trials: list[Trial], L: Labels, locale: str) -> Page:
    title = fill(L["trialsForTitle"], disease=d.name)
    parts = [
        f"<h1>{esc(title)}</h1>",
        _p(L["trialsLead"]),
        f'<ul class="ggp-rows">{"".join(_trial(t, L) for t in trials)}</ul>' if trials else _p(L["noneYet"]),
        _note(L["trialsProvenance"]),
        _site_links(L, locale, (f"/diseases/{d.slug}", d.name)),
    ]
    return Page(
        path=f"/trials?disease={d.slug}",
        title=_titled(title, L),
        description=fill(L["trialsDescription"], disease=d.name),
        body="\n".join(p for p in parts if p),
        noindex=not d.listed or not trials,
    )


def trials_directory(diseases: list[Disease], L: Labels, locale: str) -> Page:
    items = "\n".join(
        f'<li>{_a(f"/trials?disease={d.slug}", fill(L["trialsForTitle"], disease=d.name), locale)} — {esc(fill(L["trialsCount"], count=d.trials_count))}</li>' for d in diseases
    )
    body = "\n".join(
        [f"<h1>{esc(L['trialsTitle'])}</h1>", _p(L["trialsLead"]), f"<h2>{esc(L['trialsByDisease'])}</h2>", f'<ul class="ggp-rows">{items}</ul>', _note(L["trialsProvenance"]), _site_links(L, locale)]
    )
    return Page(path="/trials", title=_titled(L["trialsTitle"], L), description=L["trialsDirectoryDescription"], body=body)
