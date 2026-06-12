import { useEffect, useState } from "react";
import { fetchUsers, patchUser, type AdminUser } from "@gene-guidelines/ops";
import "./users-view.css";

type LoadState =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "ready"; users: readonly AdminUser[] };

/** A user is awaiting verification when they are a doctor and not yet verified. */
function isPendingVerification(user: AdminUser): boolean {
  return user.role === "doctor" && !user.verified;
}

/**
 * Minimal superadmin Users view: lists every account and lets an admin approve
 * a doctor (PATCH verified=true). The "Pending verification" filter narrows to
 * doctors awaiting approval — the daily review queue.
 */
export function UsersView() {
  const [state, setState] = useState<LoadState>({ status: "loading" });
  const [pendingOnly, setPendingOnly] = useState(false);
  const [busyId, setBusyId] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      await Promise.resolve();
      if (cancelled) {
        return;
      }
      try {
        const users = await fetchUsers();
        if (!cancelled) {
          setState({ status: "ready", users });
        }
      } catch (e: unknown) {
        if (!cancelled) {
          setState({
            status: "error",
            message: e instanceof Error ? e.message : "Could not load users.",
          });
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const approve = async (user: AdminUser) => {
    setBusyId(user.id);
    try {
      const updated = await patchUser(user.id, { verified: true });
      setState((prev) =>
        prev.status === "ready"
          ? {
              status: "ready",
              users: prev.users.map((u) => (u.id === updated.id ? updated : u)),
            }
          : prev,
      );
    } catch {
      // Leave the row as-is; the admin can retry. Errors surface on reload.
    } finally {
      setBusyId(null);
    }
  };

  if (state.status === "loading") {
    return (
      <section className="admin-section">
        <h1 className="admin-section__title">Users</h1>
        <p className="admin-section__lead">Loading accounts…</p>
      </section>
    );
  }

  if (state.status === "error") {
    return (
      <section className="admin-section">
        <h1 className="admin-section__title">Users</h1>
        <p className="admin-section__lead" role="alert">
          {state.message}
        </p>
      </section>
    );
  }

  const rows = pendingOnly
    ? state.users.filter(isPendingVerification)
    : state.users;

  return (
    <section className="admin-section users-view">
      <h1 className="admin-section__title">Users</h1>
      <p className="admin-section__lead">
        Accounts and doctor verification. Approve a clinician to grant verified status.
      </p>

      <label className="users-view__filter">
        <input
          type="checkbox"
          checked={pendingOnly}
          onChange={(e) => setPendingOnly(e.target.checked)}
        />
        Pending verification only
      </label>

      <table className="users-view__table">
        <thead>
          <tr>
            <th scope="col">Email</th>
            <th scope="col">Role</th>
            <th scope="col">Verified</th>
            <th scope="col">ORCID</th>
            <th scope="col">Institution</th>
            <th scope="col">Created</th>
            <th scope="col">Action</th>
          </tr>
        </thead>
        <tbody>
          {rows.length === 0 ? (
            <tr>
              <td colSpan={7} className="users-view__empty">
                {pendingOnly ? "No doctors awaiting verification." : "No users yet."}
              </td>
            </tr>
          ) : (
            rows.map((user) => (
              <tr key={user.id}>
                <td>{user.email}</td>
                <td>{user.role ?? "—"}</td>
                <td>
                  {user.verified ? (
                    <span className="users-view__badge users-view__badge--ok">Verified</span>
                  ) : isPendingVerification(user) ? (
                    <span className="users-view__badge users-view__badge--pending">
                      Pending
                    </span>
                  ) : (
                    "—"
                  )}
                </td>
                <td>
                  {user.orcid != null ? (
                    <a
                      href={`https://orcid.org/${user.orcid}`}
                      target="_blank"
                      rel="noreferrer"
                    >
                      {user.orcid}
                    </a>
                  ) : (
                    "—"
                  )}
                </td>
                <td>{user.institution ?? "—"}</td>
                <td>{user.created_at.slice(0, 10)}</td>
                <td>
                  {isPendingVerification(user) ? (
                    <button
                      type="button"
                      className="users-view__approve"
                      onClick={() => void approve(user)}
                      disabled={busyId === user.id}
                    >
                      {busyId === user.id ? "Approving…" : "Approve"}
                    </button>
                  ) : (
                    "—"
                  )}
                </td>
              </tr>
            ))
          )}
        </tbody>
      </table>
    </section>
  );
}
