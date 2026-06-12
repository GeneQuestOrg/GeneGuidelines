import { useState } from "react";
import { ROLE_OPTIONS } from "./roleOptions";
import type { SelectableRole } from "../types/account";
import "./role-picker.css";

export interface RolePickerModalProps {
  /** Apply the one-time role selection. Resolves once `/me` is updated. */
  onSelect: (role: SelectableRole) => Promise<void>;
}

/**
 * One-time role selection shown after first login when `/me` returns `role:null`.
 * Not dismissable — choosing a role is required to use the account. Doctors are
 * told their access is pending verification (handled by the AccountMenu badge).
 */
export function RolePickerModal({ onSelect }: RolePickerModalProps) {
  const [role, setRole] = useState<SelectableRole>("parent");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async () => {
    setSubmitting(true);
    setError(null);
    try {
      await onSelect(role);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Could not save your selection. Please try again.");
      setSubmitting(false);
    }
  };

  return (
    <div className="role-picker" role="dialog" aria-modal={true} aria-label="Choose your role">
      <div className="role-picker__sheet">
        <h2 className="role-picker__title">Welcome — how will you use GeneGuidelines?</h2>
        <p className="role-picker__intro">
          Choose the role that fits you best. This is a one-time choice; contact us if you need it
          changed later.
        </p>

        <div className="role-picker__options" role="radiogroup" aria-label="Select your role">
          {ROLE_OPTIONS.map((option) => (
            <label
              key={option.value}
              className={
                role === option.value
                  ? "role-picker__option is-active"
                  : "role-picker__option"
              }
            >
              <input
                type="radio"
                name="role"
                value={option.value}
                checked={role === option.value}
                onChange={() => setRole(option.value)}
              />
              <div>
                <b>{option.label}</b>
                <span>{option.description}</span>
              </div>
            </label>
          ))}
        </div>

        {error != null ? (
          <p className="role-picker__err" role="alert">
            {error}
          </p>
        ) : null}

        <div className="role-picker__actions">
          <button
            type="button"
            className="btn btn--primary"
            onClick={() => void submit()}
            disabled={submitting}
          >
            {submitting ? "Saving…" : "Continue"}
          </button>
        </div>
      </div>
    </div>
  );
}
