export type ClerkRole = "user" | "admin" | "super_admin";

type ClerkPublicUser = {
  publicMetadata?: Record<string, unknown>;
};

export function clerkRoleFromUser(user: ClerkPublicUser | null | undefined): ClerkRole {
  const meta = user?.publicMetadata as { role?: string } | undefined;
  const role = meta?.role;
  if (role === "super_admin") return "super_admin";
  if (role === "admin") return "admin";
  return "user";
}

export function isClerkAdmin(user: ClerkPublicUser | null | undefined): boolean {
  const role = clerkRoleFromUser(user);
  return role === "admin" || role === "super_admin";
}

export function isClerkSuperAdmin(user: ClerkPublicUser | null | undefined): boolean {
  return clerkRoleFromUser(user) === "super_admin";
}
