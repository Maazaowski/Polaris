import { test, expect, type APIRequestContext } from "@playwright/test";
import path from "node:path";
import { collectErrors, unnamedControls } from "./helpers";

/**
 * A supplier profile owns its own contract: the fields its invoices are read
 * for and the columns it delivers. Both start empty, nothing is assumed, and
 * the profile cannot run until both exist.
 */

const CORPUS_PDF = path.resolve(
  __dirname,
  "../../tests/fixtures/corpus/colt.standard/invoices/676198608_20240201.pdf",
);

function uniqueId(prefix: string): string {
  return `${prefix}.${Date.now().toString(36)}`;
}

async function deleteProfile(request: APIRequestContext, profileId: string) {
  await request.delete(`/api/v1/profiles/${profileId}`);
}

test.describe("profile contract", () => {
  test("a new supplier starts with nothing to read and nothing to deliver", async ({ page, request }) => {
    const errors = collectErrors(page);
    const profileId = uniqueId("e2e.contract");
    await page.goto("/profiles/new");

    await expect(page.getByText(/2\. fields to read/i)).toBeVisible();
    await expect(page.getByText(/3\. delivered columns/i)).toBeVisible();
    await expect(page.getByText(/nothing is read yet/i)).toBeVisible();
    await expect(page.getByText(/no columns yet/i)).toBeVisible();
    // The registries are gone from the editor.
    await expect(page.getByText(/output spec/i)).toHaveCount(0);
    await expect(page.getByText(/field schema/i)).toHaveCount(0);

    await page.locator('label:has-text("Profile ID") + input').fill(profileId);
    await page.locator('label:has-text("Source / Supplier Name") + input').fill("Contract Test Supplier");
    await page.getByRole("button", { name: /^save$/i }).click();
    await expect(page.getByText(/profile created/i)).toBeVisible();

    try {
      const saved = await request.get(`/api/v1/profiles/${profileId}`);
      expect(saved.ok()).toBeTruthy();
      const body = await saved.json();
      expect(body.fields).toEqual([]);
      expect(body.output_columns).toEqual([]);
      expect(body).not.toHaveProperty("output_spec_id");

      // Moving it into training is refused and says exactly why.
      const activate = await request.post(`/api/v1/profiles/${profileId}/start-training`);
      expect(activate.status()).toBe(422);
      const issues: string[] = (await activate.json()).detail.issues;
      expect(issues).toContain("No fields to read are configured; add at least one field");
      expect(issues).toContain("No output columns are configured; add at least one delivered column");
      expect(errors).toEqual([]);
    } finally {
      await deleteProfile(request, profileId);
    }
  });

  test("picking fields and adding columns from the editor unblocks the profile", async ({ page, request }) => {
    const errors = collectErrors(page);
    const profileId = uniqueId("e2e.contract");
    await page.goto("/profiles/new");
    await page.locator('label:has-text("Profile ID") + input').fill(profileId);
    await page.locator('label:has-text("Source / Supplier Name") + input').fill("Contract Test Supplier");

    // Three catalogue picks: two document fields and the row amount is always
    // on, so pick service_id as the delivered row identifier.
    for (const name of ["invoice number", "invoice date", "service id"]) {
      await page.getByRole("button", { name: /^add field$/i }).click();
      const search = page.getByLabel(/search the field catalogue/i);
      await search.fill(name);
      await page.getByRole("button", { name: new RegExp(`^${name}\\b`, "i") }).first().click();
      await page.getByRole("button", { name: /close field picker/i }).click();
    }
    await expect(page.getByText("Invoice Number", { exact: true })).toBeVisible();
    // A date pick asks for the printed format.
    await page.getByLabel(/printed date format/i).fill("%d/%m/%Y");

    // Two delivered columns.
    await page.getByRole("button", { name: /^add column$/i }).click();
    await page.getByLabel(/header for column 1/i).fill("INVOICE_NUMBER");
    await page.getByLabel(/^source$/i).first().click();
    await page.getByRole("option", { name: /invoice number · document/i }).click();
    await page.getByRole("button", { name: /^add column$/i }).click();
    await page.getByLabel(/header for column 2/i).fill("SERVICE");
    await page.getByLabel(/^source$/i).nth(1).click();
    await page.getByRole("option", { name: /service id · row/i }).click();

    expect(await unnamedControls(page)).toEqual([]);

    await page.getByRole("button", { name: /^save$/i }).click();
    await expect(page.getByText(/profile created/i)).toBeVisible();

    try {
      const saved = await request.get(`/api/v1/profiles/${profileId}`);
      const body = await saved.json();
      expect(body.fields.map((f: { name: string }) => f.name)).toEqual(
        expect.arrayContaining(["invoice_number", "invoice_date", "service_id"]),
      );
      expect(body.fields.find((f: { name: string }) => f.name === "invoice_date").date_format).toBe("%d/%m/%Y");
      expect(body.output_columns.map((c: { header: string; source: string }) => [c.header, c.source])).toEqual([
        ["INVOICE_NUMBER", "field.invoice_number"],
        ["SERVICE", "row.service_id"],
      ]);

      // The contract no longer blocks; only the delivery folders do.
      const activate = await request.post(`/api/v1/profiles/${profileId}/start-training`);
      expect(activate.status()).toBe(422);
      const issues: string[] = (await activate.json()).detail.issues;
      expect(issues.filter((i) => /fields to read|output columns|date format|amount role/i.test(i))).toEqual([]);
      expect(issues.some((i) => /delivery account/i.test(i))).toBeTruthy();
      expect(errors).toEqual([]);
    } finally {
      await deleteProfile(request, profileId);
    }
  });

  test("the builder's Output tab inherits the profile's columns until customised", async ({ page, request }) => {
    const profileId = uniqueId("e2e.contract");
    const created = await request.post("/api/v1/profiles", {
      data: {
        profile_id: profileId,
        identity: { canonical_name: "Builder Contract Supplier", aliases: [] },
        fields: [{ name: "invoice_number", scope: "document" }, { name: "service_id", scope: "row" }],
        output_columns: [
          { header: "ID", source: "row.service_id" },
          { header: "NUMBER", source: "field.invoice_number" },
        ],
      },
    });
    expect(created.ok(), await created.text()).toBeTruthy();

    try {
      const errors = collectErrors(page);
      await page.goto(`/models/builder?profileId=${encodeURIComponent(profileId)}`);
      await page.locator('input[type="file"]').setInputFiles(CORPUS_PDF);
      await expect(page.getByText(/676198608_20240201\.pdf/)).toBeVisible();
      await page.getByRole("button", { name: /start building/i }).click();

      await page.getByRole("tab", { name: /^output$/i }).click();
      await expect(page.getByText(/inheriting/i)).toBeVisible();
      await expect(page.getByText("ID, NUMBER")).toBeVisible();
      await page.getByRole("button", { name: /customise for this template/i }).click();
      await expect(page.getByLabel(/header for column 1/i)).toHaveValue("ID");
      await expect(page.getByLabel(/header for column 2/i)).toHaveValue("NUMBER");

      // The dry-run reports where its columns came from.
      await page.getByRole("button", { name: /run all/i }).click();
      await expect(page.getByText(/template columns/i)).toBeVisible();
      await page.getByRole("button", { name: /back to the profile's columns/i }).click();
      await expect(page.getByText(/inheriting/i)).toBeVisible();
      expect(errors).toEqual([]);
    } finally {
      await deleteProfile(request, profileId);
    }
  });

  test("the field catalogue is served read-only", async ({ request }) => {
    const res = await request.get("/api/v1/profiles/field-catalogue");
    expect(res.ok()).toBeTruthy();
    const body = await res.json();
    expect(body.fields.length).toBeGreaterThan(30);
    expect(body.computed_sources).toEqual(["computed.line_tax"]);
    expect(body.fields.find((f: { name: string; scope: string }) => f.name === "amount" && f.scope === "row").always_on).toBe(true);
  });
});
