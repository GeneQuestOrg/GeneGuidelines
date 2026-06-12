import { describe, expect, it } from "vitest";
import { fixtureAccountRepository } from "./fixtureAccountRepository";

describe("fixtureAccountRepository invites", () => {
  it("mints a join URL path and round-trips a preview", async () => {
    const invite = await fixtureAccountRepository.createInvite({
      doctorSlug: "dr-dowgierd",
    });
    expect(invite.urlPath).toBe(`/join/${invite.token}`);
    expect(invite.expiresAt).toMatch(/\dT\d/); // ISO timestamp

    const preview = await fixtureAccountRepository.getInvitePreview(invite.token);
    expect(preview.intendedRole).toBe("doctor");
    expect(preview.doctorSlug).toBe("dr-dowgierd");
    expect(preview.used).toBe(false);
    expect(preview.expired).toBe(false);
  });

  it("accept marks the invite used and sets the doctor role unverified", async () => {
    const invite = await fixtureAccountRepository.createInvite();
    const me = await fixtureAccountRepository.acceptInvite(invite.token);
    expect(me.role).toBe("doctor");
    expect(me.verified).toBe(false);

    const preview = await fixtureAccountRepository.getInvitePreview(invite.token);
    expect(preview.used).toBe(true);
  });

  it("reports ORCID disabled in fixture mode", async () => {
    expect(await fixtureAccountRepository.orcidEnabled()).toBe(false);
  });
});
