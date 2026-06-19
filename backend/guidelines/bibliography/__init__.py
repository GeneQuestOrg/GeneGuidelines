"""Analyzed-bibliography component (researcher-facing) within the guidelines context.

A distinct **component** inside the guidelines bounded context — same context
(it is the knowledge engine's by-product), different *actor*: the researcher /
audit reader, not the clinical-read site that ``guidelines.api`` serves. Kept in
its own package so that boundary is visible (CCP: the audit concern is closed
together; CRP: the clinical-read consumers don't depend on it).

What it is: the **analyzed corpus** of an engine run — every paper the shelf-build
and monitor steps *considered*, with the engine's verdict (on-shelf / became a
suggestion / rejected / low) and the one-line reason. The negative paths (why a
paper did *not* become a source or a delta) are the value: they make the engine
auditable and double as a triage-quality dashboard.

This is an audit record of a run — a point-in-time snapshot of "what the engine
read and decided", distinct from the *live* curated shelf / suggestions (current
clinical state). Not recommendations, not a guideline.
"""
