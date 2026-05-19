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


def prepare_llm_message_text(text: str) -> str:
    """Ensure non-empty, null-byte-free message text for OpenAI-compatible APIs.

    Some vLLM gateways return HTTP 400 ``invalid message content type: <nil>`` when a
    message ``content`` field would be empty or null after JSON encoding.
    """
    cleaned = (text or "").replace("\x00", "")
    if not cleaned.strip():
        return "(no additional context provided.)"
    return cleaned


def build_simple_llm_prompts(
    node_prompt: str,
    *,
    system_head: str,
    ticket_id: int,
    title: str,
    description: str,
    comments_text: str = "",
) -> tuple[str, str]:
    """Return (system_prompt, user_prompt) for simple LLM nodes.

    Keeps the system message short and places the (often large) interpolated task in the
    user message — better compatibility with self-hosted vLLM and Gemma endpoints.
    """
    sys_prompt = prepare_llm_message_text(system_head)
    user_parts = [
        "--- Task ---",
        prepare_llm_message_text(node_prompt),
        "",
        "--- Run metadata ---",
        f"Ticket #{ticket_id}",
        f"Title: {prepare_llm_message_text(title)}",
        f"Description: {prepare_llm_message_text(description)}",
    ]
    if (comments_text or "").strip():
        user_parts.append(f"Discussion: {prepare_llm_message_text(comments_text)}")
    return sys_prompt, "\n".join(user_parts)


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
