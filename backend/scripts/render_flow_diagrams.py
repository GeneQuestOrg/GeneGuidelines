"""Render the flow specs as Mermaid diagrams into docs/FLOWS.md.

Hand-drawn architecture documentation goes stale the week after it is written, and
a stale diagram is worse than none: it teaches the wrong model of the system to
whoever reads it next. These flows are already *data* — `backend/flows/specs/*.json`
is what the engine executes — so the picture can be generated from the same source
of truth and regenerated whenever it drifts.

    python3 -m backend.scripts.render_flow_diagrams          # write docs/FLOWS.md
    python3 -m backend.scripts.render_flow_diagrams --check  # fail if out of date

The --check mode is what keeps it honest in CI: change a flow, forget the diagram,
the build tells you.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys

_ROOT = pathlib.Path(__file__).resolve().parents[2]
_SPECS = _ROOT / "backend" / "flows" / "specs"
_OUT = _ROOT / "docs" / "FLOWS.md"

# Which domain a node type belongs to, for colouring. Mirrors the executor packages;
# the boundary test keeps those honest, this only has to render them.
_DOMAIN_BY_PREFIX = {
    "guideline": "guidelines",
    "guidelines": "guidelines",
    "pubmed": "guidelines",
    "pmid": "guidelines",
    "doctor_finder": "doctors",
    "parent_pathway": "pathways",
}

_CLASS_DEFS = """    classDef guidelines fill:#e8f0fe,stroke:#4285f4,color:#1a3d6d;
    classDef doctors fill:#e6f4ea,stroke:#34a853,color:#1e4620;
    classDef pathways fill:#fef7e0,stroke:#f9ab00,color:#5c4400;
    classDef core fill:#f1f3f4,stroke:#9aa0a6,color:#3c4043;"""


def _domain_of(node_type: str) -> str:
    for prefix, domain in _DOMAIN_BY_PREFIX.items():
        if node_type.startswith(prefix):
            return domain
    return "core"


# Mermaid keywords that cannot be used as a node id. `end` is the one that bites:
# nearly every flow has a node called exactly that, and Mermaid silently fails to
# render the whole diagram rather than complaining about the one line.
_MERMAID_RESERVED = {"end", "graph", "subgraph", "class", "click", "style", "linkStyle", "default"}


def _safe(node_id: str) -> str:
    """A Mermaid-safe id: no hyphens or dots, and never a reserved word."""
    ident = node_id.replace("-", "_").replace(".", "_")
    return f"{ident}_node" if ident.lower() in _MERMAID_RESERVED else ident


def _label(node: dict) -> str:
    label = str(node.get("label") or node.get("node_id") or "").strip()
    node_type = str(node.get("node_type") or "").strip()
    label = label.replace('"', "'")
    return f"{label}<br/><i>{node_type}</i>" if node_type else label


def render_flow(spec: dict) -> str:
    nodes = spec.get("nodes") or []
    edges = spec.get("edges") or []
    lines = ["```mermaid", "flowchart TD", _CLASS_DEFS]

    for node in nodes:
        nid = _safe(str(node.get("node_id")))
        lines.append(f'    {nid}["{_label(node)}"]')
    for edge in edges:
        src = _safe(str(edge.get("source_node_id") or ""))
        dst = _safe(str(edge.get("target_node_id") or ""))
        if not src or not dst:
            continue
        cond = str(edge.get("condition") or "").strip()
        lines.append(f"    {src} -->|{cond}| {dst}" if cond else f"    {src} --> {dst}")
    for node in nodes:
        lines.append(
            f'    class {_safe(str(node.get("node_id")))} {_domain_of(str(node.get("node_type") or ""))};'
        )
    lines.append("```")
    return "\n".join(lines)


def render_all() -> str:
    out = [
        "# Flows",
        "",
        "> Generated from `backend/flows/specs/*.json` by",
        "> `python3 -m backend.scripts.render_flow_diagrams`. Do not edit by hand — the",
        "> specs are what the engine actually executes, so they are the source of truth",
        "> and this file is only a view of them. `--check` fails when the two drift.",
        "",
        "Colours follow the executor domain packages: "
        "**guidelines** (blue), **doctors** (green), **pathways** (amber), shared core (grey).",
        "",
    ]
    for path in sorted(_SPECS.glob("*.json")):
        spec = json.loads(path.read_text())
        out.append(f"## {spec.get('flow_key') or path.stem}")
        desc = str(spec.get("description") or "").strip()
        if desc:
            out.append("")
            out.append(desc)
        out.append("")
        out.append(render_flow(spec))
        out.append("")
    return "\n".join(out).rstrip() + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="fail if docs/FLOWS.md is stale")
    args = ap.parse_args()

    rendered = render_all()
    if args.check:
        current = _OUT.read_text() if _OUT.exists() else ""
        if current != rendered:
            print(
                "docs/FLOWS.md is out of date — run "
                "`python3 -m backend.scripts.render_flow_diagrams`",
                file=sys.stderr,
            )
            return 1
        print("docs/FLOWS.md is current")
        return 0

    _OUT.parent.mkdir(parents=True, exist_ok=True)
    _OUT.write_text(rendered)
    print(f"wrote {_OUT.relative_to(_ROOT)} ({len(rendered)} chars)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
