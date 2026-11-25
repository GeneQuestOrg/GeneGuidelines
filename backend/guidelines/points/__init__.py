"""Generated "What the guideline says about diagnosis – to show your doctor" blocks, for any disease with a guideline-grade source.

Each point is a verbatim quote from a guideline-grade document, a plain-language summary in English and Polish, and one open question for the doctor. A deterministic check requires every quote to be found word for word in its source; model checkers judge fairness, faithfulness, the question and the Polish. Quality comes from this generator-checker design and from a plain "AI-generated, nobody approved it" note, not from human review.

Modules: ``models`` (value objects, the typed run record, the shelf fingerprint), ``sources`` (grading and selection, pure), ``loader`` (reading a shelf), ``quote_check`` (verbatim check), ``block`` (the published shape), ``ports`` / ``llm`` (model calls), ``loop`` + ``prompts`` (the current generator-verifier loop), ``repository``, ``run_lock``, ``service`` (runs and stores), ``deps`` / ``api`` / ``cli`` (entry points). Import from the module you need; this package re-exports nothing, so importing it pulls in no service, model client or database.
"""
