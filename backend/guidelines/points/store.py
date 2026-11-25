"""Reading and writing the stored guideline-points block (``guideline_points``), and the shelf fingerprint that decides when it is rebuilt."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from ..orm import GuidelinePointsRow

# Bump when the loop, its prompts or the block shape change enough that every stored block should be rebuilt on the next run.
LOOP_VERSION = "2026-11-24"


def _engine(engine: Engine | None) -> Engine:
    if engine is not None:
        return engine
    from ...shared.persistence.engine import get_engine

    return get_engine()


def shelf_hash(shelf: list[Any]) -> str:
    """Fingerprint of a shelf (``SourceDocument`` rows) and the loop version: what a block is built from."""
    rows = sorted((str(d.doc_id), str(d.pmid or ""), str(d.bookshelf or ""), str(d.pmcid or ""), str(d.title or "")) for d in shelf)
    return hashlib.sha256(json.dumps([LOOP_VERSION, rows]).encode("utf-8")).hexdigest()


def get_points(slug: str, engine: Engine | None = None) -> GuidelinePointsRow | None:
    with Session(_engine(engine)) as session:
        row = session.get(GuidelinePointsRow, slug)
        if row is not None:
            session.expunge(row)
        return row


def published_block(slug: str, engine: Engine | None = None) -> dict | None:
    """The block a page may show, or None: no row, a row that did not publish, or no table yet."""
    row = get_points(slug, engine)
    if row is None or not row.publish or not row.block:
        return None
    return dict(row.block)


def save_points(*, slug: str, publish: bool, reason: str, shelf_hash: str, block: dict | None, record: dict, models: str, cost_usd: float | None, engine: Engine | None = None) -> None:
    now = datetime.now(UTC).isoformat(timespec="seconds")
    payload: dict[str, Any] = {"publish": int(bool(publish)), "reason": reason, "shelf_hash": shelf_hash, "block": block, "record": record, "models": models, "cost_usd": "" if cost_usd is None else f"{cost_usd:.4f}", "generated_at": now}
    with Session(_engine(engine)) as session, session.begin():
        row = session.get(GuidelinePointsRow, slug)
        if row is None:
            session.add(GuidelinePointsRow(disease_slug=slug, **payload))
        else:
            for key, value in payload.items():
                setattr(row, key, value)
