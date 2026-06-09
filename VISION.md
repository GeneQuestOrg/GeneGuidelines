# Product vision — GeneGuidelines

> Where this is heading and why. This is the public, condensed version of the
> product vision; it is derived from the foundation's internal design canon and
> kept deliberately short. Built by the [GeneQuest Foundation](https://genequest.org)
> as part of a broader knowledge infrastructure for rare genetic diseases,
> starting with fibrous dysplasia / McCune-Albright syndrome (FD/MAS) — the
> architecture is general.

## North-star

**GeneGuidelines guides a family and patient through the stages of a rare
genetic disease — from recognition, through diagnosis and monitoring, to
treatment options.** The starting point is the official guidelines, from which
we extract *concrete, actionable* steps for each stage — not a wall of text
written for a specialist. Where guidelines exist, a clinician panel reviews
extensions the AI proposes from new and overlooked older papers. Where none
exist, we build the first baseline for an expert to review. And the picture of
the disease is widened by parents themselves — through anonymized case
descriptions and test results that never reached PubMed.

If any other document contradicts that paragraph, that paragraph wins.

## The problem: two failures, not one

Around a rare disease, two different things fail at once.

1. **Existing knowledge doesn't reach the point of care.** Sometimes the answer
   is already written in an official guideline — and still doesn't reach the
   doctor making the decision for a specific patient. (The founder's own case,
   below, is the sharpest proof: the FD guideline said plainly what *not* to do
   — and it was done anyway.)
2. **Knowledge grows faster than guidelines update.** A primary-care doctor —
   or even a hospital specialist — cannot keep up with the literature for every
   rare disease. It is not the doctors' fault; it is the scale of the
   literature (numbers, sources, and the median guideline lag are tracked in the
   foundation's canonical-facts registry). In rare disease it hurts most: too
   few papers per disease for standing review teams to form, yet too many and
   too scattered for one specialist to keep up — with enormous stakes per
   patient.

So the product has two jobs: **make existing knowledge usable at the point of
care**, and **keep it alive as it changes.**

## What we build — four pillars

1. **Guidelines translated into action, stage by stage.** From the official
   documents we extract how to run diagnosis, best-practice monitoring, and
   treatment options — in a form a parent and a non-specialist doctor can
   actually use (decision tree, red flags, questions to ask the doctor).
2. **Guidelines where none exist.** For ultra-rare entities with no consensus
   at all, we assemble an AI-drafted baseline for expert review — something that
   exists nowhere else.
3. **Cyclic refresh: extensions guidelines haven't captured yet.** The AI tracks
   new and overlooked older papers and surfaces them as a **"thing to
   consider"** — with rationale and citations, never as hard guidance. A
   clinician rates each one *useful / not useful* (with an optional note) — a
   lightweight signal that feeds a weighted ranking, not a sign-off on the
   official guideline. This serves three groups: parents and family doctors get a "worth discussing"
   signal; specialists and consortia get a ready, in-depth analysis to pull from
   — so the tool **accelerates the next official guideline.**
4. **Parent contribution — and the exchange it starts.** Parents describe their
   own cases and upload results; the data is **anonymized** and gives a picture
   broader than PubMed describes. It is a fair exchange: **the parent gets custom
   research for their case; the specialist gets access to anonymized clinical
   data found nowhere else.** The more families contribute, the fuller the
   picture for everyone.

## The safety core: a three-level epistemic taxonomy

Everything hinges on never letting a user confuse what is established with what
the AI proposes. Content is layered by epistemic status, and AI-generated
novelty is shifted by default from the patient surface to the expert surface:

- **(a) A guideline exists** (e.g. FD: Boyce 2019) — we render the consensus as
  the reference. Near-zero AI validation burden. The parent sees it with a
  "discuss with your doctor" frame.
- **(b) A guideline exists + newer or overlooked older papers** — "things to
  consider", expert-first. A lighter question for the clinician than co-signing
  a living document: *"here are 3 papers since Boyce — does any change the
  recommendation?"*
- **(c) No guideline at all** — the AI assembles a baseline for expert review.
  This is a must-have, not an option: for an ultra-rare entity even Orphanet has
  nothing, so this is where we are most unique and the moral weight is highest.
  Experts can **author** here, not only review.

Exposure of (b)/(c) to a parent is conditional and per-item — it may surface
(framed as "discuss with your doctor") only when several clinicians rate it
useful, or when it is low-risk and high-benefit — never as a raw, authoritative
verdict.

## The clinician loop: signal first, consortium-shaped over time

The AI proposes; the clinician decides; every recommendation is traceable to a
published source. That is the difference between a tool ("AI summarizes the
literature") and an institution (every claim traceable to a source, every
clinician signal attributable to a name).

We are deliberately incremental. **V1 is a light signal:** a reviewing clinician
marks a suggestion useful or not (with optional comment), which feeds a weighted
ranking for the next reviewer — it does **not** rewrite the official guideline.
The full versioned approve / request-changes / reject model, with signed, dated
decisions by verified reviewers and meta-PRs where experts disagree, is the
**target** the workflow is built toward — the shape a rare-disease consortium
actually uses. Refresh is **demand-driven, not calendar-promised**: a background
monitor can run as often as we like, but expert review goes where there is real
interest (a research request, a subscription, a foundation's ask).

## The parent's core value: unknown unknowns

The failure mode for a newly diagnosed parent is not "I couldn't find the
answer" — it is **"I didn't know there was anything to ask."** That you must
police the diagnostics yourself. That an expert in *this* entity exists. That
foundations, clinical trials, and official guidelines exist at all. These are
not things you can type into a search box. So the value is that the **taxonomy
of options is visible by default** — an editorial act ("you didn't ask, but you
must know X exists"), not a search one.

## Why it exists

The vision is not abstract — it grows from the founder's son's diagnostic
odyssey: a guideline that said what not to do, a biopsy that wasn't required, a
histopathology misread as a bone tumor without the genetic test that is standard
when in doubt, a major operation narrowly avoided, and the correct call made by
one experienced clinician — plus an international network that existed but had to
be found by hand. The point is not "knowledge was missing." It is that
**knowledge existed — in a guideline and in the heads of a few people in the
world — and still didn't reach where the decisions were made.** GeneGuidelines
exists so that path doesn't depend on luck. (More on the public site's About
page.)

## The byproduct: an audit corpus

Every decision a clinician makes over concrete evidence — and every
PMID-grounded justification the AI produces alongside it — becomes a structured
record of expert clinical reasoning, with provenance per claim and a named
reviewer per decision. We intend that corpus to help train and align future
medical models, openly and with contributors credited. It is a byproduct of the
mission, never the purpose.
