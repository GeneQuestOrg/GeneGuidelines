import { describe, expect, it } from "vitest";
import { doctorEvidenceLine } from "../utils/doctorLabels";

/**
 * The per-disease list is headed "Specialists" / "Specjaliści". An audit of the FD
 * list found that of 15 Polish entries, none had more than one FD paper, 5 were
 * middle authors, and 9 came from just two case reports — every record technically
 * true, and the heading turning each into a claim the data does not support.
 *
 * The weight of evidence was already in the payload and simply never rendered. This
 * puts it beside the name so a family can judge it, rather than trusting a heading.
 */

const t = (key: string, opts?: Record<string, unknown>) => {
  if (key === "doctorCard.paperCount") return `${opts?.count} papers`;
  if (key.startsWith("doctorCard.authorPosition.")) return key.split(".").pop() as string;
  return key;
};

describe("doctor evidence line", () => {
  it("shows count, position and the most recent year", () => {
    const line = doctorEvidenceLine(
      { publications: [{ year: 2017, position: "middle" }] },
      t,
    );

    expect(line).toBe("1 papers · middle · 2017");
  });

  it("reports the strongest authorship position across a mixed record", () => {
    const line = doctorEvidenceLine(
      { publications: [{ year: 2011, position: "middle" }, { year: 2019, position: "first" }] },
      t,
    );

    expect(line).toContain("first");
    expect(line).toContain("2019");
  });

  it("prefers last author over middle when there is no first authorship", () => {
    const line = doctorEvidenceLine(
      { publications: [{ year: 2020, position: "middle" }, { year: 2020, position: "last" }] },
      t,
    );

    expect(line).toContain("last");
  });

  it("says nothing when there is nothing measured", () => {
    // Silence beats an invented zero: several seeded records carry no publications
    // at all, and "0 papers" would read as a finding rather than an absence.
    expect(doctorEvidenceLine({}, t)).toBe("");
    expect(doctorEvidenceLine({ publications: [] }, t)).toBe("");
  });

  it("omits the year rather than inventing one when it is missing", () => {
    const line = doctorEvidenceLine({ publications: [{ year: null, position: "first" }] }, t);

    expect(line).toBe("1 papers · first");
  });
});
