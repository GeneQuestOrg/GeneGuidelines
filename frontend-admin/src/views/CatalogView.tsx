import { useEffect, useState } from "react";
import {
  approveDisease,
  fetchUnlistedDiseases,
  type CatalogDisease,
} from "@gene-guidelines/ops";
import "./users-view.css";

type LoadState =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "ready"; diseases: readonly CatalogDisease[] };

/**
 * Minimal superadmin Catalog view (RES-1): lists diseases pending catalog
 * approval (listed=false) and lets an admin approve one into the public index
 * (PATCH listed=true). Mirrors the visual idiom of the Users view.
 */
export function CatalogView() {
  const [state, setState] = useState<LoadState>({ status: "loading" });
  const [busySlug, setBusySlug] = useState<string | null>(null);

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
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const approve = async (disease: CatalogDisease) => {
    setBusySlug(disease.slug);
    try {
      await approveDisease(disease.slug);
      // Approved diseases leave the pending queue.
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

  if (state.status === "loading") {
    return (
      <section className="admin-section">
        <h1 className="admin-section__title">Catalog</h1>
        <p className="admin-section__lead">Loading the approval queue…</p>
      </section>
    );
  }

  if (state.status === "error") {
    return (
      <section className="admin-section">
        <h1 className="admin-section__title">Catalog</h1>
        <p className="admin-section__lead" role="alert">
          {state.message}
        </p>
      </section>
    );
  }

  return (
    <section className="admin-section users-view">
      <h1 className="admin-section__title">Catalog</h1>
      <p className="admin-section__lead">
        Diseases launched from public research are unlisted until approved.
        Approve one to publish it to the public catalog index.
      </p>

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
    </section>
  );
}
