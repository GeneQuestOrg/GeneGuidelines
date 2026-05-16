import { z } from "zod";

export const ACCOUNT_STORAGE_KEY = "gg-account";

export const FIELD_LIMITS = {
  email: 254,
  name: 100,
  specialty: 100,
  institution: 200,
  diseaseSlug: 64,
  maxDiseases: 50,
} as const;

const roleSchema = z.enum(["parent", "doctor", "researcher"]);

const diseaseSlugSchema = z
  .string()
  .min(1)
  .max(FIELD_LIMITS.diseaseSlug)
  .regex(/^[a-z0-9-]+$/);

export const accountSchema = z.object({
  email: z.string().email().max(FIELD_LIMITS.email),
  name: z.string().min(1).max(FIELD_LIMITS.name),
  role: roleSchema,
  specialty: z.string().max(FIELD_LIMITS.specialty).nullable(),
  institution: z.string().max(FIELD_LIMITS.institution).nullable(),
  diseases: z.array(diseaseSlugSchema).max(FIELD_LIMITS.maxDiseases),
  verified: z.boolean(),
  joinedAt: z.string().regex(/^\d{4}-\d{2}-\d{2}$/),
});

export type Account = z.infer<typeof accountSchema>;

export function parseStoredAccount(raw: string): Account | null {
  try {
    const parsed: unknown = JSON.parse(raw);
    const result = accountSchema.safeParse(parsed);
    return result.success ? result.data : null;
  } catch {
    return null;
  }
}

export function trimField(value: string, max: number): string {
  return value.trim().slice(0, max);
}

export function fieldTooLong(value: string, max: number): boolean {
  return value.trim().length > max;
}
