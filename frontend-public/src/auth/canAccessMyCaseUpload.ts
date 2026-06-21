import type { AccountContextValue } from "./accountContext";

/**
 * Whether the signed-in viewer may upload to My case.
 * When Auth0 is not configured (local dev), uploads stay open without auth.
 */
export function canAccessMyCaseUpload(ctx: AccountContextValue): boolean {
  if (!ctx.signInAvailable) {
    return true;
  }
  if (ctx.loading || !ctx.isAuthenticated || ctx.account == null) {
    return false;
  }
  if (ctx.needsRoleSelection) {
    return false;
  }
  return ctx.account.role === "parent" || ctx.account.role === "superadmin";
}

export type MyCaseGateVariant = "sign-in" | "needs-role" | "wrong-role";

export function myCaseGateVariant(ctx: AccountContextValue): MyCaseGateVariant {
  if (!ctx.signInAvailable || !ctx.isAuthenticated || ctx.account == null) {
    return "sign-in";
  }
  if (ctx.needsRoleSelection) {
    return "needs-role";
  }
  return "wrong-role";
}
