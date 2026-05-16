export interface PlaceholderSectionProps {
  title: string;
  description: string;
  migrationNote?: string;
}

export function PlaceholderSection({
  title,
  description,
  migrationNote,
}: PlaceholderSectionProps) {
  return (
    <section className="admin-section">
      <h1 className="admin-section__title">{title}</h1>
      <p className="admin-section__lead">{description}</p>
      {migrationNote != null ? (
        <p className="admin-section__note">{migrationNote}</p>
      ) : null}
    </section>
  );
}
