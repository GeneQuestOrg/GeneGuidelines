/** Current page URL for sharing (hash-router aware). */
export function getCurrentPageUrl(): string {
  if (typeof window === "undefined") {
    return "";
  }
  return window.location.href;
}

export function shareMessage(diseaseName: string, url: string): string {
  return `I wanted to share this guideline summary for ${diseaseName} with you: ${url}`;
}

export function buildWhatsAppShareUrl(message: string): string {
  return `https://wa.me/?text=${encodeURIComponent(message)}`;
}

export function buildEmailShareUrl(subject: string, body: string): string {
  return `mailto:?subject=${encodeURIComponent(subject)}&body=${encodeURIComponent(body)}`;
}
