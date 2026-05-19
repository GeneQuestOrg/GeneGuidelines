"""Per-disease guideline prompt profiles for the pubmed flow."""
from __future__ import annotations

from typing import Any

PROFILE_CLINICAL_FRAMING = "clinicalFraming"
PROFILE_PUBMED_RETRIEVAL = "pubmedRetrieval"
PROFILE_SYNTHESIS_EMPHASIS = "synthesisEmphasis"
PROFILE_HOMONYMS_TO_AVOID = "homonymsToAvoid"
PROFILE_PREFERRED_TERMS = "preferredTerms"

FLOW_PROMPT_DISEASE_BLOCK = """
--- Disease-specific instructions (mandatory; follow exactly) ---
Catalog slug: {{ context.initial.disease_slug }}
{{ context.initial.guideline_prompt_block }}
""".strip()


def empty_guideline_prompt_profile() -> dict[str, Any]:
    """Default empty profile (camelCase keys — matches JSON API)."""
    return {
        PROFILE_CLINICAL_FRAMING: "",
        PROFILE_PUBMED_RETRIEVAL: "",
        PROFILE_SYNTHESIS_EMPHASIS: "",
        PROFILE_HOMONYMS_TO_AVOID: [],
        PROFILE_PREFERRED_TERMS: [],
    }


def normalize_guideline_prompt_profile(raw: Any) -> dict[str, Any]:
    """Parse and validate profile dict from JSON."""
    base = empty_guideline_prompt_profile()
    if not isinstance(raw, dict):
        return base
    for key in (PROFILE_CLINICAL_FRAMING, PROFILE_PUBMED_RETRIEVAL, PROFILE_SYNTHESIS_EMPHASIS):
        val = raw.get(key)
        if isinstance(val, str):
            base[key] = val.strip()
    for key in (PROFILE_HOMONYMS_TO_AVOID, PROFILE_PREFERRED_TERMS):
        val = raw.get(key)
        if isinstance(val, list):
            base[key] = [str(x).strip() for x in val if str(x).strip()]
    return base


def format_guideline_prompt_block(profile: dict[str, Any], disease: dict[str, Any]) -> str:
    """Human-readable block injected into flow prompts via context.initial.guideline_prompt_block."""
    parts: list[str] = []

    framing = str(profile.get(PROFILE_CLINICAL_FRAMING) or "").strip()
    if framing:
        parts.append(f"Clinical framing:\n{framing}")

    retrieval = str(profile.get(PROFILE_PUBMED_RETRIEVAL) or "").strip()
    if retrieval:
        parts.append(f"PubMed retrieval:\n{retrieval}")

    synthesis = str(profile.get(PROFILE_SYNTHESIS_EMPHASIS) or "").strip()
    if synthesis:
        parts.append(f"Synthesis emphasis:\n{synthesis}")

    homonyms = profile.get(PROFILE_HOMONYMS_TO_AVOID) or []
    if homonyms:
        parts.append("Homonyms / unrelated entities to exclude:\n- " + "\n- ".join(homonyms))

    preferred = profile.get(PROFILE_PREFERRED_TERMS) or []
    if preferred:
        parts.append("Preferred search terms:\n- " + "\n- ".join(preferred))

    if not parts:
        summary = str(disease.get("summary") or "").strip()
        gene = str(disease.get("gene") or "").strip()
        types = disease.get("types") or []
        types_s = ", ".join(types) if types else "n/a"
        parts.append(
            "Clinical framing (from catalog only — add a custom profile for richer guidance):\n"
            f"{summary}\n\nGene: {gene or 'n/a'}\nSubtypes: {types_s}"
        )

    return "\n\n".join(parts)


def append_disease_prompt_block(prompt: str) -> str:
    """Append standard placeholder block if not already present."""
    if "context.initial.guideline_prompt_block" in prompt:
        return prompt
    return prompt.rstrip() + "\n\n" + FLOW_PROMPT_DISEASE_BLOCK


def build_disease_flow_initial_fields(disease: dict[str, Any] | None) -> dict[str, str]:
    """Fields merged into flow store initial_context for pubmed runs."""
    if not disease:
        return {
            "disease_slug": "",
            "disease_name": "",
            "guideline_prompt_block": "",
        }
    profile = normalize_guideline_prompt_profile(disease.get("guidelinePromptProfile"))
    return {
        "disease_slug": str(disease.get("slug") or ""),
        "disease_name": str(disease.get("name") or ""),
        "guideline_prompt_block": format_guideline_prompt_block(profile, disease),
    }


def build_custom_disease_flow_initial_fields(
    disease_name: str,
    aliases: list[str],
) -> dict[str, str]:
    """Fields for pubmed runs when the disease is not in the catalog."""
    alias_s = ", ".join(aliases) if aliases else "n/a"
    block = (
        "Custom rare-disease research (not in the published catalog).\n"
        f"Preferred name: {disease_name}\n"
        f"Search aliases / synonyms: {alias_s}\n"
        "PubMed queries must target this exact clinical entity — avoid unrelated homonyms."
    )
    return {
        "disease_slug": "",
        "disease_name": disease_name,
        "disease_aliases": alias_s,
        "guideline_prompt_block": block,
    }
