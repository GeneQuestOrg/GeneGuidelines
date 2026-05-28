import { useCallback, useEffect, useState } from "react";
import { SignedIn } from "@clerk/clerk-react";
import { Badge, Button, Status } from "@gene-guidelines/ui";
import type { Disease, GuidelineMeta } from "../types";
import type { DiseaseCopy } from "../copy";
import { isClerkEnabled } from "../auth/clerkConfig";
import { fetchWatches, watchDisease, unwatchDisease } from "../api/account";
import "../styles/disease-page.css";

export interface DiseaseHeroProps {
  disease: Disease;
  guideline: GuidelineMeta | null;
  copy: DiseaseCopy;
  isClinician: boolean;
  onNav: (path: string) => void;
}

function WatchDiseaseButton({ slug }: { slug: string }) {
  const [isWatched, setIsWatched] = useState<boolean | null>(null);
  const [isPending, setIsPending] = useState(false);

  useEffect(() => {
    fetchWatches()
      .then((watches) => {
        setIsWatched(watches.some((w) => w.disease_slug === slug));
      })
      .catch(() => {
        setIsWatched(false);
      });
  }, [slug]);

  const toggle = useCallback(async () => {
    if (isPending || isWatched === null) return;
    const wasWatched = isWatched;
    setIsWatched(!wasWatched);
    setIsPending(true);
    try {
      if (wasWatched) {
        await unwatchDisease(slug);
      } else {
        await watchDisease(slug);
      }
    } catch {
      setIsWatched(wasWatched);
    } finally {
      setIsPending(false);
    }
  }, [slug, isWatched, isPending]);

  if (isWatched === null) return null;

  return (
    <Button
      type="button"
      variant="ghost"
      onClick={() => void toggle()}
      disabled={isPending}
      aria-pressed={isWatched}
    >
      {isWatched ? "★ Watched" : "☆ Watch"}
    </Button>
  );
}

export function DiseaseHero({
  disease,
  guideline,
  copy,
  isClinician,
  onNav,
}: DiseaseHeroProps) {
  const slug = disease.slug;

  return (
    <div className={`d-hero d-hero--${disease.accent}`}>
      <div className="d-hero__top">
        <div className="d-hero__abbr">{disease.nameShort}</div>
        <div className="d-hero__title-block">
          <h1 className="d-hero__name">{disease.name}</h1>
        </div>
        <Status
          status={disease.status}
          by={disease.statusBy ?? undefined}
          date={disease.statusDate ?? undefined}
        />
        {guideline != null ? <Badge>Guideline {guideline.version}</Badge> : null}
      </div>
      <p className="d-hero__summary">{disease.summary}</p>
      <dl className="d-hero__facts">
        <div>
          <dt>Gene</dt>
          <dd>
            <code>{disease.gene}</code>
          </dd>
        </div>
        <div>
          <dt>OMIM</dt>
          <dd>
            <code>{disease.omim}</code>
          </dd>
        </div>
        <div>
          <dt>Inheritance</dt>
          <dd>{disease.inheritance}</dd>
        </div>
        <div>
          <dt>Prevalence</dt>
          <dd>{disease.prevalenceText}</dd>
        </div>
        <div>
          <dt>Types</dt>
          <dd>{disease.types.join(" · ")}</dd>
        </div>
        <div>
          <dt>Coverage</dt>
          <dd>{disease.coverage}</dd>
        </div>
        {disease.aiDraftDate != null ? (
          <div>
            <dt>Last AI draft</dt>
            <dd>
              {disease.aiDraftDate}
              {disease.openPRs > 0 ? ` · ${disease.openPRs} open PRs` : ""}
            </dd>
          </div>
        ) : null}
      </dl>
      {disease.coverage === "skeleton" ? (
        <div className="d-hero__notice" role="note">
          <span aria-hidden>⚠️</span>
          <p>
            <b>{copy.skeletonNoticeTitle}</b> {copy.skeletonNoticeBody}
          </p>
        </div>
      ) : null}
      <div className="d-hero__actions">
        <Button variant="primary" type="button" onClick={() => onNav(`/diseases/${slug}/guidelines`)}>
          {isClinician ? "Open guidelines" : copy.guidelinesCta}
        </Button>
        <Button type="button" onClick={() => onNav(`/diseases/${slug}/flowchart`)}>
          View pathway
        </Button>
        <Button variant="ghost" type="button" onClick={() => onNav(`/start-research?disease=${encodeURIComponent(slug)}`)}>
          {copy.researchRunCta}
        </Button>
        <Button variant="ghost" type="button" onClick={() => onNav(`/doctors?disease=${encodeURIComponent(slug)}`)}>
          {isClinician ? "Expert directory" : "Find specialists"} ({disease.doctorsCount})
        </Button>
        {isClerkEnabled() ? (
          <SignedIn>
            <WatchDiseaseButton slug={slug} />
          </SignedIn>
        ) : null}
      </div>
    </div>
  );
}
