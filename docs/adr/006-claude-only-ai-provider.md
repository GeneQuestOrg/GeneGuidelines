# ADR 006 — Claude is the only AI provider, and the model per step is chosen by measurement

**Status:** accepted · 2026-11-21

## Context

On 2026-11-20 production called three providers. Most steps ran on Gemma 4 at SiliconFlow (`LLM_BASE_URL`), a provider whose legal entity and processing location we could not establish and which offers no data processing agreement with standard contractual clauses. The guideline synthesis (`direct:gpt-6-astra`) and the wider-search judge (`openai:gpt-5.4`) called OpenAI on an account with no credit: every synthesis run failed with 429, and the disease search silently fell back to Gemma alone, which gave 11 confident wrong answers on 90 FD queries (for example "OMIM 174800", McCune-Albright, became Tay-Sachs).

The privacy policy we are about to publish must list every recipient of what a user types. It cannot honestly list a provider we cannot describe, and three providers mean three transfers to explain.

The foundation decided to move every model to one new Anthropic account. Which Claude model runs which step was not assumed; it was measured on fibrous dysplasia in `scripts/labs/model_choice_fd/` (762 calls, 11.63 USD, 0 safety refusals, 0 truncated answers; report in the foundation's docs, `realizacja/eksperyment-modele-fd-2026-11.md`).

## Decision

`MODEL_PROFILE=anthropic` makes Claude the only AI provider. Every model call in the app goes to Claude, and any other model spec still stored in a flow row or an env var is replaced by the default Claude model at call time (`backend.agents.anthropic_direct.enforce_anthropic_only`), so a stale row cannot quietly send a user's text elsewhere. Leftover `LLM_*` variables no longer switch the app to the old endpoint under this profile.

Models per step, from the lab:

| Step | Model | Why |
| --- | --- | --- |
| Disease search, generator and judge | Sonnet 5.5, effort medium (profile default) | 87/90 hits and 0 confident wrong answers. Haiku as generator gave 1 wrong in 90 for ~1 cent less per query; a rare-disease search should not be wrong to save a cent. |
| Guideline synthesis sections (`gs-sec-*`) | Sonnet 5.5, effort high (named in `guideline_synthesis.json`) | Same scores as Opus on every automated measure at 47 % of the cost (1.16 vs 2.46 USD per disease). The measures were at ceiling, so a blind clinical review decides between Sonnet and Opus; switching is a one-line spec change. |
| PubMed `pass1-*` evidence appraisal | Opus 5.5, effort medium (named on the seeded rows, kept in sync by `_sync_pubmed_pass1_model`) | Sonnet picked nearly the same papers but kept 0.3 of 6 decision-changing claims; Opus kept 2.7. |
| Everything else (finders, `pm-4-*`, shelf classification, translation, doctor geo-resolution) | Sonnet 5.5, effort medium (profile default) | Not measured separately. Haiku is excluded from any step that states facts: it invented a disease ("Nunan syndrome (KDR)") from a typo and accepted a fictitious one. |

Claude is called through a direct adapter (`backend/agents/anthropic_direct.py`), not pydantic-ai, exactly as the lab called it: one streamed Messages call with the node's Pydantic schema as a JSON-schema response format, a pinned effort, the model's default adaptive thinking, and `max_tokens = max(node budget × 4, 16000)`. pydantic-ai 1.97.0 is pinned and sends structured output as a forced tool call, which Claude 5.5 models reject. Every call opts into Anthropic's server-side refusal fallback (`fallbacks: "default"`), which stays on Anthropic. A refusal that survives it is reported as a failed node and never retried.

The `pm-4-*` section prompts reference their pass1 node as `{{ context.pass1-<section> }}`. The resolver returned an empty string for any single-segment reference, so pm-4 never saw the appraisal it was meant to build on. A bare node id now renders that node's whole output as JSON.

## Consequences

- The privacy policy can name one AI provider. `ANTHROPIC_API_KEY` is the only model key production needs; `LLM_*` and `OPENAI_API_KEY` should be removed from the container apps once the profile is live.
- A full research run costs roughly 3–4 USD per disease (synthesis ~1.2, pass1 ~1.2, pm-4 ~0.7, the rest small).
- Simple-call concurrency defaults to 3 under this profile: a pass1 call can carry a ~200k-token corpus, and a new account's input-tokens-per-minute limit is the first thing to hit.
- The agentic MCP runner has no Claude path and raises a clear error. No production flow uses it (`pm-1` retrieval is deterministic, `PUBMED_PM1_DETERMINISTIC_RETRIEVAL=1`).
- "My case" (switched off) has no Claude path and stays off: the policy does not cover uploaded medical documents.
- The pm-4 model was not measurable before the placeholder fix; it runs on the default Sonnet until a lab run with the fix says otherwise.
