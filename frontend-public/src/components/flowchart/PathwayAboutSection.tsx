import type { PathwayAbout } from "../../types/parentPathway";

export interface PathwayAboutSectionProps {
  about: PathwayAbout;
}

export function PathwayAboutSection({ about }: PathwayAboutSectionProps) {
  const paragraphs = about.summary
    .split(/\n\n+/)
    .map((p) => p.trim())
    .filter(Boolean);

  return (
    <section className="flow__about" aria-labelledby="flow-about-title">
      <h2 id="flow-about-title" className="flow__about-title">
        {about.title}
      </h2>
      <div className="flow__about-body">
        {paragraphs.map((p, i) => (
          <p key={i} className="flow__about-summary">
            {p}
          </p>
        ))}
      </div>
    </section>
  );
}
