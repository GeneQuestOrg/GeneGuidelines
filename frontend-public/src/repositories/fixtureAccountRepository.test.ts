import { describe, expect, it } from "vitest";
import { ApiRequestError } from "../api/client";
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

describe("fixtureAccountRepository verification requests", () => {
  it("keeps a researcher unverified after selecting the role", async () => {
    const me = await fixtureAccountRepository.selectRole("researcher");
    expect(me.role).toBe("researcher");
    expect(me.verified).toBe(false);
  });

  it("submits a manual request and round-trips it via mine (newest first)", async () => {
    await fixtureAccountRepository.selectRole("researcher");
    const created = await fixtureAccountRepository.submitVerificationRequest({
      institution: "  Institute of X  ",
      note: "Please verify me.",
    });
    expect(created.status).toBe("pending");
    // Whitespace is trimmed; unset fields normalise to null.
    expect(created.institution).toBe("Institute of X");
    expect(created.orcid).toBeNull();

    const mine = await fixtureAccountRepository.myVerificationRequests();
    expect(mine).toHaveLength(1);
    expect(mine[0]?.id).toBe(created.id);
  });

  it("rejects an empty submission with a 400", async () => {
    await fixtureAccountRepository.selectRole("doctor");
    await expect(
      fixtureAccountRepository.submitVerificationRequest({ note: "   " }),
    ).rejects.toBeInstanceOf(ApiRequestError);
    await expect(
      fixtureAccountRepository.submitVerificationRequest({}),
    ).rejects.toMatchObject({ status: 400 });
  });

  it("rejects a second pending request with a 409", async () => {
    await fixtureAccountRepository.selectRole("doctor");
    await fixtureAccountRepository.submitVerificationRequest({ note: "first" });
    await expect(
      fixtureAccountRepository.submitVerificationRequest({ note: "second" }),
    ).rejects.toMatchObject({ status: 409 });
  });

  it("rejects a non-verifiable role with a 403", async () => {
    await fixtureAccountRepository.selectRole("parent");
    await expect(
      fixtureAccountRepository.submitVerificationRequest({ note: "hi" }),
    ).rejects.toMatchObject({ status: 403 });
  });
});
