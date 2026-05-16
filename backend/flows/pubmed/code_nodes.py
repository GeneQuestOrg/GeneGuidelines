from __future__ import annotations

PM_GATE_SOURCE = """def run(context):
    outs = context.get("outputs", {})
    pm2_out = outs.get("pm-2", {})
    pm2 = pm2_out.get("result", pm2_out) if isinstance(pm2_out, dict) else {}
    n = int(pm2.get("article_count", 0) or 0)
    retrieval_ok = bool(pm2.get("retrieval_ok", n > 0))
    has_core = bool(pm2.get("has_core_buckets", True))
    per_domain = pm2.get("per_domain_pmid_counts") if isinstance(pm2.get("per_domain_pmid_counts"), dict) else {}
    min_domain_threshold = 10
    diagnostics_n = int(per_domain.get("diagnostics", 0) or 0)
    treatment_n = int(per_domain.get("treatment", 0) or 0)
    followup_n = int(per_domain.get("follow_up", 0) or 0)
    domain_coverage_ok = (
        diagnostics_n >= min_domain_threshold
        and treatment_n >= min_domain_threshold
        and followup_n >= min_domain_threshold
    )
    warning = ""
    warnings = []
    if not retrieval_ok:
        warning = "no_articles"
        warnings.append("No articles retrieved from PubMed.")
    elif not has_core:
        warning = "missing_core_buckets"
        warnings.append("Core buckets missing: diagnostics/treatment/follow_up.")
    elif not domain_coverage_ok:
        warning = "low_domain_coverage"
        warnings.append("Domain coverage below minimum threshold for at least one core domain.")
    retrieval_channel = str(pm2.get("retrieval_channel") or "primary_get")
    if retrieval_channel != "primary_get":
        warnings.append("Retrieval used fallback channel: " + retrieval_channel)
    return {
        "quality_ok": True,
        "article_count": n,
        "has_core_buckets": has_core,
        "warning_reason": warning,
        "warnings": warnings,
        "min_domain_threshold": min_domain_threshold,
        "domain_coverage_ok": domain_coverage_ok,
        "per_domain_pmid_counts": per_domain,
        "retrieval_channel": retrieval_channel,
    }
"""

PM_MERGE_SOURCE = """def run(context):
    outs = context.get("outputs", {})

    def _get_payload(nid):
        out = outs.get(nid, {})
        if isinstance(out, dict) and "result" in out and isinstance(out["result"], dict):
            return out["result"]
        return out if isinstance(out, dict) else {}

    pm2_out = outs.get("pm-2", {})
    pm2 = pm2_out.get("result", pm2_out) if isinstance(pm2_out, dict) else {}
    source_links_html = pm2.get("source_links_html", "<p>No sources available.</p>")

    sections = [
        ("pm-4-overview", "Overview", "pass1-overview"),
        ("pm-4-epidemiology", "Epidemiology", "pass1-epidemiology"),
        ("pm-4-pathogenesis", "Pathogenesis", "pass1-pathogenesis"),
        ("pm-4-diagnostics", "Diagnostics", "pass1-diagnostics"),
        ("pm-4-red-flags", "Red Flags & Contraindications", None),
        ("pm-4-treatment", "Treatment", "pass1-treatment"),
        ("pm-4-monitoring", "Monitoring", "pass1-monitoring"),
        ("pm-4-followup", "Follow-Up & Outcomes", "pass1-followup"),
        ("pm-4-references", "References & Evidence Gaps", None),
    ]

    text_sections = []
    html_sections = []
    all_pmids = []
    domain_counts = {}

    for nid, label, pass1_id in sections:
        section = _get_payload(nid)
        pass1 = _get_payload(pass1_id) if pass1_id else {}
        section_html = str(section.get("section_html") or "")
        key_findings = str(pass1.get("key_findings") or "(no data)")
        evidence_gaps = str(pass1.get("evidence_gaps") or "")
        strength = str(pass1.get("strength_of_evidence") or "unknown")
        contradictions = str(pass1.get("contradictions") or "")
        key_pmids = str(pass1.get("key_pmids_cited") or "")
        art_count = int(pass1.get("article_count_processed", 0) or 0)
        domain_counts[label] = art_count
        if key_pmids:
            all_pmids.extend([p.strip() for p in key_pmids.split(",") if p.strip()])

        text_sections.append(
            "=== " + label + " ===\\n"
            "Evidence strength: " + strength + "\\n"
            "Articles processed: " + str(art_count) + "\\n"
            "Key findings: " + key_findings + "\\n"
            "Contradictions: " + contradictions + "\\n"
            "Evidence gaps: " + evidence_gaps + "\\n"
            "Key PMIDs: " + key_pmids + "\\n"
        )

        html_sections.append(
            "<section class=\\"domain-synthesis\\">"
            "<h3>" + label + " <span class=\\"badge\\">" + strength + "</span></h3>"
            "<p><strong>Artykuly przeanalizowane:</strong> " + str(art_count) + "</p>"
            "<p><strong>Kluczowe ustalenia:</strong> " + key_findings + "</p>"
            "<p><strong>Sprzecznosci:</strong> " + contradictions + "</p>"
            "<p><strong>Luki w dowodach:</strong> " + evidence_gaps + "</p>"
            "<p><em>Cytowane PMID: " + key_pmids + "</em></p>"
            + ("<div>" + section_html + "</div>" if section_html else "")
            + "</section>"
        )

    all_pmids_unique = sorted(set(all_pmids))
    counts_text = "; ".join(k + ": " + str(v) for k, v in domain_counts.items())

    return {
        "evidence_base_text": "\\n\\n".join(text_sections),
        "evidence_base_html": "\\n".join(html_sections),
        "source_links_html": source_links_html,
        "all_cited_pmids": ", ".join(all_pmids_unique),
        "domain_article_counts": counts_text,
        "total_articles_synthesized": sum(domain_counts.values()),
    }
"""

PM4_BUILD_SOURCE = """def run(context):
    import re
    outs = context.get("outputs", {})

    def _unwrap(node_id):
        raw = outs.get(node_id) or {}
        if isinstance(raw, dict) and "result" in raw and isinstance(raw["result"], dict):
            return raw["result"]
        return raw

    overview = _unwrap("pm-4-overview")
    epidemiology = _unwrap("pm-4-epidemiology")
    pathogenesis = _unwrap("pm-4-pathogenesis")
    diagnostics = _unwrap("pm-4-diagnostics")
    red_flags = _unwrap("pm-4-red-flags")
    treatment = _unwrap("pm-4-treatment")
    monitoring = _unwrap("pm-4-monitoring")
    followup = _unwrap("pm-4-followup")
    references = _unwrap("pm-4-references")

    grade = outs.get("pm-3", {})
    if isinstance(grade, dict) and "result" in grade and isinstance(grade["result"], dict):
        grade = grade["result"]
    pm2_out = outs.get("pm-2", {})
    if isinstance(pm2_out, dict) and "result" in pm2_out and isinstance(pm2_out["result"], dict):
        pm2_out = pm2_out["result"]

    disease_name = overview.get("disease_name") or "Unknown Disease"

    section_parts = [
        ("overview", "Overview", overview),
        ("epidemiology", "Epidemiology", epidemiology),
        ("pathogenesis", "Pathogenesis", pathogenesis),
        ("diagnostics", "Diagnostics", diagnostics),
        ("red-flags", "Red Flags &amp; Contraindications", red_flags),
        ("treatment", "Treatment &amp; Management", treatment),
        ("monitoring", "Monitoring Protocol", monitoring),
        ("follow-up", "Follow-Up &amp; Prognosis", followup),
        ("references", "References &amp; Evidence Gaps", references),
    ]
    sections = []
    for sid, heading, data in section_parts:
        html = data.get("section_html") or ""
        if html:
            sections.append("<section id='" + sid + "'><h2>" + heading + "</h2>" + html + "</section>")
    guideline_html = "\\n".join(sections)
    references_text = str(references.get("references") or "").strip()
    source_links_html = str(_unwrap("pm-merge").get("source_links_html") or "")
    article_count = int(pm2_out.get("article_count") or 0)
    cited_pmids = set()
    for pattern in [r"PMID[:\\s]+([0-9]{6,10})", r"/pubmed/([0-9]{6,10})", r"pubmed\\.ncbi[^/]*/([0-9]{6,10})"]:
        cited_pmids.update(re.findall(pattern, guideline_html, re.IGNORECASE))
    has_transparent_sources = bool(article_count > 0 and (cited_pmids or references_text))
    warning_html = ""
    if not has_transparent_sources:
        warning_html = (
            "<section id='source-transparency-warning'>"
            "<h2>Source Transparency Warning</h2>"
            "<p>The run has weak citation transparency. Review and verify PMID support before clinical use.</p>"
            "</section>"
        )
        guideline_html = warning_html + guideline_html

    return {
        "disease_name": disease_name,
        "guideline_html": guideline_html,
        "diagnostic_algorithm_html": diagnostics.get("section_html") or "",
        "treatment_steps_html": treatment.get("section_html") or "",
        "monitoring_protocol_html": monitoring.get("section_html") or "",
        "recommendation_matrix_html": "",
        "red_flags_html": red_flags.get("section_html") or "",
        "contraindications_html": "",
        "follow_up_schedule_html": followup.get("section_html") or "",
        "evidence_gaps_html": references.get("section_html") or "",
        "disclaimer_html": references.get("disclaimer_html") or "",
        "key_updates": overview.get("key_updates") or "",
        "confidence_level": grade.get("confidence_level") or grade.get("evidence_level") or "low",
        "evidence_score": grade.get("evidence_score") or 0,
        "confidence_index": grade.get("confidence_index") or 0,
        "reliability_assessment_html": "",
        "source_links_html": source_links_html,
        "references": references.get("references") or "",
        "article_count": article_count,
        "sources_transparency_ok": has_transparent_sources,
        "sources_transparency_warning": not has_transparent_sources,
        "cited_pmids_count": len(cited_pmids),
    }
"""

PM5_SOURCE = """def run(context):
    import re
    outs = context.get("outputs", {})

    pm4 = outs.get("pm-4-build", {})
    if isinstance(pm4, dict) and "result" in pm4 and isinstance(pm4["result"], dict):
        pm4 = pm4["result"]
    guideline_html = str(pm4.get("guideline_html", "") or "")

    pm2_out = outs.get("pm-2", {})
    pm2 = pm2_out.get("result", pm2_out) if isinstance(pm2_out, dict) else {}
    retrieved_pmids = set(str(p).strip() for p in (pm2.get("article_pmids", []) or []) if str(p).strip())
    sources_transparency_ok = bool(pm4.get("sources_transparency_ok", True))

    cited_pmids = set()
    for pattern in [r"PMID[:\\s]+([0-9]{6,10})", r"/pubmed/([0-9]{6,10})", r"pubmed\\.ncbi[^/]*/([0-9]{6,10})"]:
        cited_pmids.update(re.findall(pattern, guideline_html, re.IGNORECASE))

    valid = cited_pmids & retrieved_pmids
    invalid = cited_pmids - retrieved_pmids
    n_cited = len(cited_pmids)
    n_retrieved = len(retrieved_pmids)
    coverage_pct = round(len(valid) / n_cited * 100) if n_cited > 0 else 0
    warnings = []
    if not sources_transparency_ok:
        badge = "SOURCE_TRANSPARENCY_WARN"
        warnings.append("Guideline generated with weak source transparency; manual review required.")
    elif n_cited == 0:
        badge = "NO_CITATIONS"
        warnings.append("No inline PMIDs were found in generated guideline.")
    elif coverage_pct >= 90:
        badge = "EVIDENCE_GROUNDED"
    elif coverage_pct >= 60:
        badge = "PARTIALLY_GROUNDED"
    elif len(invalid) > 0:
        badge = "CITATION_ERRORS"
        warnings.append("Some cited PMIDs are not present in retrieved corpus.")
    else:
        badge = "LOW_GROUNDING"
        warnings.append("Citation grounding is below expected threshold.")

    return {
        "validation_badge": badge,
        "citation_coverage_pct": coverage_pct,
        "pmids_cited": n_cited,
        "pmids_retrieved": n_retrieved,
        "invalid_citations": list(invalid)[:20],
        "invalid_citations_count": len(invalid),
        "sources_transparency_ok": sources_transparency_ok,
        "warnings": warnings,
        "validation_passed": True,
    }
"""
