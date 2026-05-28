export type ClerkRole = "user" | "admin";

type ClerkPublicUser = {
  publicMetadata?: Record<string, unknown>;
};

/** Role from Clerk public metadata (`role`: `user` | `admin`). Defaults to user. */
export function clerkRoleFromUser(user: ClerkPublicUser | null | undefined): ClerkRole {
  const meta = user?.publicMetadata as { role?: string } | undefined;
  return meta?.role === "admin" ? "admin" : "user";
}

export function isClerkAdmin(user: ClerkPublicUser | null | undefined): boolean {
  return clerkRoleFromUser(user) === "admin";
}
