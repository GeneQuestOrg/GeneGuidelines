"""Generated "What the guideline says about diagnosis – to show your doctor" blocks, for any disease with a guideline-grade source.

A generator (Claude Sonnet) drafts 3–6 points from the full text of a disease's strongest shelf documents; each point is a verbatim quote, an EN/PL summary and one open question for the doctor. A deterministic check requires every quote to be found word for word in its source, and a separate verifier (Claude Opus) judges fairness, faithfulness, the question and the Polish. Rejected points get at most two revision rounds; a disease gets the block only with at least three accepted points. Quality comes from this loop and from a plain "AI-generated, nobody approved it" note, not from human review.

Phase 1 (this package and ``scripts/labs/guideline_points/``) builds and measures the block; storing and serving it is phase 2.
"""

from .block import published_block
from .loop import build_points_block, revision_rounds_used
from .models import DraftPoint, Paragraph, PointsDraft, SourceDoc, VerifierOutput
from .quote_check import DocIndex, check_point, normalize
from .sources import block_basis, grade_document, select_documents

__all__ = [
    "DocIndex",
    "DraftPoint",
    "Paragraph",
    "PointsDraft",
    "SourceDoc",
    "VerifierOutput",
    "block_basis",
    "build_points_block",
    "check_point",
    "grade_document",
    "normalize",
    "published_block",
    "revision_rounds_used",
    "select_documents",
]
