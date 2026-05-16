/** Disease URL slug — aligned with backend/accountSchema disease slugs. */
export const DISEASE_SLUG_PATTERN = /^[a-z0-9-]+$/;

export function isValidDiseaseSlug(slug: string): boolean {
  return slug.length > 0 && slug.length <= 64 && DISEASE_SLUG_PATTERN.test(slug);
}

export function normalizeDiseaseSlug(slug: string): string | null {
  const trimmed = slug.trim().toLowerCase();
  return isValidDiseaseSlug(trimmed) ? trimmed : null;
}
