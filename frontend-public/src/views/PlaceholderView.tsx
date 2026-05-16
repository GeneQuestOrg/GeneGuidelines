import { Button } from "@gene-guidelines/ui";

export interface PlaceholderViewProps {
  title: string;
  description: string;
  primaryAction?: { label: string; path: string };
  onNav: (path: string) => void;
}

export function PlaceholderView({
  title,
  description,
  primaryAction,
  onNav,
}: PlaceholderViewProps) {
  return (
    <section className="page page--narrow">
      <h1 className="page__title">{title}</h1>
      <p className="page__lead">{description}</p>
      {primaryAction != null ? (
        <p className="page__actions">
          <Button variant="primary" onClick={() => onNav(primaryAction.path)}>
            {primaryAction.label}
          </Button>
        </p>
      ) : null}
    </section>
  );
}
