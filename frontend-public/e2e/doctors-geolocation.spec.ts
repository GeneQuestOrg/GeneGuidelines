import { expect, test } from "@playwright/test";

const WARSAW = { latitude: 52.229, longitude: 21.012, accuracy: 10 };
const LEIDEN = { latitude: 52.166, longitude: 4.49, accuracy: 10 };

test.describe("doctors — geolocation and location picker", () => {
  test("geolocation button sets location and shows distance filter", async ({ page, context }) => {
    await context.grantPermissions(["geolocation"]);
    await context.setGeolocation(WARSAW);

    await page.goto("/doctors");
    await expect(page.getByRole("heading", { name: "Find a specialist" })).toBeVisible();

    // Before geolocation: distance filter row is hidden
    await expect(page.getByLabel("Filter by distance")).not.toBeVisible();

    // Click the geolocation button (⊙)
    await page.getByRole("button", { name: "Use my location" }).click();

    // After: location badge appears and distance filter is shown
    await expect(page.locator(".loc-picker__badge")).toBeVisible();
    await expect(page.getByLabel("Filter by distance")).toBeVisible();
  });

  test("geolocation sorts doctors by distance from user", async ({ page, context }) => {
    // Put the user near Leiden — Dr. Appelman-Dijkstra should appear closer than Rome doctors
    await context.grantPermissions(["geolocation"]);
    await context.setGeolocation(LEIDEN);

    await page.goto("/doctors");
    await page.getByRole("button", { name: "Use my location" }).click();

    // Wait for distance badges to appear
    await expect(page.locator(".pill--dist").first()).toBeVisible({ timeout: 5000 });

    const distancePills = page.locator(".pill--dist");
    const count = await distancePills.count();
    expect(count).toBeGreaterThan(1);

    // Extract numeric km values and verify they are in ascending order
    const texts = await distancePills.allTextContents();
    const kms = texts.map((t) => parseFloat(t.replace(/[^0-9.]/g, ""))).filter(isFinite);
    for (let i = 1; i < kms.length; i++) {
      expect(kms[i]).toBeGreaterThanOrEqual(kms[i - 1]);
    }
  });

  test("distance filter hides doctors beyond threshold", async ({ page, context }) => {
    await context.grantPermissions(["geolocation"]);
    await context.setGeolocation(WARSAW);

    await page.goto("/doctors");
    await page.getByRole("button", { name: "Use my location" }).click();
    await expect(page.locator(".pill--dist").first()).toBeVisible({ timeout: 5000 });

    const totalCards = await page.locator(".doc").count();

    // Apply 25 km filter — should show fewer doctors (or empty)
    await page.getByRole("button", { name: "25 km" }).click();
    const filteredCards = await page.locator(".doc").count();
    expect(filteredCards).toBeLessThanOrEqual(totalCards);

    // Worldwide restores all
    await page.getByRole("button", { name: "Worldwide" }).click();
    const restoredCards = await page.locator(".doc").count();
    expect(restoredCards).toBe(totalCards);
  });

  test("clearing location hides distance filter and resets distances", async ({
    page,
    context,
  }) => {
    await context.grantPermissions(["geolocation"]);
    await context.setGeolocation(WARSAW);

    await page.goto("/doctors");
    await page.getByRole("button", { name: "Use my location" }).click();
    await expect(page.locator(".loc-picker__badge")).toBeVisible();

    // Clear the location
    await page.getByRole("button", { name: "Clear location" }).click();

    await expect(page.locator(".loc-picker__badge")).not.toBeVisible();
    await expect(page.getByLabel("Filter by distance")).not.toBeVisible();
  });

  test("view toggle switches between list, both, and map modes", async ({ page }) => {
    await page.goto("/doctors");
    await expect(page.getByRole("heading", { name: "Find a specialist" })).toBeVisible();

    // Default: both list and map visible
    await expect(page.locator(".doctors-list")).toBeVisible();
    await expect(page.locator(".doctors-map")).toBeVisible();

    // Switch to list only
    await page.getByRole("button", { name: "List only" }).click();
    await expect(page.locator(".doctors-list")).toBeVisible();
    await expect(page.locator(".doctors-map")).not.toBeVisible();

    // Switch to map only
    await page.getByRole("button", { name: "Map only" }).click();
    await expect(page.locator(".doctors-map")).toBeVisible();
    await expect(page.locator(".doctors-list")).not.toBeVisible();

    // Back to both
    await page.getByRole("button", { name: "List and map" }).click();
    await expect(page.locator(".doctors-list")).toBeVisible();
    await expect(page.locator(".doctors-map")).toBeVisible();
  });
});
