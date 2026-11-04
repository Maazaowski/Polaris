/**
 * Record silent 1080p footage of the video-series scenes that changed with the
 * profile contract (docs/VIDEO_SERIES_PLAN.md, "Needs re-recording").
 *
 *   node scripts/record-episode-scenes.mjs <outDir> [scene ...]
 *
 * SCENE_NO_PROFILE_INTAKE names the intake for part2-raw-workbook.
 * Scenes: part2-raw-workbook, part3-profile-contract, part3-readiness,
 * part5-builder-output, part6-rekey. No scene names = all of them.
 *
 * Each scene is its own .webm (1920x1080, dark theme, browser at 125%) with a
 * drawn cursor, so the clips are ready for a voice-over. A few checkpoint PNGs
 * per scene land in <outDir>/checkpoints for a quick review without a player.
 *
 * Run it against the production build (`npm run build && next start`), not
 * `next dev`: dev compiles routes on first visit and shows its badge.
 * Credentials come from E2E_EMAIL / E2E_PASSWORD (`seed-e2e-user.mjs` makes
 * a throwaway admin). The demo data the scenes expect (seed_demo.py, one
 * invoice from a supplier with no profile) is listed in DEMO below.
 *
 * Some scenes save changes (part3-profile-contract edits and saves the Colt
 * profile; part3-readiness creates a profile; part6-rekey adds a summary
 * anchor to Colt's fingerprint rules). Run part6-rekey after part3-profile-contract: the Colt
 * fixture has no printed date formats, so its first save is refused until that
 * scene fills them in. `python scripts/seed_demo.py --reset` restores the demo.
 */
import { chromium } from "@playwright/test";
import { mkdirSync, renameSync } from "node:fs";
import path from "node:path";

const outDir = path.resolve(process.argv[2] || "recordings");
const wanted = process.argv.slice(3);
const base = process.env.E2E_BASE_URL || "http://localhost:3000";
const email = process.env.E2E_EMAIL;
const password = process.env.E2E_PASSWORD;
if (!email || !password) throw new Error("Set E2E_EMAIL and E2E_PASSWORD.");

const repo = path.resolve(import.meta.dirname, "..", "..");
const DEMO = {
  colt: "colt.standard.v1",
  coltSample: path.join(repo, "tests/fixtures/corpus/colt.standard/invoices/676198608_20240201.pdf"),
  coltDateFormat: "%d-%b-%Y", // Colt prints 01-Feb-2024
  coltNewAnchor: "Current Month Activity", // a summary label printed on Colt page 1
  // An intake processed with no profile (upload a PDF from a supplier that has none).
  noProfileIntake: process.env.SCENE_NO_PROFILE_INTAKE,
  newProfileId: "northwind.standard.v1",
  newProfileName: "Northwind Telecom",
};

const VIEWPORT = { width: 1536, height: 864 }; // 1920x1080 at 125%
mkdirSync(path.join(outDir, "checkpoints"), { recursive: true });

// ── Pacing helpers ─────────────────────────────────────────────────────────

const CURSOR = `
  (() => {
    const install = () => {
      if (document.getElementById("__rec_cursor")) return;
      const c = document.createElement("div");
      c.id = "__rec_cursor";
      Object.assign(c.style, {
        position: "fixed", left: "0px", top: "0px", width: "18px", height: "18px",
        marginLeft: "-9px", marginTop: "-9px", borderRadius: "50%",
        background: "rgba(255,255,255,0.85)", boxShadow: "0 0 0 2px rgba(0,0,0,0.55)",
        pointerEvents: "none", zIndex: "2147483647", transition: "transform 120ms ease",
      });
      document.documentElement.appendChild(c);
      document.addEventListener("mousemove", (e) => {
        c.style.left = e.clientX + "px";
        c.style.top = e.clientY + "px";
      }, true);
      document.addEventListener("mousedown", () => { c.style.transform = "scale(0.7)"; }, true);
      document.addEventListener("mouseup", () => { c.style.transform = "scale(1)"; }, true);
    };
    if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", install);
    else install();
  })();
`;

const beat = (page, ms = 700) => page.waitForTimeout(ms);

async function show(page, locator) {
  await locator.evaluate((el) => el.scrollIntoView({ behavior: "smooth", block: "center" }));
  await beat(page, 900);
}

async function glide(page, locator) {
  await locator.scrollIntoViewIfNeeded();
  const box = await locator.boundingBox();
  if (!box) return;
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2, { steps: 28 });
  await beat(page, 250);
}

async function click(page, locator, pause = 600) {
  await glide(page, locator);
  await locator.click();
  await beat(page, pause);
}

async function type(page, locator, text) {
  await click(page, locator, 200);
  await locator.press("Control+A");
  await locator.pressSequentially(text, { delay: 65 });
  await beat(page, 400);
}

async function pick(page, trigger, optionName) {
  await click(page, trigger, 400);
  await click(page, page.getByRole("option", { name: optionName }), 500);
}

let shot = 0;
async function checkpoint(page, scene, label) {
  shot += 1;
  const file = path.join(outDir, "checkpoints", `${scene}-${String(shot).padStart(2, "0")}-${label}.png`);
  await page.screenshot({ path: file });
}

// ── Scenes ─────────────────────────────────────────────────────────────────

const SCENES = {
  /** Part 2 closing: an invoice with no profile delivers JSON + a raw workbook. */
  async "part2-raw-workbook"(page, name) {
    if (!DEMO.noProfileIntake) throw new Error("Set SCENE_NO_PROFILE_INTAKE to a no-profile intake id.");
    await page.goto(`${base}/invoices/${DEMO.noProfileIntake}`);
    await page.getByText(/delivered rows/i).first().waitFor({ timeout: 20000 });
    await beat(page, 3000);
    await checkpoint(page, name, "detail");
    const delivered = page.getByText(/delivered rows|extracted rows|raw extraction/i).first();
    if (await delivered.count()) await show(page, delivered);
    await beat(page, 2500);
    await checkpoint(page, name, "rows");
    for (const label of [/^json$/i, /download xlsx/i]) {
      const button = page.getByRole("button", { name: label }).or(page.getByRole("link", { name: label })).first();
      if (await button.count()) {
        await glide(page, button);
        await beat(page, 1500);
      }
    }
    await beat(page, 2000);
  },

  /** Part 3: the profile owns what it reads and what it delivers. */
  async "part3-profile-contract"(page, name) {
    await page.goto(`${base}/profiles/${DEMO.colt}`);
    await page.getByText(/2\. fields to read/i).waitFor({ timeout: 20000 });
    await beat(page, 2000);
    await show(page, page.getByText(/2\. fields to read/i));
    await beat(page, 2500);
    await checkpoint(page, name, "fields");

    // A catalogue pick: type and role come from the catalogue.
    await click(page, page.getByRole("button", { name: /^add field$/i }));
    await type(page, page.getByLabel(/search the field catalogue/i), "billing period");
    await beat(page, 1200);
    await checkpoint(page, name, "catalogue");
    await click(page, page.locator("button", { hasText: "Billing Period Start" }).filter({ hasText: "row ·" }).first(), 900);
    await click(page, page.getByRole("button", { name: /close field picker/i }), 900);

    // A custom field the catalogue does not know.
    await click(page, page.getByRole("button", { name: /^custom field$/i }));
    await type(page, page.locator("#custom-field-name"), "cost_centre");
    await pick(page, page.locator("#custom-field-scope"), /row \(once per line item\)/i);
    await type(page, page.locator("#custom-field-description"), "Cost centre printed on each line");
    await checkpoint(page, name, "custom");
    await click(page, page.getByRole("button", { name: /^add custom field$/i }), 1200);

    // Delivered columns: point two new columns at the new fields, reorder one.
    await show(page, page.getByText(/3\. delivered columns/i));
    await beat(page, 1500);
    const n = await page.getByLabel(/^header for column \d+$/i).count();
    await click(page, page.getByRole("button", { name: /^add column$/i }));
    await type(page, page.getByLabel(new RegExp(`^header for column ${n + 1}$`, "i")), "PERIOD_START");
    await pick(page, page.locator(`#column-${n}-source`), /billing period start · row/i);
    await click(page, page.getByRole("button", { name: /^add column$/i }));
    await type(page, page.getByLabel(new RegExp(`^header for column ${n + 2}$`, "i")), "COST_CENTRE");
    await pick(page, page.locator(`#column-${n + 1}-source`), /cost centre · row/i);
    await click(page, page.getByRole("button", { name: new RegExp(`^move column ${n + 2} up$`, "i") }), 1200);
    await checkpoint(page, name, "columns");

    // A delivered date needs its printed format. The Colt fixture has none, so
    // the first save is refused with the list of date fields: show that, fill
    // the formats, save again.
    const save = page.getByRole("button", { name: /^save$/i });
    await click(page, save, 600);
    const refusal = page.getByText(/requires an explicit printed date format/i).first();
    if (await refusal.waitFor({ timeout: 6000 }).then(() => true).catch(() => false)) {
      await beat(page, 3500);
      await checkpoint(page, name, "refused");
    }
    for (const key of ["document.invoice_date", "document.due_date", "row.billing_period_start"]) {
      const input = page.locator(`[id="date-${key}"]`);
      if ((await input.count()) && !(await input.inputValue())) {
        await show(page, input);
        await type(page, input, DEMO.coltDateFormat);
      }
    }
    await page.evaluate(() => window.scrollTo({ top: 0, behavior: "smooth" }));
    await beat(page, 900);
    await click(page, save, 600);
    await page.getByText(/profile updated/i).first().waitFor({ timeout: 30000 });
    await beat(page, 3000);
    await checkpoint(page, name, "saved");

    // Preview Output: the same invoice, delivered with the new columns.
    await page.evaluate(() => window.scrollTo({ top: 0, behavior: "smooth" }));
    await beat(page, 900);
    await click(page, page.getByRole("tab", { name: /preview output/i }), 1200);
    const upload = page.getByRole("button", { name: /upload a sample pdf/i });
    await glide(page, upload);
    const chooser = page.waitForEvent("filechooser");
    await upload.click();
    await (await chooser).setFiles(DEMO.coltSample);
    await page.getByText("COST_CENTRE", { exact: true }).last().waitFor({ timeout: 240000 });
    await beat(page, 1200);
    await show(page, page.getByText("PERIOD_START", { exact: true }).last());
    await beat(page, 3500);
    await checkpoint(page, name, "preview");
  },

  /** Parts 3 and 4: a new profile starts empty and cannot train until configured. */
  async "part3-readiness"(page, name) {
    await page.goto(`${base}/profiles/new`);
    await page.getByText(/2\. fields to read/i).waitFor({ timeout: 20000 });
    await beat(page, 1500);
    await type(page, page.locator('label:has-text("Profile ID") + input'), DEMO.newProfileId);
    await type(page, page.locator('label:has-text("Source / Supplier Name") + input'), DEMO.newProfileName);
    await show(page, page.getByText(/nothing is read yet/i));
    await beat(page, 2500);
    await show(page, page.getByText(/no columns yet/i));
    await beat(page, 2500);
    await checkpoint(page, name, "empty");
    await page.evaluate(() => window.scrollTo({ top: 0, behavior: "smooth" }));
    await beat(page, 900);
    await click(page, page.getByRole("button", { name: /^save$/i }), 2500);
    await page.waitForURL(new RegExp(`/profiles/${DEMO.newProfileId.replace(/\./g, "\\.")}`), { timeout: 20000 });
    await beat(page, 1500);
    await click(page, page.getByRole("tab", { name: /^training$/i }), 1500);
    await click(page, page.getByRole("button", { name: /start training/i }), 3500);
    await checkpoint(page, name, "blocked");
    await beat(page, 3000);
  },

  /** Part 5: the builder's Output tab inherits the profile's columns until customised. */
  async "part5-builder-output"(page, name) {
    await page.goto(`${base}/models/builder?profileId=${encodeURIComponent(DEMO.colt)}`);
    const choose = page.getByRole("button", { name: /choose pdf/i });
    await choose.waitFor({ timeout: 20000 });
    await beat(page, 1500);
    await glide(page, choose);
    const chooser = page.waitForEvent("filechooser");
    await choose.click();
    await (await chooser).setFiles(DEMO.coltSample);
    await page.getByText(path.basename(DEMO.coltSample)).waitFor({ timeout: 20000 });
    await beat(page, 1200);
    await click(page, page.getByRole("button", { name: /start building/i }), 3500);
    const outputTab = page.getByRole("tab", { name: /^output$/i });
    await outputTab.waitFor({ timeout: 60000 });
    await beat(page, 1500);
    // At 100% the page is wider than the canvas; zoom out so all of it shows.
    for (let i = 0; i < 2; i += 1) await click(page, page.getByTitle("Zoom out"), 500);
    await beat(page, 2000);
    await checkpoint(page, name, "canvas");
    await click(page, outputTab, 1800);
    await checkpoint(page, name, "inherit");
    await click(page, page.getByRole("button", { name: /customise for this template/i }), 1500);
    const header = page.getByLabel(/^header for column 1$/i).first();
    await type(page, header, "SERVICE_ID");
    await beat(page, 1800);
    await checkpoint(page, name, "custom");
    await click(page, page.getByRole("button", { name: /back to the profile's columns/i }), 2500);
    await checkpoint(page, name, "back");
  },

  /** Part 6: an edit to the fingerprint rules re-keys the profile's templates. */
  async "part6-rekey"(page, name) {
    // The document category only moves the family key; the layout hash is
    // salted by the fingerprint rules, so the edit shown is one of those.
    await page.goto(`${base}/profiles/${DEMO.colt}`);
    await page.getByText(/2\. fields to read/i).waitFor({ timeout: 20000 });
    await beat(page, 1500);
    await click(page, page.getByRole("tab", { name: /^advanced$/i }), 1500);
    // The fingerprint rules are an engine internal, hidden until asked for.
    const internals = page.locator("div", { hasText: /^Show engine internals/ }).last().locator("xpath=..").getByRole("switch").first();
    await click(page, internals, 1500);
    const label = page.locator("label", { hasText: /^Summary Anchors$/ }).first();
    await label.waitFor({ timeout: 20000 });
    await show(page, label);
    await beat(page, 1800);
    const input = label.locator("xpath=..").locator("input").first();
    await type(page, input, DEMO.coltNewAnchor);
    await input.press("Enter");
    await beat(page, 1500);
    await checkpoint(page, name, "edited");
    await page.evaluate(() => window.scrollTo({ top: 0, behavior: "smooth" }));
    await beat(page, 900);
    await click(page, page.getByRole("button", { name: /^save$/i }), 600);
    await page.getByText(/re-keyed/i).first().waitFor({ timeout: 30000 });
    await beat(page, 600);
    await checkpoint(page, name, "rekeyed");
    await beat(page, 4000);
  },
};

// ── Run ────────────────────────────────────────────────────────────────────

const browser = await chromium.launch();

const login = await browser.newContext({ viewport: VIEWPORT });
const lp = await login.newPage();
await lp.goto(`${base}/login`);
await lp.getByLabel("Email").fill(email);
await lp.getByLabel("Password").fill(password);
await lp.getByRole("button", { name: "Sign in" }).click();
await lp.waitForURL((u) => !u.pathname.startsWith("/login"), { timeout: 20000 });
const storageState = await login.storageState();
await login.close();

const names = wanted.length ? wanted : Object.keys(SCENES);
let failed = 0;
for (const name of names) {
  const scene = SCENES[name];
  if (!scene) {
    console.error(`unknown scene: ${name}`);
    failed += 1;
    continue;
  }
  const ctx = await browser.newContext({
    viewport: VIEWPORT,
    deviceScaleFactor: 1.25,
    colorScheme: "dark",
    storageState,
    recordVideo: { dir: path.join(outDir, ".raw"), size: { width: 1920, height: 1080 } },
  });
  // next-themes keeps its own choice (default light) and ignores the OS scheme.
  await ctx.addInitScript(() => {
    try { localStorage.setItem("theme", "dark"); } catch {}
  });
  await ctx.addInitScript(CURSOR);
  const page = await ctx.newPage();
  page.setDefaultTimeout(20000);
  const started = Date.now();
  try {
    await scene(page, name);
    console.log(`  ${name}: ok (${Math.round((Date.now() - started) / 1000)} s)`);
  } catch (err) {
    failed += 1;
    console.error(`  ${name}: FAILED - ${err.message.split("\n")[0]}`);
    await checkpoint(page, name, "failure").catch(() => {});
  }
  const video = page.video();
  await ctx.close();
  if (video) renameSync(await video.path(), path.join(outDir, `${name}.webm`));
}

await browser.close();
process.exit(failed ? 1 : 0);
