import type { ReactNode } from "react";
import "./section.css";

export interface SectionProps {
  title: ReactNode;
  count?: number;
  sub?: ReactNode;
  action?: ReactNode;
  divider?: boolean;
  children?: ReactNode;
}

export function Section({ title, count, sub, action, divider = false, children }: SectionProps) {
  return (
    <section className={`section${divider ? " section--divider" : ""}`}>
      <div className="section__head">
        <div className="section__titleblock">
          <h2 className="section__title">
            {title}
            {count != null && <span className="section__count">{count}</span>}
          </h2>
          {sub != null && <p className="section__sub">{sub}</p>}
        </div>
        {action != null && <div className="section__action">{action}</div>}
      </div>
      <div className="section__body">{children}</div>
    </section>
  );
}
