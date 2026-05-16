import { useState, useEffect } from "react";
import type { FormEvent } from "react";
import {
  ACCOUNT_STORAGE_KEY,
  FIELD_LIMITS,
  accountSchema,
  fieldTooLong,
  parseStoredAccount,
  trimField,
  type Account,
} from "../accountSchema";
import "./modal.css";
import "./auth-modal.css";

function readAccount(): Account | null {
  try {
    const raw = localStorage.getItem(ACCOUNT_STORAGE_KEY);
    if (raw == null) {
      return null;
    }
    const account = parseStoredAccount(raw);
    if (account == null) {
      localStorage.removeItem(ACCOUNT_STORAGE_KEY);
    }
    return account;
  } catch {
    return null;
  }
}

function writeAccount(acc: Account | null): boolean {
  try {
    if (acc != null) {
      localStorage.setItem(ACCOUNT_STORAGE_KEY, JSON.stringify(acc));
    } else {
      localStorage.removeItem(ACCOUNT_STORAGE_KEY);
    }
    window.dispatchEvent(new Event("gg-account-change"));
    return true;
  } catch {
    return false;
  }
}

export function useAccount(): [Account | null, (acc: Account | null) => void] {
  const [account, setAccount] = useState<Account | null>(() => readAccount());

  useEffect(() => {
    const sync = () => setAccount(readAccount());
    window.addEventListener("gg-account-change", sync);
    window.addEventListener("storage", sync);
    return () => {
      window.removeEventListener("gg-account-change", sync);
      window.removeEventListener("storage", sync);
    };
  }, []);

  const setAccountAndPersist = (acc: Account | null) => {
    if (!writeAccount(acc)) {
      return;
    }
    setAccount(acc);
  };

  return [account, setAccountAndPersist];
}

type AuthMode = "register" | "login";
type RoleValue = Account["role"];

export type { Account };

interface FormState {
  email: string;
  name: string;
  role: RoleValue;
  specialty: string;
  institution: string;
  consent: boolean;
}

const ROLES: ReadonlyArray<{ value: RoleValue; label: string; description: string }> = [
  { value: "parent", label: "Patient / Family", description: "Access disease information and updates for your family" },
  { value: "doctor", label: "Doctor / Clinician", description: "Review and submit clinical guideline PRs" },
  { value: "researcher", label: "Researcher", description: "Follow evidence updates and contribute to research" },
];

export interface AuthModalProps {
  initialMode?: AuthMode;
  onClose: () => void;
  onSuccess?: (account: Account) => void;
}

function validateFormFields(form: FormState, mode: AuthMode): string | null {
  if (fieldTooLong(form.email, FIELD_LIMITS.email)) {
    return `Email must be at most ${FIELD_LIMITS.email} characters`;
  }
  if (mode === "register" && fieldTooLong(form.name, FIELD_LIMITS.name)) {
    return `Name must be at most ${FIELD_LIMITS.name} characters`;
  }
  if (fieldTooLong(form.specialty, FIELD_LIMITS.specialty)) {
    return `Specialty must be at most ${FIELD_LIMITS.specialty} characters`;
  }
  if (fieldTooLong(form.institution, FIELD_LIMITS.institution)) {
    return `Institution must be at most ${FIELD_LIMITS.institution} characters`;
  }
  return null;
}

export function AuthModal({ initialMode = "register", onClose, onSuccess }: AuthModalProps) {
  const [mode, setMode] = useState<AuthMode>(initialMode);
  const [form, setForm] = useState<FormState>({
    email: "",
    name: "",
    role: "parent",
    specialty: "",
    institution: "",
    consent: false,
  });
  const [err, setErr] = useState<string>("");

  const update = (patch: Partial<FormState>) => setForm((f) => ({ ...f, ...patch }));

  const submit = (e: FormEvent) => {
    e.preventDefault();
    setErr("");

    const lengthErr = validateFormFields(form, mode);
    if (lengthErr != null) {
      setErr(lengthErr);
      return;
    }

    const email = trimField(form.email, FIELD_LIMITS.email);
    if (email.length === 0) {
      setErr("Email is required");
      return;
    }
    if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email)) {
      setErr("Invalid email format");
      return;
    }

    if (mode === "register") {
      const name = trimField(form.name, FIELD_LIMITS.name);
      if (name.length === 0) {
        setErr("Name is required");
        return;
      }
      if (!form.consent) {
        setErr("You must accept the terms");
        return;
      }
      const institution = trimField(form.institution, FIELD_LIMITS.institution);
      if (form.role === "doctor" && institution.length === 0) {
        setErr("Doctors: please provide your institution for verification");
        return;
      }
    }

    const name =
      mode === "register"
        ? trimField(form.name, FIELD_LIMITS.name)
        : trimField(form.email.split("@")[0] ?? "", FIELD_LIMITS.name);

    const specialtyRaw = trimField(form.specialty, FIELD_LIMITS.specialty);
    const institutionRaw = trimField(form.institution, FIELD_LIMITS.institution);

    const candidate = {
      email,
      name: name.length > 0 ? name : (email.split("@")[0] ?? "User"),
      role: form.role,
      specialty: specialtyRaw.length > 0 ? specialtyRaw : null,
      institution: institutionRaw.length > 0 ? institutionRaw : null,
      diseases: [] as string[],
      verified: form.role !== "doctor",
      joinedAt: new Date().toISOString().slice(0, 10),
    };

    const parsed = accountSchema.safeParse(candidate);
    if (!parsed.success) {
      setErr("Could not save account — check your entries and try again");
      return;
    }

    if (!writeAccount(parsed.data)) {
      setErr("Could not save account — browser storage may be full or blocked");
      return;
    }
    onSuccess?.(parsed.data);
    onClose();
  };

  return (
    <div
      className="modal"
      onClick={onClose}
      role="dialog"
      aria-modal={true}
      aria-label="Sign in or create account"
    >
      <div className="modal__sheet modal__sheet--auth" onClick={(e) => e.stopPropagation()}>
        <button type="button" className="modal__close" onClick={onClose} aria-label="Close">
          ×
        </button>

        <div className="auth__tabs">
          <button
            type="button"
            className={`auth__tab${mode === "register" ? " is-active" : ""}`}
            onClick={() => setMode("register")}
          >
            Create account
          </button>
          <button
            type="button"
            className={`auth__tab${mode === "login" ? " is-active" : ""}`}
            onClick={() => setMode("login")}
          >
            Sign in
          </button>
        </div>

        <p className="auth__intro">
          {mode === "register"
            ? "Create an account to subscribe to disease updates and — for doctors — review living guideline PRs."
            : "Enter the email you registered with. No password needed — we simulate an immediate sign-in (prototype)."}
        </p>

        <form onSubmit={submit} className="auth__form" noValidate>
          <label className="field">
            <span className="field__label">
              Email <em>· required</em>
            </span>
            <input
              type="email"
              autoFocus
              value={form.email}
              onChange={(e) => update({ email: e.target.value })}
              placeholder="you@example.org"
              maxLength={FIELD_LIMITS.email}
            />
          </label>

          {mode === "register" && (
            <>
              <label className="field">
                <span className="field__label">Name or nickname</span>
                <input
                  type="text"
                  value={form.name}
                  onChange={(e) => update({ name: e.target.value })}
                  placeholder="How you want to appear"
                  maxLength={FIELD_LIMITS.name}
                />
              </label>

              <div className="auth__roles" role="group" aria-label="Select your role">
                {ROLES.map((r) => (
                  <label
                    key={r.value}
                    className={`auth__role${form.role === r.value ? " is-active" : ""}`}
                  >
                    <input
                      type="radio"
                      name="role"
                      value={r.value}
                      checked={form.role === r.value}
                      onChange={() => update({ role: r.value })}
                    />
                    <div>
                      <b>{r.label}</b>
                      <span>{r.description}</span>
                    </div>
                  </label>
                ))}
              </div>

              {form.role === "doctor" && (
                <div className="auth__doctor">
                  <label className="field">
                    <span className="field__label">Specialty</span>
                    <input
                      type="text"
                      value={form.specialty}
                      onChange={(e) => update({ specialty: e.target.value })}
                      placeholder="e.g. Medical Genetics"
                      maxLength={FIELD_LIMITS.specialty}
                    />
                  </label>
                  <label className="field">
                    <span className="field__label">
                      Institution <em>· required for doctors</em>
                    </span>
                    <input
                      type="text"
                      value={form.institution}
                      onChange={(e) => update({ institution: e.target.value })}
                      placeholder="Hospital or university"
                      maxLength={FIELD_LIMITS.institution}
                    />
                  </label>
                </div>
              )}

              <label className="field field--check">
                <input
                  type="checkbox"
                  checked={form.consent}
                  onChange={(e) => update({ consent: e.target.checked })}
                />
                <span>
                  I accept the <b>terms of use</b> and <b>privacy policy</b>
                </span>
              </label>
            </>
          )}

          {err !== "" && (
            <p className="auth__err" role="alert">
              {err}
            </p>
          )}

          <div className="auth__actions">
            <button type="button" className="btn btn--ghost" onClick={onClose}>
              Cancel
            </button>
            <button type="submit" className="btn btn--primary">
              {mode === "register" ? "Create account" : "Sign in"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
