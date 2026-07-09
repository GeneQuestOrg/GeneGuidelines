import { beforeEach, describe, expect, it, vi } from "vitest";
import { apiAccountRepository } from "./apiAccountRepository";

function jsonResponse(body: unknown, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    headers: new Headers({ "content-type": "application/json" }),
    text: async () => JSON.stringify(body),
    json: async () => body,
  } as Response;
}

describe("apiAccountRepository invites + ORCID", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
  });

  it("createInvite posts snake_case and maps the response to camelCase", async () => {
    vi.mocked(fetch).mockResolvedValue(
      jsonResponse(
        { token: "tok-1", url_path: "/join/tok-1", expires_at: "2026-07-12T00:00:00Z" },
        201,
      ),
    );
    const invite = await apiAccountRepository.createInvite({ doctorSlug: "dr-x" });
    expect(invite).toEqual({
      token: "tok-1",
      urlPath: "/join/tok-1",
      expiresAt: "2026-07-12T00:00:00Z",
    });
    const [, init] = vi.mocked(fetch).mock.calls[0];
    expect(init?.method).toBe("POST");
    expect(JSON.parse(init?.body as string)).toEqual({
      email: null,
      doctor_slug: "dr-x",
    });
  });

  it("getInvitePreview maps the public preview", async () => {
    vi.mocked(fetch).mockResolvedValue(
      jsonResponse({
        intended_role: "doctor",
        inviter_display: "p***@example.com",
        doctor_slug: null,
        expired: false,
        used: false,
      }),
    );
    const preview = await apiAccountRepository.getInvitePreview("tok-1");
    expect(preview).toEqual({
      intendedRole: "doctor",
      inviterDisplay: "p***@example.com",
      doctorSlug: null,
      expired: false,
      used: false,
    });
    expect(vi.mocked(fetch).mock.calls[0][0]).toBe("/api/account/invites/tok-1");
  });

  it("orcidEnabled reads the status flag", async () => {
    vi.mocked(fetch).mockResolvedValue(jsonResponse({ enabled: true }));
    expect(await apiAccountRepository.orcidEnabled()).toBe(true);
  });

  it("orcidLoginUrl returns the authorize URL", async () => {
    vi.mocked(fetch).mockResolvedValue(
      jsonResponse({ authorize_url: "https://orcid.org/oauth/authorize?x=1" }),
    );
    expect(await apiAccountRepository.orcidLoginUrl()).toBe(
      "https://orcid.org/oauth/authorize?x=1",
    );
  });
});

describe("apiAccountRepository verification requests", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
  });

  it("submitVerificationRequest posts snake_case and maps the response", async () => {
    vi.mocked(fetch).mockResolvedValue(
      jsonResponse(
        {
          id: "vr-1",
          user_id: "u-1",
          role: "researcher",
          orcid: "0000-0002-1825-0097",
          license_no: null,
          institution: "Institute of X",
          note: null,
          status: "pending",
          created_at: "2026-07-09T10:00:00Z",
          updated_at: "2026-07-09T10:00:00Z",
          reviewed_by: null,
          reviewed_at: null,
          user_email: null,
        },
        201,
      ),
    );
    const created = await apiAccountRepository.submitVerificationRequest({
      orcid: "0000-0002-1825-0097",
      institution: "Institute of X",
    });
    expect(created).toEqual({
      id: "vr-1",
      userId: "u-1",
      role: "researcher",
      orcid: "0000-0002-1825-0097",
      licenseNo: null,
      institution: "Institute of X",
      note: null,
      status: "pending",
      createdAt: "2026-07-09T10:00:00Z",
      updatedAt: "2026-07-09T10:00:00Z",
      reviewedBy: null,
      reviewedAt: null,
      userEmail: null,
    });
    const [url, init] = vi.mocked(fetch).mock.calls[0];
    expect(url).toBe("/api/account/verification-requests");
    expect(init?.method).toBe("POST");
    expect(JSON.parse(init?.body as string)).toEqual({
      orcid: "0000-0002-1825-0097",
      license_no: null,
      institution: "Institute of X",
      note: null,
    });
  });

  it("myVerificationRequests maps a list of requests", async () => {
    vi.mocked(fetch).mockResolvedValue(
      jsonResponse([
        {
          id: "vr-2",
          user_id: "u-1",
          role: "doctor",
          orcid: null,
          license_no: "LIC-99",
          institution: null,
          note: "Please verify.",
          status: "pending",
          created_at: "2026-07-09T11:00:00Z",
          updated_at: "2026-07-09T11:00:00Z",
          reviewed_by: null,
          reviewed_at: null,
          user_email: null,
        },
      ]),
    );
    const mine = await apiAccountRepository.myVerificationRequests();
    expect(mine).toHaveLength(1);
    expect(mine[0]).toMatchObject({
      id: "vr-2",
      role: "doctor",
      licenseNo: "LIC-99",
      note: "Please verify.",
      status: "pending",
    });
    expect(vi.mocked(fetch).mock.calls[0][0]).toBe(
      "/api/account/verification-requests/mine",
    );
  });

  it("surfaces a 409 as an ApiRequestError with the backend detail", async () => {
    vi.mocked(fetch).mockResolvedValue(
      jsonResponse(
        { detail: "You already have a verification request under review." },
        409,
      ),
    );
    await expect(
      apiAccountRepository.submitVerificationRequest({ note: "again" }),
    ).rejects.toMatchObject({
      status: 409,
      message: expect.stringContaining("already have a verification request"),
    });
  });
});
