"""Guidelines layer (D6) — the read side of draft10's "signal, not publication" model.

One disease has a curated **shelf** of real source documents, ONE AI **synthesis**
over them (rendered at two depths by the frontend), **suggestions** hanging
alongside as deltas, and an asymmetric per-section **signal**. This module is the
persistence + read-API plumbing that lets ``VITE_DATA_SOURCE=api`` serve exactly
what the frontend fixtures serve (GL-1/2/3).

Clean ORM domain (golden pattern: ``backend/doctor_contributions/``). The
generation workflow (synthesis-over-shelf, critic loop, monitor) is a separate
concern and is intentionally NOT here — accuracy-critical, human-driven
(wizja 04). The rating/signal write-path lands in D5 (W4).
"""
