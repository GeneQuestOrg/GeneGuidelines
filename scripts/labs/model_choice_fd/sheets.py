"""Blind review sheets for the humans who hold the gold standard. The sheet never says which model wrote what; the key goes to a separate folder.

- Synthesis (for Dorota): every section in every compared version, under random letters that change per section, with a rating table; plus a sample of paragraphs next to the passage of the source they cite.
- PubMed (for Darek or Dorota): 30 sentences from the drafted section that cite a PMID, each next to that paper's abstract.
"""

from __future__ import annotations

import csv
import random
import string
from pathlib import Path

from . import task_pubmed, task_synthesis
from .common import read_jsonl, write_json
from .runs import load_run
from .snapshot import load_snapshot

_SYNTH_INTRO = """# Ocena streszczenia wytycznych FD — arkusz ślepy

Dorota, poniżej każda z pięciu sekcji streszczenia jest w kilku wersjach napisanych przez różne modele (albo zapisanych na produkcji). Litery są losowe i w każdej sekcji inne, więc nie da się z nich odczytać, kto co napisał. Klucz trzyma Darek w osobnym pliku.

Proszę o ocenę każdej wersji w pliku `ratings.csv` (skala 1–5, 5 = najlepiej):

- **poprawność** — czy wszystko, co napisano, jest zgodne z wiedzą i ze źródłem; każdy błąd merytoryczny proszę opisać w kolumnie `bledy`;
- **kompletność** — czy jest to, co rodzic lub lekarz pierwszego kontaktu powinien z tej sekcji wynieść (proszę wpisać, czego brakuje);
- **użyteczność dla rodzica** — czy po przeczytaniu wiadomo, co dalej zrobić, a czego nie robić.

Drugi plik, `citations.md`, to losowe akapity obok fragmentu źródła, na które się powołują. Przy każdym proszę wpisać w `citations.csv`, czy fragment popiera akapit: `tak`, `czesciowo`, `nie` albo `nie_da_sie_ocenic`.

Teksty są po angielsku, bo tak je pisze produkt. Oznaczenie `[źródło: …]` po akapicie to dokument i rozdział, na które model się powołał.
"""

_PUBMED_INTRO = """# Sprawdzenie cytowań w szkicu z PubMed — arkusz ślepy

Każdy wiersz to jedno zdanie z wygenerowanej sekcji „Diagnostics”, które powołuje się na pracę (PMID), oraz abstrakt tej pracy. Nie wiadomo, który model napisał które zdanie; klucz jest w osobnym pliku.

Proszę wpisać w `citations.csv`, czy abstrakt popiera zdanie: `tak`, `czesciowo`, `nie` albo `nie_da_sie_ocenic` (np. gdy sam abstrakt nie wystarcza).
"""


def _letters(n: int, rng: random.Random) -> list[str]:
    letters = list(string.ascii_uppercase[:n])
    rng.shuffle(letters)
    return letters


def synthesis_sheet(outs: list[Path], dest: Path, *, repeat: int, citations_per_version: int, seed: int) -> Path:
    rng = random.Random(seed)
    versions = []
    for out in outs:
        run, trials = load_run(out)
        snapshot = load_snapshot(run["snapshot"], "synthesis")
        chosen = [t for t in trials if t["repeat"] == repeat]
        versions.append({"run": run["run"], "arm": run["arm"], "sections": task_synthesis.assemble(snapshot, chosen), "trials": chosen, "snapshot": snapshot})
    labels = {str(d["docId"]): f"{d['role']}: {d['title'][:90]}" for d in versions[0]["snapshot"]["shelf_docs"]}
    dest.mkdir(parents=True, exist_ok=True)
    key: dict = {"sections": {}, "citations": {}, "repeat": repeat, "seed": seed}
    lines = [_SYNTH_INTRO]
    ratings = []
    for idx, spec in enumerate(versions[0]["sections"]):
        letters = _letters(len(versions), rng)
        order = list(range(len(versions)))
        rng.shuffle(order)
        lines.append(f"\n---\n\n## Sekcja {spec.get('title') or spec['id']}\n")
        for pos, vi in enumerate(order):
            letter = letters[pos]
            section = versions[vi]["sections"][idx]
            key["sections"][f"{spec['id']}/{letter}"] = {"run": versions[vi]["run"], "arm": versions[vi]["arm"]}
            lines.append(f"\n### Wersja {letter}\n")
            if section.get("noSource") or not section.get("paragraphs"):
                lines.append("_(ta wersja nie ma tu żadnego akapitu)_\n")
            if section.get("intro"):
                lines.append(f"_{section['intro']}_\n")
            for p in section.get("paragraphs") or []:
                src = p.get("source") or {}
                lines.append(f"{p.get('text')}\n\n> [źródło: {labels.get(str(src.get('doc')), src.get('doc'))}{' · ' + src['loc'] if src.get('loc') else ''}]\n")
            ratings.append({"sekcja": spec["id"], "wersja": letter, "poprawnosc_1_5": "", "kompletnosc_1_5": "", "uzytecznosc_dla_rodzica_1_5": "", "bledy": "", "czego_brakuje": "", "uwagi": ""})
    (dest / "sheet.md").write_text("\n".join(lines), encoding="utf-8")
    _write_csv(dest / "ratings.csv", sorted(ratings, key=lambda r: (r["sekcja"], r["wersja"])))
    pool = []
    for v in versions:
        for item in task_synthesis.sample_paragraphs(v["snapshot"], v["trials"], citations_per_version, seed):
            pool.append((v, item))
    rng.shuffle(pool)
    cit_lines, cit_rows = [_SYNTH_INTRO.split("\n")[0].replace("arkusz ślepy", "cytowania") + "\n"], []
    for n, (v, item) in enumerate(pool, 1):
        cid = f"c{n:02d}"
        key["citations"][cid] = {"run": v["run"], "arm": v["arm"], "section": item["section"]}
        cit_lines.append(f"\n---\n\n## {cid} (sekcja {item['section']})\n\n**Akapit:** {item['text']}\n\n**Powołuje się na:** {labels.get(str(item['doc']), item['doc'])} · {item.get('loc') or '(bez rozdziału)'}; PMID: {', '.join(item['citations']) or '–'}\n\n**Fragment źródła:**\n\n```\n{item['excerpt'].strip()}\n```\n")
        cit_rows.append({"id": cid, "popiera": "", "uwagi": ""})
    (dest / "citations.md").write_text("\n".join(cit_lines), encoding="utf-8")
    _write_csv(dest / "citations.csv", cit_rows)
    write_json(dest.parent / f"{dest.name}-KEY" / "key.json", key)
    return dest


def pubmed_sheet(outs: list[Path], dest: Path, *, n: int, seed: int) -> Path:
    rng = random.Random(seed)
    per_run = max(1, -(-n // max(1, len(outs))))
    pool = []
    for out in outs:
        run, trials = load_run(out)
        snapshot = load_snapshot(run["snapshot"], "pubmed")
        for item in task_pubmed.sample_citations(snapshot, trials, per_run, seed):
            pool.append((run, item))
    rng.shuffle(pool)
    pool = pool[:n]
    dest.mkdir(parents=True, exist_ok=True)
    key, lines, rows = {"citations": {}, "seed": seed}, [_PUBMED_INTRO], []
    for i, (run, item) in enumerate(pool, 1):
        cid = f"p{i:02d}"
        key["citations"][cid] = {"run": run["run"], "arm": run["arm"]}
        lines.append(f"\n---\n\n## {cid}\n\n**Zdanie:** {item['sentence']}\n\n**PMID {item['pmid']}:** {item['title']}\n\n**Abstrakt:**\n\n```\n{item['abstract'] or '(brak abstraktu w danych)'}\n```\n")
        rows.append({"id": cid, "pmid": item["pmid"], "popiera": "", "uwagi": ""})
    (dest / "sheet.md").write_text("\n".join(lines), encoding="utf-8")
    _write_csv(dest / "citations.csv", rows)
    write_json(dest.parent / f"{dest.name}-KEY" / "key.json", key)
    return dest


def _write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


_SELECTION_INTRO = """# Wybór prac przez krok oceny dowodów (PubMed, diagnostyka FD) — arkusz ślepy

Model dostał 80 abstraktów o FD i miał wskazać prace kluczowe dla **diagnostyki** (jak rozpoznać FD, badania obrazowe, biopsja, genetyka, różnicowanie). Poniżej losowe prace z tych, które wskazał którykolwiek z porównywanych modeli. Nie widać, który model co wybrał, ani ile razy; klucz jest w osobnym pliku.

Przy każdej pracy proszę wpisać w `selection.csv`, czy jest przydatna jako źródło do sekcji o diagnostyce FD: `tak`, `czesciowo` albo `nie`.
"""


def pubmed_selection_sheet(outs: list[Path], dest: Path, *, n: int, seed: int) -> Path:
    """A random sample of the papers any compared evidence pass selected, for a relevance label; precision per arm follows from the key."""
    rng = random.Random(seed)
    selected: dict[str, dict[str, int]] = {}
    snapshot = None
    for out in outs:
        run, _ = load_run(out)
        snapshot = snapshot or load_snapshot(run["snapshot"], "pubmed")
        for row in read_jsonl(out / "scores.jsonl"):
            if row["unit"].startswith("pass1") and row["ok"]:
                for pmid in row["cited"]:
                    selected.setdefault(pmid, {})
                    selected[pmid][run["arm"]] = selected[pmid].get(run["arm"], 0) + 1
    papers = {a["pmid"]: a for a in (snapshot or {}).get("corpus", [])}
    pool = sorted(selected)
    rng.shuffle(pool)
    pool = pool[:n]
    dest.mkdir(parents=True, exist_ok=True)
    lines, rows, key = [_SELECTION_INTRO], [], {"papers": {}, "seed": seed, "runs": [str(o.name) for o in outs], "selected_by_arm_and_count": {}}
    for i, pmid in enumerate(pool, 1):
        pid = f"s{i:02d}"
        paper = papers.get(pmid) or {}
        key["papers"][pid] = pmid
        key["selected_by_arm_and_count"][pmid] = selected[pmid]
        lines.append(f"\n---\n\n## {pid} — PMID {pmid}\n\n**{paper.get('title') or '(tytuł nieznany)'}**\n\n```\n{(paper.get('abstract') or '(brak abstraktu w danych)')[:2500]}\n```\n")
        rows.append({"id": pid, "pmid": pmid, "przydatna_do_diagnostyki": "", "uwagi": ""})
    (dest / "sheet.md").write_text("\n".join(lines), encoding="utf-8")
    _write_csv(dest / "selection.csv", rows)
    write_json(dest.parent / f"{dest.name}-KEY" / "key.json", key)
    return dest


def score_selection_labels(dest: Path) -> dict:
    """Per-arm precision of the evidence pass once a human has filled selection.csv (tak = 1, czesciowo = 0.5, nie = 0)."""
    from .common import read_json

    key = read_json(dest.parent / f"{dest.name}-KEY" / "key.json")
    weights = {"tak": 1.0, "czesciowo": 0.5, "nie": 0.0}
    with (dest / "selection.csv").open(encoding="utf-8") as handle:
        labels = {row["id"]: weights.get((row.get("przydatna_do_diagnostyki") or "").strip().lower()) for row in csv.DictReader(handle)}
    per_arm: dict[str, list[float]] = {}
    for pid, pmid in key["papers"].items():
        if labels.get(pid) is None:
            continue
        for arm in key["selected_by_arm_and_count"][pmid]:
            per_arm.setdefault(arm, []).append(labels[pid])
    return {"labelled": sum(1 for v in labels.values() if v is not None), "precision_by_arm": {arm: {"papers": len(v), "precision": sum(v) / len(v)} for arm, v in per_arm.items()}}
