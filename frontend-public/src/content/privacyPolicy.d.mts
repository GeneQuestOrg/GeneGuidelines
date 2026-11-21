import type { Locale } from "../router/locale";

export declare const PRIVACY_POLICY_VERSION: string;
export declare const PRIVACY_PATH: string;
export declare const VERSION_PLACEHOLDER: string;

export declare function privacyPolicyHref(locale: Locale, sectionId?: string): string;
export declare function formatPolicyVersion(locale: Locale): string;

export interface InlineToken {
  readonly kind: "text" | "bold" | "code" | "email";
  readonly value: string;
}

export declare function inlineTokens(text: string): InlineToken[];
