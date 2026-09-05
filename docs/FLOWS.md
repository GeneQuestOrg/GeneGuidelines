# Flows

> Generated from `backend/flows/specs/*.json` by
> `python3 -m backend.scripts.render_flow_diagrams`. Do not edit by hand — the
> specs are what the engine actually executes, so they are the source of truth
> and this file is only a view of them. `--check` fails when the two drift.

Colours follow the executor domain packages: **guidelines** (blue), **doctors** (green), **pathways** (amber), shared core (grey).

## guideline_factcheck

Fact-check pass (research pipeline step 4): for each synthesis paragraph, verify against the abstract of the source it cites whether the claim is actually supported. Produces a per-paragraph verdict report (supported / unsupported / uncertain) as the run output — a pre-pass for the domain expert before publication, not a public data write. Set gfc-check.model_name to a stronger model for the judgement.

```mermaid
flowchart TD
    classDef guidelines fill:#e8f0fe,stroke:#4285f4,color:#1a3d6d;
    classDef doctors fill:#e6f4ea,stroke:#34a853,color:#1e4620;
    classDef pathways fill:#fef7e0,stroke:#f9ab00,color:#5c4400;
    classDef core fill:#f1f3f4,stroke:#9aa0a6,color:#3c4043;
    start["Start<br/><i>trigger</i>"]
    gfc_load["Load claims + cited sources<br/><i>guideline_factcheck_load</i>"]
    gfc_check["Fact-check claims vs sources<br/><i>prompt</i>"]
    end_node["End<br/><i>end</i>"]
    start --> gfc_load
    gfc_load --> gfc_check
    gfc_check --> end_node
    class start core;
    class gfc_load guidelines;
    class gfc_check core;
    class end_node core;
```

## guideline_shelf_build

Build the curated source shelf for a disease (step 1 of the research pipeline). Broadly searches PubMed + NCBI Bookshelf, an LLM classifies which documents belong on the shelf and the role of each (base consensus / update / subtopic / reference compendium), and the writer replaces guideline_source_documents. The synthesis flow (guideline_synthesis) consumes this shelf. Deterministic recall validation lives OUTSIDE the workflow (scripts/validate_shelf_fd.py).

```mermaid
flowchart TD
    classDef guidelines fill:#e8f0fe,stroke:#4285f4,color:#1a3d6d;
    classDef doctors fill:#e6f4ea,stroke:#34a853,color:#1e4620;
    classDef pathways fill:#fef7e0,stroke:#f9ab00,color:#5c4400;
    classDef core fill:#f1f3f4,stroke:#9aa0a6,color:#3c4043;
    start["Start<br/><i>trigger</i>"]
    gsb_search["Search PubMed + Bookshelf<br/><i>guideline_shelf_search</i>"]
    gsb_classify["Classify the shelf<br/><i>prompt</i>"]
    gsb_write["Write the shelf<br/><i>guideline_shelf_write</i>"]
    gsb_bib["Record analyzed bibliography<br/><i>guideline_bibliography_write</i>"]
    end_node["End<br/><i>end</i>"]
    start --> gsb_search
    gsb_search --> gsb_classify
    gsb_classify --> gsb_write
    gsb_write --> gsb_bib
    gsb_bib --> end_node
    class start core;
    class gsb_search guidelines;
    class gsb_classify core;
    class gsb_write guidelines;
    class gsb_bib guidelines;
    class end_node core;
```

## guideline_suggestions

Level-b monitor (research pipeline step 3): find recent literature beyond the shelf, triage cheaply for whether each paper changes the guideline vs what the synthesis ALREADY says, then a (stronger) model proposes deltas — additions/modifications beyond current guidance. Empty is a valid answer. Budget-disciplined: bounded candidate set, cheap Gemma triage, strong model only on the short list. Deterministic checks live in tests/scripts, not here.

```mermaid
flowchart TD
    classDef guidelines fill:#e8f0fe,stroke:#4285f4,color:#1a3d6d;
    classDef doctors fill:#e6f4ea,stroke:#34a853,color:#1e4620;
    classDef pathways fill:#fef7e0,stroke:#f9ab00,color:#5c4400;
    classDef core fill:#f1f3f4,stroke:#9aa0a6,color:#3c4043;
    start["Start<br/><i>trigger</i>"]
    gsd_search["Load guidance + recent papers<br/><i>guideline_monitor_search</i>"]
    gsd_triage["Triage (cheap): does it change anything?<br/><i>prompt</i>"]
    gsd_delta["Propose deltas (stronger model)<br/><i>prompt</i>"]
    gsd_write["Write suggestions<br/><i>guideline_suggestion_writer</i>"]
    gsd_bib["Record analyzed bibliography<br/><i>guideline_bibliography_write</i>"]
    end_node["End<br/><i>end</i>"]
    start --> gsd_search
    gsd_search --> gsd_triage
    gsd_triage --> gsd_delta
    gsd_delta --> gsd_write
    gsd_write --> gsd_bib
    gsd_bib --> end_node
    class start core;
    class gsd_search guidelines;
    class gsd_triage core;
    class gsd_delta core;
    class gsd_write guidelines;
    class gsd_bib guidelines;
    class end_node core;
```

## guideline_synthesis

Synthesis over a curated source shelf (epistemic level a). Loads the disease's source documents + abstracts, synthesises one section per node strictly from the shelf (provenance per paragraph), and the terminal writer assembles + upserts the synthesis into the GL-4 guideline_synthesis table. The anti-hallucination critic backbone (pmid_verify / source_doc_verify / evaluation_check) is wired in GL-ENGINE-2.

```mermaid
flowchart TD
    classDef guidelines fill:#e8f0fe,stroke:#4285f4,color:#1a3d6d;
    classDef doctors fill:#e6f4ea,stroke:#34a853,color:#1e4620;
    classDef pathways fill:#fef7e0,stroke:#f9ab00,color:#5c4400;
    classDef core fill:#f1f3f4,stroke:#9aa0a6,color:#3c4043;
    start["Start<br/><i>trigger</i>"]
    gs_shelf["Load source shelf<br/><i>guideline_shelf_load</i>"]
    gs_sec_diagnosis["Synthesise: Diagnosis<br/><i>prompt</i>"]
    gs_sec_histopathology["Synthesise: Histopathology & genetics<br/><i>prompt</i>"]
    gs_sec_therapy["Synthesise: Therapy<br/><i>prompt</i>"]
    gs_sec_surgery["Synthesise: Indications for surgery<br/><i>prompt</i>"]
    gs_sec_monitoring["Synthesise: Monitoring & follow-up<br/><i>prompt</i>"]
    gs_quotes_load["Load claims + cited abstracts<br/><i>guideline_quote_extract_load</i>"]
    gs_quotes["Extract grounded source paraphrases<br/><i>prompt</i>"]
    gs_write["Assemble + write synthesis<br/><i>guideline_synthesis_writer</i>"]
    end_node["End<br/><i>end</i>"]
    start --> gs_shelf
    gs_shelf --> gs_sec_diagnosis
    gs_shelf --> gs_sec_histopathology
    gs_shelf --> gs_sec_therapy
    gs_shelf --> gs_sec_surgery
    gs_shelf --> gs_sec_monitoring
    gs_sec_diagnosis --> gs_quotes_load
    gs_sec_histopathology --> gs_quotes_load
    gs_sec_therapy --> gs_quotes_load
    gs_sec_surgery --> gs_quotes_load
    gs_sec_monitoring --> gs_quotes_load
    gs_quotes_load --> gs_quotes
    gs_quotes --> gs_write
    gs_write --> end_node
    class start core;
    class gs_shelf guidelines;
    class gs_sec_diagnosis core;
    class gs_sec_histopathology core;
    class gs_sec_therapy core;
    class gs_sec_surgery core;
    class gs_sec_monitoring core;
    class gs_quotes_load guidelines;
    class gs_quotes core;
    class gs_write guidelines;
    class end_node core;
```

## official_guidelines_finder

Auto-discover the recognised international consensus paper for a disease. Triggers when a new disease is added; promotes its top-ranked PubMed result into the official-guideline pointer block once a reviewer confirms.

```mermaid
flowchart TD
    classDef guidelines fill:#e8f0fe,stroke:#4285f4,color:#1a3d6d;
    classDef doctors fill:#e6f4ea,stroke:#34a853,color:#1e4620;
    classDef pathways fill:#fef7e0,stroke:#f9ab00,color:#5c4400;
    classDef core fill:#f1f3f4,stroke:#9aa0a6,color:#3c4043;
    start["Start<br/><i>trigger</i>"]
    pubmed_esearch["PubMed esearch<br/><i>http_request</i>"]
    parse_pmids["Parse PMIDs<br/><i>code</i>"]
    pubmed_esummary["PubMed esummary<br/><i>http_request</i>"]
    format_candidates["Format candidate list<br/><i>code</i>"]
    rank_with_gemma["Rank with Gemma 4<br/><i>prompt</i>"]
    verify_candidate["Reject hallucinated PMIDs<br/><i>code</i>"]
    persist_pointer["Persist pointer<br/><i>code</i>"]
    end_node["End<br/><i>end</i>"]
    start --> pubmed_esearch
    pubmed_esearch --> parse_pmids
    parse_pmids --> pubmed_esummary
    pubmed_esummary --> format_candidates
    format_candidates --> rank_with_gemma
    rank_with_gemma --> verify_candidate
    verify_candidate --> persist_pointer
    persist_pointer --> end_node
    class start core;
    class pubmed_esearch core;
    class parse_pmids core;
    class pubmed_esummary core;
    class format_candidates core;
    class rank_with_gemma core;
    class verify_candidate core;
    class persist_pointer core;
    class end_node core;
```
