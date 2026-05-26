import { useEffect, useRef, useState } from "react";
import {
  SignInButton,
  SignedIn,
  SignedOut,
  UserButton,
  useUser,
} from "@clerk/clerk-react";
import { Button } from "@gene-guidelines/ui";
import { ApiRequestError } from "../api/client";
import {
  fetchMe,
  fetchNotifications,
  markNotificationsRead,
  type MeResponse,
  type NotificationItem,
} from "../api/account";
import { ActiveResearchSection } from "../components/ActiveResearchSection";
import { PersonaSwitcher } from "../components/PersonaSwitcher";
import { WatchedDiseasesSection } from "../components/WatchedDiseasesSection";
import { isClerkEnabled } from "../auth/clerkConfig";
import { getAdminAppUrl } from "../config/adminUrl";
import { repositories } from "../repositories";
import type { AudienceView } from "../router/types";
import type { ResearchRun } from "../types/researchRun";
import "./account-view.css";

export interface AccountViewProps {
  onNav: (path: string) => void;
  onSignIn: () => void;
  view: AudienceView;
  onViewChange: (v: AudienceView) => void;
}

function userInitials(name: string | null | undefined, email: string | null | undefined): string {
  const source = (name ?? email ?? "?").trim();
  const parts = source.split(/\s+/).filter(Boolean);
  if (parts.length >= 2) {
    return `${parts[0]![0] ?? ""}${parts[1]![0] ?? ""}`.toUpperCase();
  }
  return source.slice(0, 2).toUpperCase();
}

function QuotaCard({ me }: { me: MeResponse }) {
  const q = me.run_quota;
  const isAdmin = me.role === "admin" && q.unlimited;
  const limit = q.limit ?? 3;
  const remaining = q.remaining ?? 0;
  const used = q.used;
  const pct = isAdmin ? 100 : limit > 0 ? Math.min(100, Math.round((used / limit) * 100)) : 0;
  const windowLabel = q.window_hours === 24 ? "24 hours" : `${q.window_hours} hours`;

  return (
    <div className="account__card">
      <p className="account__card-label">Research runs</p>
      {isAdmin ? (
        <>
          <p className="account__card-value">Unlimited</p>
          <div className="account__quota-bar" aria-hidden>
            <div className="account__quota-fill account__quota-fill--full" />
          </div>
          <p className="account__quota-hint">No daily cap for admin accounts.</p>
        </>
      ) : (
        <>
          <p className="account__card-value">
            {remaining} of {limit} left
          </p>
          <div
            className="account__quota-bar"
            role="progressbar"
            aria-valuenow={remaining}
            aria-valuemin={0}
            aria-valuemax={limit}
            aria-label={`${remaining} of ${limit} research runs remaining`}
          >
            <div className="account__quota-fill" style={{ width: `${100 - pct}%` }} />
          </div>
          <p className="account__quota-hint">
            Resets on a rolling {windowLabel} window (bootstrap, guideline, and related runs).
          </p>
        </>
      )}
    </div>
  );
}

function timeAgo(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const minutes = Math.floor(diff / 60_000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

function NotificationsSection({ notifications, onMarkAllRead }: {
  notifications: readonly NotificationItem[];
  onMarkAllRead: () => void;
}) {
  const hasUnread = notifications.some((n) => n.read_at == null);

  if (notifications.length === 0) {
    return (
      <div>
        <h3 className="account__section-title">Updates</h3>
        <p className="account__empty-runs">No notifications yet.</p>
      </div>
    );
  }

  return (
    <div>
      <h3 className="account__section-title" style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
        Updates
        {hasUnread ? (
          <Button type="button" variant="ghost" onClick={onMarkAllRead}>
            Mark all read
          </Button>
        ) : null}
      </h3>
      <ul className="account__notif-list" style={{ listStyle: "none", padding: 0, margin: 0 }}>
        {notifications.map((n) => (
          <li
            key={n.id}
            className={`account__notif-item${n.read_at == null ? " account__notif-item--unread" : ""}`}
          >
            <p className="account__notif-label">
              {n.label ?? n.flow_key ?? "Research run"}
              {" "}
              <span className={`account__status-badge account__status-badge--${n.status}`}>
                {n.status}
              </span>
            </p>
            <p className="account__notif-meta">
              {n.disease_slug != null ? `${n.disease_slug} · ` : ""}
              {timeAgo(n.created_at)}
            </p>
          </li>
        ))}
      </ul>
    </div>
  );
}

function SignedInAccount({
  onNav,
  view,
  onViewChange,
}: {
  onNav: (path: string) => void;
  view: AudienceView;
  onViewChange: (v: AudienceView) => void;
}) {
  const { user, isLoaded } = useUser();
  const [me, setMe] = useState<MeResponse | null>(null);
  const [meError, setMeError] = useState<string | null>(null);
  const [myRuns, setMyRuns] = useState<readonly ResearchRun[]>([]);
  const [notifications, setNotifications] = useState<readonly NotificationItem[]>([]);
  const viewSyncedRef = useRef(false);

  useEffect(() => {
    if (!isLoaded || user == null) return;
    const cancelled = false;
    void fetchMe()
      .then((profile) => {
        if (!cancelled) {
          setMe(profile);
          setMeError(null);
        }
      })
      .catch((e: unknown) => {
        if (!cancelled) {
          setMe(null);
          if (e instanceof ApiRequestError && e.status === 503) {
            setMeError(
              "Backend cannot verify Clerk sessions. Add CLERK_SECRET_KEY to repo root `.env` and restart `make dev`.",
            );
          } else if (e instanceof ApiRequestError && e.status === 401) {
            setMeError(
              `${e.message} Try signing out and back in.`,
            );
          } else if (e instanceof Error) {
            setMeError(e.message);
          } else {
            setMeError("Could not load account from API.");
          }
        }
      });
  }, [isLoaded, user]);

  // Sync audience_view from server once on me load
  useEffect(() => {
    if (me == null || viewSyncedRef.current) return;
    viewSyncedRef.current = true;
    if (me.audience_view != null && me.audience_view !== view) {
      onViewChange(me.audience_view);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [me]);

  useEffect(() => {
    if (!isLoaded || user == null || me == null) return;
    let cancelled = false;
    void repositories()
      .researchRuns.listMyActiveRuns(5)
      .then((runs) => {
        if (!cancelled) setMyRuns(runs);
      })
      .catch(() => {
        if (!cancelled) setMyRuns([]);
      });
    return () => {
      cancelled = true;
    };
  }, [isLoaded, user, me]);

  useEffect(() => {
    if (!isLoaded || user == null || me == null) return;
    let cancelled = false;
    void fetchNotifications({ unreadOnly: false, limit: 10 })
      .then((notifs) => {
        if (!cancelled) {
          setNotifications(notifs);
          const unreadIds = notifs
            .filter((n) => n.read_at == null)
            .map((n) => n.id);
          if (unreadIds.length > 0) {
            void markNotificationsRead({ ids: unreadIds });
          }
        }
      })
      .catch(() => {
        if (!cancelled) setNotifications([]);
      });
    return () => {
      cancelled = true;
    };
  }, [isLoaded, user, me]);

  const handleMarkAllRead = () => {
    setNotifications((prev) =>
      prev.map((n) => ({ ...n, read_at: n.read_at ?? new Date().toISOString() })),
    );
    void markNotificationsRead({ all: true });
  };

  if (!isLoaded || user == null) {
    return <p className="account__loading">Loading profile…</p>;
  }

  if (me == null) {
    return (
      <p className={meError != null ? "account__alert" : "account__loading"}>
        {meError ?? "Loading account from API…"}
      </p>
    );
  }

  const adminUrl = getAdminAppUrl();
  const email = user.primaryEmailAddress?.emailAddress ?? me.email ?? "—";
  const displayName = user.fullName ?? "—";
  const imageUrl = user.imageUrl;

  return (
    <>
      <div className="account__profile">
        {imageUrl != null && imageUrl !== "" ? (
          <img className="account__avatar" src={imageUrl} alt="" width={56} height={56} />
        ) : (
          <div className="account__avatar account__avatar--initials" aria-hidden>
            {userInitials(displayName, email)}
          </div>
        )}
        <div className="account__identity">
          <h2 className="account__name">{displayName}</h2>
          <p className="account__email">{email}</p>
        </div>
        <div className="account__manage">
          <UserButton afterSignOutUrl="/" />
        </div>
      </div>

      <div className="account__grid">
        <div className="account__card">
          <p className="account__card-label">Access level</p>
          <span
            className={`account__badge account__badge--${me.role === "admin" ? "admin" : "user"}`}
          >
            {me.role}
          </span>
          <p className="account__quota-hint">
            {me.role === "admin"
              ? "Full operator access including the admin panel."
              : "Standard access — 3 research starts per day."}
          </p>
        </div>
        <QuotaCard me={me} />
      </div>

      <WatchedDiseasesSection onNav={onNav} />

      <div className="account__actions">
        <Button variant="primary" onClick={() => onNav("/start-research")}>
          Start research
        </Button>
        <Button variant="ghost" onClick={() => onNav("/add-disease")}>
          Add a disease
        </Button>
        {me.role === "admin" && adminUrl != null ? (
          <Button
            variant="ghost"
            onClick={() => {
              window.open(adminUrl, "_blank", "noopener,noreferrer");
            }}
          >
            Admin panel ↗
          </Button>
        ) : null}
      </div>

      {myRuns.length > 0 ? (
        <ActiveResearchSection runs={myRuns} onNav={onNav} />
      ) : (
        <div>
          <h3 className="account__section-title">Your active workflows</h3>
          <p className="account__empty-runs">
            No runs in progress right now. Start a guideline or bootstrap a new disease to see live
            progress here.
          </p>
        </div>
      )}

      <NotificationsSection
        notifications={notifications}
        onMarkAllRead={handleMarkAllRead}
      />

      <div style={{ marginBottom: "1.75rem" }}>
        <h3 className="account__section-title">Preferred view</h3>
        <PersonaSwitcher view={view} onChange={onViewChange} />
      </div>
    </>
  );
}

function SignedOutAccount() {
  return (
    <div className="account__signed-out">
      <p className="account__signed-out-lead">
        Sign in to start disease research, track running workflows, and manage your daily run quota.
      </p>
      <ul className="account__benefits">
        <li>Start PubMed-backed guideline research for rare diseases</li>
        <li>Bootstrap new disease entries with automated workflows</li>
        <li>See live progress on runs you own</li>
      </ul>
      <SignInButton mode="modal">
        <Button variant="primary">Sign in or register</Button>
      </SignInButton>
    </div>
  );
}

export function AccountView({ onNav, onSignIn, view, onViewChange }: AccountViewProps) {
  const clerkOn = isClerkEnabled();

  if (clerkOn) {
    return (
      <section className="page page--account">
        <header className="account__hero">
          <p className="account__eyebrow">Account</p>
          <h1 className="page__title">Your account</h1>
          <p className="page__lead">
            Profile, access level, and research run allowance for GeneGuidelines.
          </p>
        </header>
        <SignedOut>
          <SignedOutAccount />
        </SignedOut>
        <SignedIn>
          <SignedInAccount onNav={onNav} view={view} onViewChange={onViewChange} />
        </SignedIn>
      </section>
    );
  }

  return (
    <section className="page page--account">
      <header className="account__hero">
        <p className="account__eyebrow">Account</p>
        <h1 className="page__title">Your account</h1>
      </header>
      <p className="page__lead">
        Configure <code>VITE_CLERK_PUBLISHABLE_KEY</code> to enable sign-in. In local dev without
        Clerk, pipeline calls use the backend dev bypass when no API key is set.
      </p>
      <p className="page__actions">
        <Button variant="primary" onClick={onSignIn}>
          Sign in
        </Button>
      </p>
    </section>
  );
}
