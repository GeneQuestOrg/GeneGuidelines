import { expect, test } from "@playwright/test";

test.describe("public home → disease flow", () => {
  test("navigates to FD, toggles persona, shows tabs", async ({ page }) => {
    await page.goto("/");

    await expect(page.getByRole("heading", { level: 1 })).toContainText(/families|guidelines/i);

    const fdCard = page.getByRole("link", { name: /Fibrous Dysplasia/i });
    await expect(fdCard).toBeVisible();
    await fdCard.click();

    await expect(page).toHaveURL(/\/diseases\/fd/);

    // Parent view: the orientation map leads, the printable list of tests follows,
    // the AI summary is one card away, and the page ends with the unusual-case contact.
    await expect(page.getByRole("heading", { level: 1 })).toContainText(/first week/i);
    await expect(
      page.getByRole("heading", { level: 2, name: /Baseline evaluation in FD\/MAS/i }),
    ).toBeVisible();
    await expect(page.getByRole("button", { name: /guideline synthesis/i })).toBeVisible();
    await expect(page.getByRole("link", { name: /Write to us/i })).toHaveAttribute(
      "href",
      /^mailto:kontakt@genequest\.org/,
    );

    const personaGroup = page.getByRole("radiogroup", { name: /You are reading as/i });
    await expect(personaGroup).toBeVisible();

    const clinicianOption = personaGroup.getByRole("radio", { name: /Clinician/i });
    await clinicianOption.click();
    await expect(clinicianOption).toHaveAttribute("aria-checked", "true");

    // Clinician view: the data hub, unchanged.
    await expect(page.getByRole("heading", { level: 1, name: "Fibrous Dysplasia" })).toBeVisible();

    const tabList = page.getByRole("tablist", { name: /Disease sections/i });
    await expect(tabList).toBeVisible();
    await expect(tabList.getByRole("tab", { name: /Overview/i })).toBeVisible();
    await expect(tabList.getByRole("tab", { name: /Specialists|Experts/i })).toBeVisible();
    await expect(tabList.getByRole("tab", { name: /Clinical trials|Trials/i })).toBeVisible();
    await expect(tabList.getByRole("tab", { name: /Guidelines|Guideline/i })).toBeVisible();
  });
});
