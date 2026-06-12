import { useEffect, useState } from "react";
import {
  approveDisease,
  buildCourtesyMailto,
  fetchPendingContributions,
  fetchUnlistedDiseases,
  patchParentRec,
  patchSubmission,
  type CatalogDisease,
  type DoctorSubmission,
  type ParentRecSubmission,
} from "@gene-guidelines/ops";
import "./users-view.css";

type LoadState =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "ready"; diseases: readonly CatalogDisease[] };

type ContribState =
  | { status: "loading" }
  | { status: "error"; message: string }
  | {
      status: "ready";
      submissions: readonly DoctorSubmission[];
      parentRecs: readonly ParentRecSubmission[];
    };

/**
 * Superadmin Catalog view: the disease approval queue (RES-1) plus the DOC-5
 * parent-contribution moderation sections — doctor submissions (with the
 * ADR-009 courtesy-email mailto + mark-sent) and parent recommendations.
 * Mirrors the Users-view table idiom.
 */
export function CatalogView() {
  const [state, setState] = useState<LoadState>({ status: "loading" });
  const [busySlug, setBusySlug] = useState<string | null>(null);
  const [contrib, setContrib] = useState<ContribState>({ status: "loading" });
  const [busyId, setBusyId] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      await Promise.resolve();
      if (cancelled) {
        return;
      }
      try {
        const diseases = await fetchUnlistedDiseases();
        if (!cancelled) {
          setState({ status: "ready", diseases });
        }
      } catch (e: unknown) {
        if (!cancelled) {
          setState({
            status: "error",
            message:
              e instanceof Error ? e.message : "Could not load the catalog queue.",
          });
        }
      }
      try {
        const pending = await fetchPendingContributions();
        if (!cancelled) {
          setContrib({
            status: "ready",
            submissions: pending.submissions,
            parentRecs: pending.parent_recs,
          });
        }
      } catch (e: unknown) {
        if (!cancelled) {
          setContrib({
            status: "error",
            message:
              e instanceof Error ? e.message : "Could not load the contributions queue.",
          });
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const approve = async (disease: CatalogDisease) => {
    setBusySlug(disease.slug);
    try {
      await approveDisease(disease.slug);
      setState((prev) =>
        prev.status === "ready"
          ? {
              status: "ready",
              diseases: prev.diseases.filter((d) => d.slug !== disease.slug),
            }
          : prev,
      );
    } catch {
      // Leave the row; the admin can retry. Errors surface on reload.
    } finally {
      setBusySlug(null);
    }
  };

  const moderateSubmission = async (
    id: string,
    reviewStatus: "approved" | "rejected",
  ) => {
    setBusyId(id);
    try {
      await patchSubmission(id, { review_status: reviewStatus });
      setContrib((prev) =>
        prev.status === "ready"
          ? { ...prev, submissions: prev.submissions.filter((s) => s.id !== id) }
          : prev,
      );
    } catch {
      // retryable; surfaces on reload
    } finally {
      setBusyId(null);
    }
  };

  const markCourtesySent = async (id: string) => {
    setBusyId(id);
    try {
      const updated = await patchSubmission(id, { rodo_email_sent: true });
      setContrib((prev) =>
        prev.status === "ready"
          ? {
              ...prev,
              submissions: prev.submissions.map((s) =>
                s.id === id ? updated : s,
              ),
            }
          : prev,
      );
    } catch {
      // retryable
    } finally {
      setBusyId(null);
    }
  };

  const moderateParentRec = async (
    id: string,
    reviewStatus: "approved" | "rejected",
  ) => {
    setBusyId(id);
    try {
      await patchParentRec(id, { review_status: reviewStatus });
      setContrib((prev) =>
        prev.status === "ready"
          ? { ...prev, parentRecs: prev.parentRecs.filter((r) => r.id !== id) }
          : prev,
      );
    } catch {
      // retryable
    } finally {
      setBusyId(null);
    }
  };

  return (
    <section className="admin-section users-view">
      <h1 className="admin-section__title">Catalog</h1>

      {/* -- Disease approval queue (RES-1) -- */}
      <p className="admin-section__lead">
        Diseases launched from public research are unlisted until approved.
        Approve one to publish it to the public catalog index.
      </p>
      {state.status === "loading" ? (
        <p className="admin-section__lead">Loading the approval queue…</p>
      ) : state.status === "error" ? (
        <p className="admin-section__lead" role="alert">
          {state.message}
        </p>
      ) : (
        <table className="users-view__table">
          <thead>
            <tr>
              <th scope="col">Slug</th>
              <th scope="col">Name</th>
              <th scope="col">Status</th>
              <th scope="col">Drafted</th>
              <th scope="col">Action</th>
            </tr>
          </thead>
          <tbody>
            {state.diseases.length === 0 ? (
              <tr>
                <td colSpan={5} className="users-view__empty">
                  No diseases awaiting approval.
                </td>
              </tr>
            ) : (
              state.diseases.map((disease) => (
                <tr key={disease.slug}>
                  <td>
                    <code>{disease.slug}</code>
                  </td>
                  <td>{disease.name}</td>
                  <td>
                    <span className="users-view__badge users-view__badge--pending">
                      {disease.status}
                    </span>
                  </td>
                  <td>{disease.aiDraftDate ?? "—"}</td>
                  <td>
                    <button
                      type="button"
                      className="users-view__approve"
                      onClick={() => void approve(disease)}
                      disabled={busySlug === disease.slug}
                    >
                      {busySlug === disease.slug ? "Approving…" : "Approve"}
                    </button>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      )}

      {/* -- Doctor submissions (DOC-5) -- */}
      <h2 className="admin-section__title">Doctor submissions (pending)</h2>
      <p className="admin-section__lead">
        Clinicians proposed by parents. Approving publishes a parent-added
        profile; send the courtesy email (ADR 009) and mark it sent for RODO
        record-keeping.
      </p>
      {contrib.status === "loading" ? (
        <p className="admin-section__lead">Loading submissions…</p>
      ) : contrib.status === "error" ? (
        <p className="admin-section__lead" role="alert">
          {contrib.message}
        </p>
      ) : (
        <table className="users-view__table">
          <thead>
            <tr>
              <th scope="col">Name</th>
              <th scope="col">Where</th>
              <th scope="col">Disease</th>
              <th scope="col">RODO</th>
              <th scope="col">Actions</th>
            </tr>
          </thead>
          <tbody>
            {contrib.submissions.length === 0 ? (
              <tr>
                <td colSpan={5} className="users-view__empty">
                  No doctor submissions awaiting review.
                </td>
              </tr>
            ) : (
              contrib.submissions.map((s) => (
                <tr key={s.id}>
                  <td>
                    {s.name}
                    {s.possible_duplicate ? (
                      <span
                        className="users-view__badge users-view__badge--pending users-view__badge--inline"
                        title="Generated slug collides with an existing profile"
                      >
                        possible duplicate
                      </span>
                    ) : null}
                    {s.specialty ? <div>{s.specialty}</div> : null}
                  </td>
                  <td>
                    {s.institution || "—"}
                    {s.city || s.country ? (
                      <div>
                        {[s.city, s.country].filter(Boolean).join(", ")}
                      </div>
                    ) : null}
                  </td>
                  <td>{s.disease_slug ? <code>{s.disease_slug}</code> : "—"}</td>
                  <td>
                    {s.rodo_email_sent_at ? (
                      <span className="users-view__badge users-view__badge--ok">
                        sent
                      </span>
                    ) : (
                      <a href={buildCourtesyMailto(s)} target="_blank" rel="noreferrer">
                        Courtesy email
                      </a>
                    )}
                  </td>
                  <td>
                    {!s.rodo_email_sent_at ? (
                      <button
                        type="button"
                        className="users-view__approve"
                        onClick={() => void markCourtesySent(s.id)}
                        disabled={busyId === s.id}
                      >
                        Mark courtesy email sent
                      </button>
                    ) : null}{" "}
                    <button
                      type="button"
                      className="users-view__approve"
                      onClick={() => void moderateSubmission(s.id, "approved")}
                      disabled={busyId === s.id}
                    >
                      Approve
                    </button>{" "}
                    <button
                      type="button"
                      className="users-view__approve"
                      onClick={() => void moderateSubmission(s.id, "rejected")}
                      disabled={busyId === s.id}
                    >
                      Reject
                    </button>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      )}

      {/* -- Parent recommendations (DOC-5) -- */}
      <h2 className="admin-section__title">Parent recommendations (pending)</h2>
      <p className="admin-section__lead">
        Family experiences left for a doctor. Approving attaches the
        recommendation to the doctor&rsquo;s public profile.
      </p>
      {contrib.status === "ready" ? (
        <table className="users-view__table">
          <thead>
            <tr>
              <th scope="col">Doctor</th>
              <th scope="col">Recommendation</th>
              <th scope="col">From</th>
              <th scope="col">Actions</th>
            </tr>
          </thead>
          <tbody>
            {contrib.parentRecs.length === 0 ? (
              <tr>
                <td colSpan={4} className="users-view__empty">
                  No recommendations awaiting review.
                </td>
              </tr>
            ) : (
              contrib.parentRecs.map((r) => (
                <tr key={r.id}>
                  <td>
                    <code>{r.doctor_slug}</code>
                  </td>
                  <td>{r.text}</td>
                  <td>
                    {r.relation}
                    {r.region ? ` · ${r.region}` : ""}
                  </td>
                  <td>
                    <button
                      type="button"
                      className="users-view__approve"
                      onClick={() => void moderateParentRec(r.id, "approved")}
                      disabled={busyId === r.id}
                    >
                      Approve
                    </button>{" "}
                    <button
                      type="button"
                      className="users-view__approve"
                      onClick={() => void moderateParentRec(r.id, "rejected")}
                      disabled={busyId === r.id}
                    >
                      Reject
                    </button>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      ) : null}
    </section>
  );
}
