import { expect, test } from "@playwright/test";

test.describe("public home → disease flow", () => {
  test("opens FD: disease card, tab links, map beside the questions, tests tab", async ({ page }) => {
    await page.goto("/");

    await expect(page.getByRole("heading", { level: 1 })).toContainText(/families|guidelines/i);

    const fdCard = page.getByRole("link", { name: /Fibrous Dysplasia/i });
    await expect(fdCard).toBeVisible();
    await fdCard.click();

    await expect(page).toHaveURL(/\/diseases\/fd$/);

    // Parent / guest view: the disease card names the disease, the tabs under it are links to real addresses with the current one marked.
    await expect(page.getByRole("heading", { level: 1 })).toContainText(/Fibrous Dysplasia/i);
    const tabs = page.getByRole("navigation", { name: /Parts of this disease page/i });
    await expect(tabs.getByRole("link", { name: /^Start/ })).toHaveAttribute("aria-current", "page");
    await expect(tabs.getByRole("link", { name: /Baseline tests/ })).toHaveAttribute(
      "href",
      "/diseases/fd/tests",
    );

    // The orientation map: five cards, one button each; the buttons are the page's menu.
    await expect(page.getByRole("heading", { level: 2, name: /Five things/i })).toBeVisible();
    const map = page.locator(".dmap-mcards");
    await expect(map.getByRole("listitem")).toHaveCount(5);
    await expect(map.getByRole("link", { name: /Doctors who know FD/i })).toHaveAttribute(
      "href",
      "/doctors?disease=fd",
    );
    await expect(map.getByRole("link", { name: /Clinical trials/i })).toHaveAttribute(
      "href",
      "/trials?disease=fd",
    );

    // The questions for the doctor: closed rows headed by the question; opening one shows the summary and the guideline sentence.
    await expect(page.getByRole("heading", { level: 2, name: /Ask your doctor/i })).toBeVisible();
    const firstQuestion = page.locator("summary.dmap-ask__sum").first();
    await expect(firstQuestion).toContainText("Q1");
    await expect(page.getByText(/From the guideline \(original\)/).first()).toBeHidden();
    await firstQuestion.click();
    await expect(page.getByText(/From the guideline \(original\)/).first()).toBeVisible();

    // The list of tests is its own tab: the Start tab does not show it, only prints it.
    await expect(page.getByRole("heading", { name: /Baseline evaluation in FD\/MAS/i })).toHaveCount(0);
    await expect(page.getByRole("button", { name: /Print the list of tests/i })).toBeVisible();

    await expect(page.getByRole("link", { name: /Write to us/i })).toHaveAttribute(
      "href",
      /^mailto:kontakt@genequest\.org/,
    );

    // The tests tab: the same card and tabs, the sheet below with its own h1.
    await tabs.getByRole("link", { name: /Baseline tests/ }).click();
    await expect(page).toHaveURL(/\/diseases\/fd\/tests$/);
    await expect(
      page.getByRole("heading", { level: 1, name: /Baseline evaluation in FD\/MAS/i }),
    ).toBeVisible();
    await expect(
      page
        .getByRole("navigation", { name: /Parts of this disease page/i })
        .getByRole("link", { name: /Baseline tests/ }),
    ).toHaveAttribute("aria-current", "page");
  });
});
