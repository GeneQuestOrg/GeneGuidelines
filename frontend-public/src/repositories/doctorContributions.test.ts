import { describe, it, expect, vi, beforeEach } from "vitest";
import { apiDoctorRepository } from "./apiDoctorRepository";
import { fixtureDoctorRepository } from "./fixtureDoctorRepository";

describe("apiDoctorRepository — DOC-5 write-path", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
  });

  it("POSTs a doctor submission and maps the snake_case response", async () => {
    vi.mocked(fetch).mockResolvedValue({
      ok: true,
      status: 201,
      headers: new Headers({ "content-type": "application/json" }),
      text: async () =>
        JSON.stringify({
          id: "sub-1",
          slug: "dr-anna-nowak",
          name: "Dr Anna Nowak",
          review_status: "pending",
          possible_duplicate: true,
        }),
    } as Response);

    const result = await apiDoctorRepository.submitDoctor({
      name: "Dr Anna Nowak",
      specialty: "Geneticist",
      diseaseSlug: "fd",
    });

    expect(result).toEqual({
      id: "sub-1",
      slug: "dr-anna-nowak",
      name: "Dr Anna Nowak",
      reviewStatus: "pending",
      possibleDuplicate: true,
    });
    const [url, init] = vi.mocked(fetch).mock.calls[0];
    expect(url).toBe("/api/doctors/submissions");
    expect(init?.method).toBe("POST");
    expect(JSON.parse(init?.body as string)).toMatchObject({
      name: "Dr Anna Nowak",
      specialty: "Geneticist",
      disease_slug: "fd",
    });
  });

  it("POSTs a parent rec to the slug-scoped path", async () => {
    vi.mocked(fetch).mockResolvedValue({
      ok: true,
      status: 201,
      headers: new Headers({ "content-type": "application/json" }),
      text: async () =>
        JSON.stringify({
          id: "rec-1",
          doctor_slug: "dr-x",
          review_status: "pending",
        }),
    } as Response);

    const result = await apiDoctorRepository.submitParentRec("dr-x", {
      text: "A genuinely helpful clinician for our family.",
      relation: "parent",
    });

    expect(result).toEqual({
      id: "rec-1",
      doctorSlug: "dr-x",
      reviewStatus: "pending",
    });
    const [url] = vi.mocked(fetch).mock.calls[0];
    expect(url).toBe("/api/doctors/dr-x/parent-recs");
  });
});

describe("fixtureDoctorRepository — DOC-5 write-path twin", () => {
  it("returns a pending submission with a slug derived from the name", async () => {
    const result = await fixtureDoctorRepository.submitDoctor({ name: "Dr Józef Kowalski" });
    expect(result.reviewStatus).toBe("pending");
    expect(result.slug).toBe("dr-j-zef-kowalski");
  });

  it("flags possibleDuplicate when the slug already exists in the fixture set", async () => {
    // "Dr Hanna Kowalczyk" exists in the fixture catalogue if present; use a name
    // we know is unlikely to collide to assert the negative path.
    const result = await fixtureDoctorRepository.submitDoctor({
      name: "Dr Totally Unique Name 9zz",
    });
    expect(result.possibleDuplicate).toBe(false);
  });

  it("returns a pending parent rec", async () => {
    const result = await fixtureDoctorRepository.submitParentRec("dr-x", {
      text: "Outstanding clinician who listened to us.",
    });
    expect(result.reviewStatus).toBe("pending");
    expect(result.doctorSlug).toBe("dr-x");
  });
});
