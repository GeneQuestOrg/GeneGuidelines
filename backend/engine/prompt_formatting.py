from __future__ import annotations


def format_tools_list_for_prompt(catalog_rows: list[dict]) -> str:
    """Format tool_catalog rows as lines: name (auto|approval)."""
    lines = []
    for r in catalog_rows:
        name = (r.get("name") or "").strip()
        if not name:
            continue
        mode = (r.get("execution_mode") or "auto").strip().lower()
        lines.append(f"- {name} ({mode})")
    return "\n".join(lines) if lines else "(no tools available)"


def build_node_prompt(
    node_prompt_text: str,
    ticket_summary: str,
    tools_list: str,
    previous_output: str,
) -> str:
    """
    Replace placeholders in node prompt. Placeholders: {{ticket_summary}}, {{tools_list}}, {{previous_output}}.
    """
    if not node_prompt_text:
        return ""
    out = node_prompt_text
    out = out.replace("{{ticket_summary}}", ticket_summary or "")
    out = out.replace("{{tools_list}}", tools_list or "(brak listy)")
    out = out.replace("{{previous_output}}", previous_output or "(brak wyniku poprzedniego kroku)")
    return out
