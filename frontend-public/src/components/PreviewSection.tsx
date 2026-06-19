import type { ReactNode } from "react";
import { Button, Section } from "@gene-guidelines/ui";

export interface PreviewSectionProps {
  title: string;
  sub?: string;
  divider?: boolean;
  totalCount: number;
  previewMax: number;
  seeAllPath: string;
  seeAllLabel?: string;
  onNav: (path: string) => void;
  children: ReactNode;
}

/**
 * Wraps a Section with a "View all" button when totalCount exceeds previewMax.
 * Use this to show a preview of a longer list with navigation to a dedicated page.
 */
export function PreviewSection({
  title,
  sub,
  divider,
  totalCount,
  previewMax,
  seeAllPath,
  seeAllLabel,
  onNav,
  children,
}: PreviewSectionProps) {
  const hasMore = totalCount > previewMax;
  const label = seeAllLabel ?? `View all ${totalCount} →`;

  return (
    <Section title={title} sub={sub} divider={divider}>
      {children}
      {hasMore ? (
        <div className="page__actions">
          <Button type="button" variant="ghost" onClick={() => onNav(seeAllPath)}>
            {label}
          </Button>
        </div>
      ) : null}
    </Section>
  );
}
