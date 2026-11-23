/**
 * Polish for the two free-text disease facts the hero shows: the mode of inheritance and the prevalence line.
 *
 * Both are written in English when a disease is researched (the pipeline's default prevalence is literally "Rare disease"), so the Polish page showed "Somatic (not inherited)" under a Polish label. The record has no Polish field, and a model call per page view is not worth it for two short phrases, so this translates the vocabulary those lines are made of: a closed set of inheritance modes and a handful of prevalence words. Anything it does not know stays as written, because a half-English fact is better than an invented one.
 */

type Phrase = readonly [RegExp, string];

const word = (text: string): RegExp => new RegExp(`\\b${text}\\b`, "gi");

/** Longest phrases first, so "x-linked recessive" is not split into two half-translations. */
const INHERITANCE_PL: readonly Phrase[] = [
  [word("autosomal dominant"), "autosomalne dominujące"],
  [word("autosomal recessive"), "autosomalne recesywne"],
  [word("x-linked dominant"), "dominujące sprzężone z chromosomem X"],
  [word("x-linked recessive"), "recesywne sprzężone z chromosomem X"],
  [word("x-linked"), "sprzężone z chromosomem X"],
  [word("y-linked"), "sprzężone z chromosomem Y"],
  [word("not inherited"), "niedziedziczne"],
  [word("most types"), "większość typów"],
  [word("most cases"), "większość przypadków"],
  [word("autosomal"), "autosomalne"],
  [word("dominant"), "dominujące"],
  [word("recessive"), "recesywne"],
  [word("mitochondrial"), "mitochondrialne"],
  [word("somatic"), "somatyczne"],
  [word("mosaic"), "mozaikowe"],
  [word("sporadic"), "sporadyczne"],
  [word("multifactorial"), "wieloczynnikowe"],
  [word("unknown"), "nieznane"],
  [word("or"), "lub"],
  [word("and"), "i"],
];

/** Longest phrases first here too: "rare disease" before "ultra-rare disease" turned the latter into "Ultra-choroba rzadka". */
const PREVALENCE_PL: readonly Phrase[] = [
  [word("true prevalence unknown"), "rzeczywista częstość nieznana"],
  [word("ultra-rare disease"), "choroba ultrarzadka"],
  [word("ultra-rare"), "ultrarzadka"],
  [word("very rare disease"), "choroba bardzo rzadka"],
  [word("very rare"), "bardzo rzadka"],
  [word("rare disease"), "choroba rzadka"],
  [word("rare"), "rzadka"],
  [word("live births"), "żywych urodzeń"],
  [word("births"), "urodzeń"],
  [word("people"), "osób"],
  [word("worldwide"), "na świecie"],
  [word("reported cases"), "opisanych przypadków"],
  [word("cases"), "przypadków"],
  [word("diagnosed"), "rozpoznanych"],
  [word("unknown"), "nieznana"],
  [/\b1 in\b/gi, "1 na"],
  [word("million"), "mln"],
];

function translate(value: string, phrases: readonly Phrase[]): string {
  const out = phrases.reduce((text, [pattern, pl]) => text.replace(pattern, pl), value);
  // Keep the original's capital letter at the start: "Somatic" → "Somatyczne".
  return /^[A-Z]/.test(value) ? out.charAt(0).toUpperCase() + out.slice(1) : out;
}

function isPolish(language: string | undefined): boolean {
  return (language ?? "").toLowerCase().startsWith("pl");
}

export function localizeInheritance(value: string, language: string | undefined): string {
  return isPolish(language) ? translate(value, INHERITANCE_PL) : value;
}

export function localizePrevalence(value: string, language: string | undefined): string {
  return isPolish(language) ? translate(value, PREVALENCE_PL) : value;
}
