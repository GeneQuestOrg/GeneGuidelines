import { useCallback, useEffect, useMemo, useState } from "react";
import { Badge, Button, Status } from "@gene-guidelines/ui";
import {
  fetchGuidelinePrDetail,
  fetchGuidelinePrs,
  reviewGuidelinePr,
  type GuidelinePrDetail,
  type GuidelinePrReviewAction,
  type GuidelinePrStatus,
  type GuidelinePrSummary,
} from "../api/client";
import { pubmedArticleUrl } from "../utils/pubmedUrl";
import "../styles/ops-hub.css";
import "../styles/ops-prs.css";

type StatusFilter = "all" | GuidelinePrStatus;

const STATUS_FILTERS: { id: StatusFilter; label: string }[] = [
  { id: "all", label: "All" },
  { id: "pending", label: "Pending" },
  { id: "under-review", label: "Under review" },
  { id: "verified", label: "Published" },
  { id: "rejected", label: "Rejected" },
];

function statusBadgeVariant(status: GuidelinePrStatus): "default" | "ok" {
  if (status === "verified") return "ok";
  return "default";
}

export function GuidelinePrsView() {
  const [prs, setPrs] = useState<GuidelinePrSummary[]>([]);
  const [filter, setFilter] = useState<StatusFilter>("all");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<GuidelinePrDetail | null>(null);
  const [listError, setListError] = useState<string | null>(null);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [reviewBusy, setReviewBusy] = useState(false);
  const [reviewer, setReviewer] = useState("");

  const loadList = useCallback(async () => {
    try {
      const status = filter === "all" ? undefined : filter;
      const rows = await fetchGuidelinePrs(status);
      setPrs(rows);
      setListError(null);
      setSelectedId((prev) => prev ?? rows[0]?.id ?? null);
    } catch (e) {
      setListError(String(e));
    }
  }, [filter]);

  useEffect(() => {
    void loadList();
  }, [loadList]);

  useEffect(() => {
    if (!selectedId) {
      setDetail(null);
      setDetailError(null);
      return;
    }
    let cancelled = false;
    setDetailError(null);
    void fetchGuidelinePrDetail(selectedId)
      .then((row) => {
        if (!cancelled) {
          setDetail(row);
          setReviewer(row.reviewer?.trim() ?? "");
        }
      })
      .catch((e) => {
        if (!cancelled) {
          setDetail(null);
          setDetailError(String(e));
        }
      });
    return () => {
      cancelled = true;
    };
  }, [selectedId]);

  const filtered = useMemo(() => {
    if (filter === "all") return prs;
    return prs.filter((p) => p.status === filter);
  }, [filter, prs]);

  const handleReview = useCallback(
    async (action: GuidelinePrReviewAction) => {
      if (!selectedId || reviewBusy) return;
      const needsReviewer = action === "publish";
      const reviewerName = reviewer.trim();
      if (needsReviewer && !reviewerName) {
        setDetailError(
          "Reviewer name is required to publish — enter your name or email below.",
        );
        return;
      }
      setReviewBusy(true);
      setDetailError(null);
      try {
        const updated = await reviewGuidelinePr(
          selectedId,
          action,
          needsReviewer ? reviewerName : reviewerName || undefined,
        );
        setDetail(updated);
        await loadList();
      } catch (e) {
        setDetailError(String(e));
      } finally {
        setReviewBusy(false);
      }
    },
    [loadList, reviewBusy, reviewer, selectedId],
  );

  const canActOnPr =
    detail != null &&
    detail.status !== "verified" &&
    detail.status !== "rejected";

  return (
    <div className="ops-hub">
      <div className="ops-hub__body">
        <aside className="ops-hub__aside" aria-label="Guideline PR queue">
          <div className="ops-hub__aside-head">
            <h2>Guideline PRs</h2>
            <p className="ops-prs__aside-lead">
              AI-proposed updates awaiting specialist review.
            </p>
          </div>
          <div className="ops-prs__filters" role="tablist" aria-label="Status filter">
            {STATUS_FILTERS.map((f) => (
              <button
                key={f.id}
                type="button"
                role="tab"
                aria-selected={filter === f.id}
                className={
                  filter === f.id ? "ops-prs__filter is-active" : "ops-prs__filter"
                }
                onClick={() => setFilter(f.id)}
              >
                {f.label}
              </button>
            ))}
          </div>
          {listError ? <p className="ops-hub__empty">{listError}</p> : null}
          {filtered.length === 0 && !listError ? (
            <p className="ops-hub__empty">No PRs in this filter.</p>
          ) : (
            <ul className="ops-hub__runs">
              {filtered.map((pr) => (
                <li key={pr.id}>
                  <button
                    type="button"
                    className={
                      selectedId === pr.id
                        ? "ops-run-item is-active"
                        : "ops-run-item"
                    }
                    onClick={() => setSelectedId(pr.id)}
                  >
                    <p className="ops-run-item__label">{pr.id}</p>
                    <p className="ops-run-item__meta">
                      <Badge variant={statusBadgeVariant(pr.status)}>
                        {pr.status}
                      </Badge>
                      <span>{pr.disease}</span>
                    </p>
                    <p className="ops-prs__item-title">{pr.title}</p>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </aside>
        <main className="ops-hub__main">
          {!selectedId ? (
            <p className="ops-hub__empty">Select a PR to review the diff.</p>
          ) : detailError && !detail ? (
            <p className="ops-hub__empty">{detailError}</p>
          ) : !detail ? (
            <p className="ops-hub__empty">Loading…</p>
          ) : (
            <article className="ops-prs__detail">
              <header className="ops-prs__detail-head">
                <div>
                  <p className="ops-prs__detail-id">{detail.id}</p>
                  <h1 className="ops-prs__detail-title">{detail.title}</h1>
                  <p className="ops-prs__detail-meta">
                    <span>{detail.disease}</span>
                    <span>Opened {detail.opened}</span>
                    <span>{detail.author}</span>
                    {detail.reviewer ? (
                      <span>Reviewer: {detail.reviewer}</span>
                    ) : null}
                  </p>
                </div>
                <Status status={detail.status} />
              </header>
              <section className="ops-prs__section">
                <h2>Summary</h2>
                <p>{detail.summary}</p>
                {detail.citationsCount > 0 ? (
                  <p className="ops-prs__citations">
                    {detail.citationsCount} supporting citation
                    {detail.citationsCount === 1 ? "" : "s"}
                  </p>
                ) : null}
              </section>
              <section className="ops-prs__section">
                <h2>Proposed changes</h2>
                <ul className="ops-prs__diff">
                  {detail.diff.map((line, i) => (
                    <li
                      key={`${line.type}-${i}`}
                      className={
                        line.type === "added"
                          ? "ops-prs__diff-line is-added"
                          : "ops-prs__diff-line is-removed"
                      }
                    >
                      <span className="ops-prs__diff-gutter" aria-hidden>
                        {line.type === "added" ? "+" : "−"}
                      </span>
                      {line.text}
                    </li>
                  ))}
                </ul>
              </section>
              {detail.papers.length > 0 ? (
                <section className="ops-prs__section">
                  <h2>Evidence</h2>
                  <ul className="ops-prs__papers">
                    {detail.papers.map((paper) => (
                      <li key={paper.pmid}>
                        <a
                          className="ops-prs__paper-pmid"
                          href={pubmedArticleUrl(paper.pmid)}
                          target="_blank"
                          rel="noopener noreferrer"
                        >
                          PMID {paper.pmid}
                        </a>
                        <span>{paper.title}</span>
                        <span className="ops-prs__paper-year">
                          ({paper.year})
                        </span>
                      </li>
                    ))}
                  </ul>
                </section>
              ) : null}
              {canActOnPr ? (
                <footer className="ops-prs__actions">
                  <div className="ops-field ops-field--wide">
                    <label htmlFor="ops-pr-reviewer">Reviewer (required to publish)</label>
                    <input
                      id="ops-pr-reviewer"
                      type="text"
                      value={reviewer}
                      onChange={(ev) => setReviewer(ev.target.value)}
                      placeholder="Dr. Name or operator email"
                      disabled={reviewBusy}
                      autoComplete="name"
                    />
                  </div>
                  <Button
                    type="button"
                    disabled={reviewBusy}
                    onClick={() => void handleReview("publish")}
                  >
                    Publish to guideline
                  </Button>
                  <Button
                    type="button"
                    variant="ghost"
                    disabled={reviewBusy}
                    onClick={() => void handleReview("request_changes")}
                  >
                    Request changes
                  </Button>
                  <Button
                    type="button"
                    variant="ghost"
                    disabled={reviewBusy}
                    onClick={() => void handleReview("reject")}
                  >
                    Reject
                  </Button>
                  <p className="ops-prs__actions-hint">
                    Publish merges this PR into the live guideline document on the public site.
                  </p>
                  {detailError ? (
                    <p className="ops-prs__action-error" role="alert">
                      {detailError}
                    </p>
                  ) : null}
                </footer>
              ) : null}
            </article>
          )}
        </main>
      </div>
    </div>
  );
}