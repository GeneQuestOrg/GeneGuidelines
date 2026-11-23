import { describe, expect, it } from "vitest";
import { localizeInheritance, localizePrevalence } from "./diseaseFacts";

describe("disease facts in Polish", () => {
  it.each([
    ["Somatic (not inherited)", "Somatyczne (niedziedziczne)"],
    ["Somatic", "Somatyczne"],
    ["autosomal dominant", "autosomalne dominujące"],
    ["Autosomal dominant (most types)", "Autosomalne dominujące (większość typów)"],
    ["autosomal recessive", "autosomalne recesywne"],
    ["X-linked recessive", "Recesywne sprzężone z chromosomem X"],
    ["Autosomal dominant or recessive", "Autosomalne dominujące lub recesywne"],
  ])("translates the inheritance %s", (en, pl) => {
    expect(localizeInheritance(en, "pl")).toBe(pl);
  });

  it.each([
    ["Rare disease", "Choroba rzadka"],
    ["Ultra-rare (~1 in 2 million)", "Ultrarzadka (~1 na 2 mln)"],
    ["~1:16,500 diagnosed (Denmark, 2018) · true prevalence unknown", "~1:16,500 rozpoznanych (Denmark, 2018) · rzeczywista częstość nieznana"],
  ])("translates the prevalence %s", (en, pl) => {
    expect(localizePrevalence(en, "pl")).toBe(pl);
  });

  it("leaves English pages and unknown words alone", () => {
    expect(localizeInheritance("Somatic (not inherited)", "en")).toBe("Somatic (not inherited)");
    expect(localizeInheritance("Imprinting disorder", "pl")).toBe("Imprinting disorder");
  });
});
