/**
 * Short note on specialist profiles: scores come from publication metadata, not clinical vetting.
 */
export function SpecialistDisclaimer() {
  return (
    <aside
      className="dprofile__disclaimer"
      role="note"
      aria-label="Directory disclaimer"
    >
      <strong>Automated directory</strong>
      <p>
        PubMed scores and roles are derived from publication metadata. This listing is not medical
        advice, an endorsement, or a guarantee that the clinician treats your condition.
      </p>
    </aside>
  );
}
