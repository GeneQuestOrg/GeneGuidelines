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
