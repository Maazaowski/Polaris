import { test, expect } from "@playwright/test";
import { collectErrors } from "./helpers";

/**
 * "Show on PDF": a delivered row can be located on the reconstructed page.
 *
 * Needs an invoice that ran on the template path with provenance recorded
 * (anything `scripts/seed_demo.py` produced, or any template-path intake
 * processed after provenance.json existed). Skips cleanly otherwise rather
 * than failing on data the stack does not have.
 */
test("a delivered row can be located on the PDF", async ({ page, request }) => {
  const list = await request.get("/api/v1/invoices?page=1&per_page=50&extraction_path=model&status=completed");
  expect(list.ok()).toBeTruthy();
  const items: Array<{ id: string }> = (await list.json()).items ?? [];

  let target: string | null = null;
  for (const item of items) {
    const prov = await request.get(`/api/v1/invoices/${item.id}/provenance`);
    if (prov.ok() && (await prov.json()).available) {
      target = item.id;
      break;
    }
  }
  test.skip(target === null, "no template-path invoice with provenance in this stack");

  const errors = collectErrors(page);
  await page.goto(`/invoices/${target}`);

  const toggle = page.getByRole("button", { name: /show on pdf/i });
  await expect(toggle).toBeEnabled();

  // Every delivered row has an accessible locate control.
  const locate = page.getByRole("button", { name: /show row 1 on the pdf/i });
  await expect(locate).toBeVisible();
  await locate.click();

  const panel = page.getByTestId("provenance-panel");
  await expect(panel).toBeVisible();
  await expect(panel.getByText(/page \d+ of \d+/i)).toBeVisible();
  // The selected row is outlined on the canvas.
  await expect(panel.getByTestId("provenance-box-focus").first()).toBeVisible();
  await expect(locate).toHaveAttribute("aria-pressed", "true");

  // Header fields are reachable too and switch the highlight.
  const headerChip = panel.getByRole("group", { name: /header fields/i }).getByRole("button").first();
  await headerChip.click();
  await expect(headerChip).toHaveAttribute("aria-pressed", "true");

  // Keyboard paging is labelled.
  await expect(panel.getByRole("button", { name: "Next page" })).toBeVisible();

  expect(errors, errors.join("\n")).toEqual([]);
});
