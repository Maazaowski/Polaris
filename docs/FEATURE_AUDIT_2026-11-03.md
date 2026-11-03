# Polaris feature audit (3 Nov 2026)

A full run-through of the product ahead of the promotional video series: the stack was brought up natively against the real dev database, every route was walked in a browser, the backend suite, the production frontend build and the Playwright suite were run, and the headline "$0 template path" was exercised end to end.

**Companion:** [`VIDEO_SERIES_PLAN.md`](VIDEO_SERIES_PLAN.md).

## Verdict in one paragraph

The product is in good shape. All 16 routes render without errors, the backend suite is green (779 tests), the production build is clean, and the Playwright suite passes once run at a sane parallelism against the dev server. The pipeline's core promise is real: an invoice from a known layout was processed by an approved template with zero tokens and zero cost, reconciled, and delivered as XLSX. Two things stand between the current checkout and a confident recording session: the AI key on file is dead, and approved templates can be silently orphaned when a profile's fingerprint rules change (a script now fixes that; the proper fix is automatic).

## What was verified working

| Area | Evidence |
|---|---|
| Login, sessions, roles | Admin login lands on the queue; anonymous users are redirected; user management lists 7 accounts with roles and last login. |
| Work queue | 192 intakes, status chips with counts, filters that survive reload, search, pagination, headline counters (need you / reconciled / ran free). |
| Invoice detail | Delivered rows table, header fields, downloads, processing timeline with per-step status, token and cost figures, reject-and-regenerate for template runs. |
| Exceptions | Reasons are specific (variance %, layout drift with both fingerprints, profile validation paused), with view/retry/resolve. |
| Upload | Drag-and-drop with recent-intake list. |
| Suppliers | 31 profiles with template state (none / cutting / ready / drifted) and delivery folders; the editor's five tabs; AI assistant entry; developer tools. |
| Accounts | 34 on-disk accounts discovered by the background scan; unmapped / mapped / conflict / missing states; assign, create, sync. |
| Templates | 6 models across statuses; model detail renders the rules as readable tables; clone, retire, delete; versions tab. |
| Model builder | Loads for a profile, asks for a sample PDF, ready for the canvas flow. |
| Field schemas, output specs | 1 schema (37 fields), 5 specs (8 to 14 columns), editors reachable. |
| Settings | Provider switch, encrypted key storage, per-task models, thresholds, worker concurrency, watcher timing, debug, danger zone. |
| Insights | Totals, reconciliation rate, cost split (extraction vs training), monthly breakdown by model and supplier. |
| Audit and usage | Processing trail with full error text; token usage tab. |
| Evals (debug) | 42 labelled cases across 10 layouts; 40 past runs with F1, hallucination count, reconciliation rate and cost; baseline compare. |
| AI calls (debug) | Capture viewer loads (empty, since no AI call succeeded recently). |
| Pipeline, template path | Corpus Colt invoice `756260789_20251001.pdf` → fingerprint match → approved model → 5 rows, reconciled, $0.00, 0 tokens, XLSX + JSON + manifest written. |
| Accessibility floor | The e2e suite's accessible-name and horizontal-scroll checks pass on every route, desktop and mobile. |

## Fixed in this pass

| Fix | Where |
|---|---|
| Nested `<button>` elements in Evals run cards (invalid HTML, React hydration error on every visit) | `frontend/src/app/evals/page.tsx` |
| Base UI "expected a native button" warning on every button-styled link (Profiles, Invoices, invoice detail, timeline, not-found) | `frontend/src/components/ui/button.tsx` now sets `nativeButton={false}` whenever `render` is given |
| Playwright pagination test matched the Next.js dev-tools button (`/next/i`) and failed in strict mode | `frontend/e2e/invoices.spec.ts` |
| Approved Colt template orphaned by fingerprint drift; every Colt invoice was going to AI as "layout drift" | New `registry.rekey_model_fingerprint`, `crud.update_model_fingerprint`, `scripts/refingerprint_models.py` (dry run by default), 6 tests. Applied to `colt.standard.v1` in the dev DB. |
| CI described in the docs did not exist | `.github/workflows/ci.yml` (lint, test, frontend lint+build, docker build) and `authoring-manual.yml` |
| README stale (profiles "live as JSON", pages list from an older nav, Docker quick start pointed at the production compose, CI references, troubleshooting paths) | Rewritten `README.md`; `frontend/README.md` was create-next-app boilerplate and is now real; `CLAUDE.md` refreshed with the native-run recipe, drift gotcha, Playwright notes |

## Needs fixing

Ordered by how much it matters for the videos.

1. **The AI key is dead.** The `.env` OpenAI key and the stored one both return 401. Every AI-path intake since 18 Aug 2026 failed with `invalid_api_key`; the 11 Granite intakes at the top of the queue are all that failure. Nothing in episodes 2, 4 or 5 can be recorded until a valid OpenAI or Anthropic key is saved in Settings. (User action; not something the code can fix.)
2. **Fingerprint drift is silent.** Editing a profile's fingerprint rules or document category after approving a model orphans it; the UI only shows "drifted" on the profile list, the queue shows "ran free: 0", and operators get a layout-drift exception per invoice. The re-key script covers it today. Proper fix: re-key the profile's models automatically when those fields are saved (or refuse the save with a warning), and show a "re-key" action on the model page. ~half a day.
3. **Timestamps are naive and mixed.** `created_at` comes from MySQL `NOW()`, job timestamps from Python `datetime.now()`, and the UI formats both as UTC. On a native run in UTC+5 the invoice detail shows *Received 13:58, Started 18:58*. In Docker (UTC) it lines up, so it has gone unnoticed. Fix: store UTC everywhere and render in the viewer's zone. ~half a day including a migration note.
4. **Invoice detail "Model" row shows the LLM name, not the template.** On a template run it shows "—" although the job carries `extraction_model_id`. Show the template id on model runs and the LLM name on AI runs. Small.
5. **"Output copy failed" is logged as a failed step on a completed intake** when the profile has no `output_path`. It reads as a failure in the timeline. Either downgrade to a warning or surface "no delivery folder" on the profile. Small.
6. **Orphaned model rows.** Two candidate models reference intakes that no longer exist and one references a deleted profile (`granite.standard.v1`), so the Templates page lists models that can never run or be retrained. Add an orphan badge and a cleanup, or cascade on profile delete. Small to medium.
7. **Settings shows "CONFIGURED" for an invalid key.** A one-call "Test key" button (list models) would have caught item 1 months earlier. Small.
8. **Playwright seeding is Docker-only.** `npm run test:e2e` shells into the backend container; against a native stack you must export credentials by hand (now documented). Teaching the seed script to call the API or a local Python fallback would make the suite one command everywhere. Small.
9. **Dev-server e2e timing.** Three navigation specs time out under full parallelism against `next dev` because routes compile on first visit. Passing with `--workers=1`. Either warm the routes in the setup project or raise the expect timeout for navigation specs. Small.
10. **Fresh install has no data.** `supplier_profiles/` is empty, so a brand-new database starts with zero profiles and the Accounts scan root is empty. Fine for production, hostile for demos and onboarding (see "add" below).
11. **Backlog hygiene.** `mypy src` has a long-standing backlog (not a gate); `scripts/probe_colt_layout.py` has two ruff findings outside the lint path; the `POLARIS_API_KEY` line in `.env` files is read by nothing.

## Worth adding

Ideas that would strengthen the product and give the series more to show. Rough sizes.

- **Demo seed command.** `python scripts/seed_demo.py` that loads the corpus Colt and euNetworks profiles, their approved models, and a handful of processed invoices, so a fresh install (or a reset before recording) shows a living dashboard in one command. Half a day. Highest value for the videos.
- **Provenance view on the invoice page.** The builder already renders the PDF as rows and cells in page space; reuse it on the invoice detail to highlight where each delivered cell came from. This is the single most convincing thing to show a sceptical operator, and it turns "AI extraction" into something auditable. 2 to 3 days.
- **Automatic re-key and template health.** Item 2 above, plus a per-profile "template health" strip: last used, last validated, drift status, with one-click re-key or retrain. 1 day.
- **Test-key button and a first-run checklist.** Key valid, worker reachable, Redis reachable, a watched folder exists. Half a day.
- **Machine access tokens.** The README is explicit that there is no API key on `/api/v1`; a downstream bot that polls `manifest.json` or calls the API has to log in like a person. Scoped bearer tokens managed on the Users page, with audit blame. 1 to 2 days.
- **Notifications.** Email or webhook when an intake lands in Needs review, with the reason and a deep link. 1 day.
- **Bulk actions on the queue.** Retry all layout-drift exceptions for a profile after retraining; reject-and-regenerate a selection after a model rollback. 1 day.
- **Template diff between versions.** The versions tab lists versions; a side-by-side of rule changes (and which eval cases each version passes) would make clone/rollback decisions obvious. 1 to 2 days.
- **Scanned-PDF path.** Extraction already attaches page images for pages with little text; make the OCR path explicit, with a confidence badge, so scanned invoices are a feature rather than a fallback. 2 to 3 days.
- **Eval runs from CI.** The eval harness exists; a manual workflow that runs a chosen layout and posts the F1 and cost deltas against the baseline on the PR would close the loop for prompt changes. Half a day on top of the manual authoring workflow.

## How the stack was run for this audit

MySQL and Redis from the Docker dev overlay (MySQL on host port 3307, which holds the real dev data), then uvicorn, the Celery worker (`--pool=solo`) and the frontend natively with `POLARIS_DATA_DIR=C:/Polaris` and `POLARIS_WORK_DIR` pointing at the folder Docker mounts as `/work`, so existing intakes and archives resolve. The recipe is in `README.md` under *Local development without Docker*.

Results: `pytest` 779 passed, 1 skipped; `ruff` clean on `src tests`; `tsc` clean; `npm run build` clean; Playwright 60 passed + 4 failed in the parallel run, of which 3 pass serially and 1 was the test bug fixed above.
