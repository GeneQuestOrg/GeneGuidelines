/**
 * Product-level on/off switches for whole features.
 *
 * Not env-driven on purpose: these are decisions about what the product *is*,
 * not per-environment configuration, so they belong in a reviewed diff rather
 * than in a container app's settings where nobody sees them change.
 */

/**
 * "My case" — private upload of a discharge summary, de-identified server-side.
 *
 * OFF. It was built for the Gemma hackathon demo and, judging over, it is out of
 * scope for what this product is narrowing to: doctors, guidelines, what the AI
 * finds in PubMed, trials, foundations and therapies. It is also the one feature
 * whose privacy story does not hold up for real use — the de-identification call
 * leaves the EU (SiliconFlow), which no consent checkbox makes appropriate for a
 * parent's medical records.
 *
 * The code stays, tested and working, and the backend has the matching gate
 * (`MY_CASE_ENABLED` in backend/config.py). Turning both on restores the feature;
 * turn it on together with an EU-hosted redaction model, not before.
 */
export const MY_CASE_ENABLED = false;
