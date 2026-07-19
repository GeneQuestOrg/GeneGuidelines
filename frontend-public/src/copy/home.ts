import type { HomeCopy } from "./types";

/*
 * ═══════════════════════════════════════════════════════════════════════════
 *  HERO WARIANTY (3) — default = WARIANT A (below). Swap `titleLine1` /
 *  `titleEmphasis` / `subtitle` for B or C to change the hero.
 * ───────────────────────────────────────────────────────────────────────────
 *  WARIANT A — „jedno miejsce, żeby zacząć"  ◀ DEFAULT
 *    H1:  Rzadka choroba. / Jedno miejsce, żeby zacząć.
 *    Sub: Znajdź w jednym miejscu wszystko, co już wiadomo o Twojej chorobie: …
 *
 *  WARIANT B — „mapa, nie szukanie po omacku"
 *    H1:  Rzadka choroba w rodzinie? / Zacznij od mapy, nie od szukania po omacku.
 *    Sub: Najtrudniejsze na początku nie jest to, że brakuje odpowiedzi — tylko
 *         to, że nie wiadomo, o co pytać. Pokazujemy, co istnieje i co z tym
 *         zrobić: wytyczne ze źródłami, lekarzy znających tę chorobę, badania
 *         kliniczne i fundacje — w jednym miejscu.
 *
 *  WARIANT C — „wiedza istnieje, niech dotrze na czas"
 *    H1:  Wiedza o tej chorobie już istnieje. / Pomożemy jej dotrzeć na czas.
 *    Sub: Wytyczne, specjaliści i badania kliniczne dla rzadkich chorób
 *         genetycznych — zebrane i napisane tak, żeby to, co już wiadomo,
 *         trafiło do rodziny i lekarza wtedy, kiedy zapadają decyzje.
 *         Z podanymi źródłami, do omówienia z lekarzem.
 * ═══════════════════════════════════════════════════════════════════════════
 */
export const homeCopy: HomeCopy = {
  eyebrow: "Rzadkie choroby genetyczne · dla rodzin i lekarzy",
  titleLine1: "Rzadka choroba.",
  titleEmphasis: "Jedno miejsce, żeby zacząć.",
  subtitle:
    "Znajdź w jednym miejscu wszystko, co już wiadomo o Twojej chorobie: " +
    "wytyczne prostym językiem i ze źródłami, lekarzy, którzy naprawdę ją znają, " +
    "oraz badania kliniczne. Zebrane tak, żeby ta wiedza dotarła do rodziny i lekarza na czas.",

  knowKicker: "Znam chorobę",
  knowTitle: "Wiem, czego szukam",
  knowDesc:
    "Przejdź prosto na stronę choroby — mapa „co robić” krok po kroku (co sprawdzić, " +
    "jakich lekarzy szukać, o co zapytać na wizycie), a obok wytyczne, badania i fundacje.",
  searchPlaceholder: "np. dysplazja włóknista, fibrous dysplasia, MAS, GNAS…",
  searchHint:
    "Szukaj po polsku, po łacinie, po nazwie genu lub po objawie — pisownia i literówki niestraszne.",

  dontKicker: "Nie znam diagnozy",
  dontBadge: "Publiczna beta",
  dontTitle: "Nie wiem, od czego zacząć",
  dontDescLead:
    "Masz tylko objaw albo wynik badania genetycznego? Wpisz, co masz — pokażemy " +
    "możliwe kierunki i z jakim specjalistą porozmawiać. ",
  dontDescEmph: "Z cytowaniami, bez diagnozy.",
  symptomPlaceholder: "np. plamy café-au-lait  ·  albo  GNAS c.601C>T",
  symptomExamples: [
    { label: "Objaw", hint: "plamy café-au-lait" },
    { label: "Wariant", hint: "GNAS c.601C>T" },
  ],
  dontCta: "Rozpocznij orientację",

  findsTitle: "Co tu znajdziesz",
  findsSub:
    "W jednym miejscu, dla dowolnej rzadkiej choroby — a jeśli Twojej jeszcze u nas " +
    "nie ma, możesz ją zlecić do researchu.",
  finds: [
    {
      title: "Wytyczne prostym językiem — i pełne do druku",
      body:
        "Krótkie, zrozumiałe streszczenie tego, co wiadomo o chorobie — przy każdym " +
        "zdaniu link do źródła, z którego pochodzi. Obok pełne, oryginalne dokumenty " +
        "do wydrukowania i pokazania lekarzowi.",
    },
    {
      title: "Lekarze z doświadczeniem w tej chorobie",
      body:
        "Choroba rzadka jest rzadka — nawet znakomity specjalista mógł nigdy jej nie " +
        "widzieć. To nie kwestia kompetencji, tylko skali: pomagamy znaleźć tych " +
        "niewielu, którzy mają z nią praktyczne doświadczenie, i sortujemy ich według " +
        "odległości od Ciebie.",
    },
    {
      title: "Terapie i badania kliniczne — także za granicą",
      body:
        "Również te, których w Polsce się nie refunduje, a prowadzone są w ośrodkach " +
        "za granicą — czasem właśnie one dają realną szansę. Pokazujemy, co aktualnie " +
        "się rekrutuje i gdzie.",
    },
    {
      title: "Fundacje, które mogą pomóc",
      body:
        "Wsparcie, które przy takich diagnozach potrafi wiele zmienić — organizacje " +
        "pacjenckie i fundacje zajmujące się daną chorobą.",
    },
  ],
  honestFootnote:
    "Uczciwie: to AI-owy skrót oficjalnych wytycznych i literatury (z odnośnikami do " +
    "źródeł) — nie oficjalna wytyczna i nikt się pod nim oficjalnie nie podpisuje; " +
    "lekarze mogą go oceniać i zgłaszać uwagi. Materiał informacyjny, nie diagnoza.",
  honestLinkLabel: "Dlaczego to robimy",

  diseasesSectionTitle: "Ostatnio dodane",
  diseasesSectionSub:
    "To nie cały katalog — najnowsze choroby, które przeszły przez nasz research. " +
    "Każdą inną zlecisz w minutę.",

  newDiseaseEyebrow: "Dla dowolnej rzadkiej choroby",
  newDiseaseTitle: "Twojej choroby tu nie ma?",
  newDiseaseSub:
    "Zleć research AI — pipeline przeszuka PubMed oraz internet, znajdzie lekarzy " +
    "i badania. Pierwsze wyniki w ~10 minut.",
  newDiseaseCta: "Zleć research AI",

  addTitle: "Nie ma Twojej choroby? Możesz ją dodać.",
  addSub:
    "Zleć research AI dla dowolnej rzadkiej choroby — jeśli nie ma jej w bazie, " +
    "pipeline przeszuka PubMed i internet i ją doda. Brakuje jakiejś informacji " +
    "albo funkcji? Też napisz.",
  addPlaceholder: "np. zespół Retta…",
  addCta: "Zleć research",
};
