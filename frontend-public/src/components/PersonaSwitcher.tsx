import type { AudienceView } from "../router/types";
import { getAudienceCopy } from "../copy";
import "./persona.css";

export interface PersonaSwitcherProps {
  view: AudienceView;
  onChange: (view: AudienceView) => void;
}

function PersonaOption({
  active,
  title,
  sub,
  onSelect,
}: {
  active: boolean;
  title: string;
  sub: string;
  onSelect: () => void;
}) {
  return (
    <button
      type="button"
      role="radio"
      aria-checked={active}
      className={`persona__choice${active ? " is-active" : ""}`}
      onClick={onSelect}
    >
      <span className="persona__body">
        <span className="persona__name">{title}</span>
        <span className="persona__sub">{sub}</span>
      </span>
      <span className="persona__check" aria-hidden>
        ✓
      </span>
    </button>
  );
}

export function PersonaSwitcher({ view, onChange }: PersonaSwitcherProps) {
  const parent = getAudienceCopy("parent").disease;
  const doctor = getAudienceCopy("doctor").disease;

  return (
    <div className="persona" role="radiogroup" aria-label={parent.personaLabel}>
      <span className="persona__label">{parent.personaLabel}</span>
      <div className="persona__choices">
        <PersonaOption
          active={view === "parent"}
          title={parent.parentPersonaTitle}
          sub={parent.parentPersonaSub}
          onSelect={() => onChange("parent")}
        />
        <PersonaOption
          active={view === "doctor"}
          title={doctor.doctorPersonaTitle}
          sub={doctor.doctorPersonaSub}
          onSelect={() => onChange("doctor")}
        />
      </div>
    </div>
  );
}
