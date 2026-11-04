# Polaris video series: plan

Eight weekly parts, each on one feature or module, each short enough to watch over coffee. The through-line for the whole series is one sentence: **the first invoice from a layout pays for AI, every invoice after it is free.** Every episode should land back on that sentence.

Target length 4 to 7 minutes. Record at 1920×1080 with the browser at 125% zoom so tables are legible on a phone. Dark theme reads better in thumbnails; the UI supports both.

**Companion:** [`FEATURE_AUDIT_2026-11-03.md`](FEATURE_AUDIT_2026-11-03.md) lists what to fix before recording.

## Before recording anything

1. **A valid AI key** saved in Settings (OpenAI or Anthropic). Episodes 2, 4, 5 and 7 need it. The key on file today is dead.
2. **Demo data that looks alive.** Either keep the current dev database (rich, but the top of the queue is a wall of failed Granite intakes from the dead key) or reset with the Danger zone and seed. A `seed_demo.py` script (see the audit) is the cleanest path: two suppliers, approved templates, twenty processed invoices across a month so Insights has curves.
3. **Run the Docker stack, not `next dev`,** for recording. Routes are pre-built, so there is no first-visit compile stutter on camera.
4. **Supplier folders on screen.** Have `C:\Polaris\<Supplier>\pdf` open in Explorer next to the browser for the drop-a-file moments.
5. **One real invoice pair per layout.** The corpus Colt invoices work today: eight PDFs, same layout, approved template. Keep two aside for "the second one is free".

## The episodes

### Part 1: What Polaris is, in five minutes

*Module: the whole product. Pure demo, no configuration.*

- Open on an Explorer window and an XLSX: "this is what the customer wants, every month, from forty suppliers".
- Drop a Colt PDF into its folder. Cut to the queue: it appears, the timeline ticks through intake, fingerprint, routing, template, reconcile, output.
- Open the invoice: delivered rows, the totals that reconcile, the XLSX download. Point at **Path: FREE, cost $0.00, 0 tokens**.
- Click **Show on PDF**, then the crosshair on one row: the page appears with that row outlined and the amount cell marked. "Every number in this spreadsheet points back at the place it was printed."
- The hook: "that was the second Colt invoice. Here is what the first one looked like" → cut to an AI-path invoice with its token count and cost. "Polaris read it once, wrote the rules, and has not paid since."
- Close on the queue's three counters: need you, reconciled, ran free.

Prep: approved Colt template (done), a processed AI-path invoice to contrast with.

### Part 2: The first invoice (AI extraction)

*Module: classification + AI extraction + reconciliation.*

- A supplier with no profile at all. Upload. Watch classification name the supplier, extraction run, reconciliation pass.
- Open AI calls (debug) and show one captured prompt: the layout text the model sees, the schema it must fill, the structured response. This is the "no magic" moment.
- Show the Audit & usage tab: tokens in, tokens out, cost, per call.
- Mention text-first extraction: page images only when a page has no text layer.
- Open the output package. With no profile there are no configured columns, so it delivers the canonical JSON plus a raw extraction workbook (an Invoice sheet with every document field read, a Line items sheet with every row field). Say so: "this is a dump of what was read; a profile is what turns it into the customer's deliverable."

Prep: valid key, debug mode on, one invoice from a supplier that does not exist yet in the DB.

### Part 3: Supplier profiles: what a supplier reads and delivers

*Module: profiles, the field catalogue, delivered columns.*

- Open a profile on the **Setup** tab and walk its sections: identify the source, **Fields to read**, **Delivered columns**, accounts, notes.
- **Fields to read:** search the field catalogue and add a field. A catalogue pick brings its type and role; the supplier only supplies the printed label, date format and required flag. Then add a custom field the catalogue does not know.
- **Delivered columns:** add, reorder and rename columns; point one at a field and one at the computed per-line tax. Open **Preview Output** and show the delivered columns change, with no code.
- The point to land: "what we read" and "what we deliver" belong to this supplier's profile, in data, not code. A new profile starts with both lists empty and there is no default column set. Show the readiness message: a profile cannot be trained or activated until it has fields, columns, a date format on every delivered date and an amount field.
- Accounts view: map a folder on disk to the profile, show the state flip from unmapped to mapped without a rescan.

Prep: a profile with fields and columns configured, and a second new profile with both lists empty for the readiness moment.

### Part 4: Teaching Polaris a layout (AI training loop)

*Module: training, candidate models, approval.*

- Put a profile in training (it must already have fields and columns, or the readiness check blocks it), upload three invoices from the same layout.
- Show the training progress: author rules, execute, diff against the AI's answer, refine. Open `training_report.json` and the AI-vs-model XLSX pair from the model review downloads.
- The candidate appears on Templates. Walk the model page: header rules, region, column bands, row classifiers, grouping, line-item fields. "This is the whole template. It is JSON. The interpreter runs it; the AI only wrote it."
- Approve. Drop a fourth invoice. It runs free.

Prep: valid key; a layout with four or more invoices (euNetworks corpus has nine).

### Part 5: Building a template by hand (the visual builder)

*Module: model builder.*

- Open the builder with a sample PDF. Draw the line-item region, the column bands, a row classifier for the lines that carry amounts, a header rule for the invoice number.
- Live preview after every edit. Score the draft against the eval folder for that layout.
- Open the **Output** tab. Bound to a profile, the template inherits the profile's columns ("Inheriting N columns from the profile"). Click **Customise for this template** to give it its own; template columns win over the profile's, and **Back to the profile's columns** undoes it.
- Save as candidate, approve, run an invoice. Same interpreter, same result, no AI involved at all.
- Follow the Orange or AT&T guides in `docs/` as the script; they already walk through the hard parts (two-column layouts, tax allocation).

Prep: valid key is not required for the builder itself; the eval-folder scoring needs debug mode.

### Part 6: When things go wrong (exceptions, drift, review)

*Module: exception queue, reconciliation, layout drift, reject and regenerate.*

- Show a variance exception: the line items do not add up to the stated total; open it, see the partial output, resolve or retry.
- Show layout drift: a supplier changed their invoice; the fingerprint no longer matches; Polaris falls back to AI and flags it instead of delivering wrong numbers silently.
- Clone the template to retrain, approve the new version, roll back if needed; versions tab.
- Mention the case where *you* changed the profile, not the supplier: saving a profile that changes its fingerprint rules, line-item anchors, field label hints or document category re-keys its approved templates automatically, and the save toast says so. `scripts/refingerprint_models.py` is only for fingerprinter code changes.
- Show the configuration exception: an active profile with no delivered columns parks its invoices before any AI is spent.

Prep: one invoice with a real variance (the Rogers ones in the dev DB), one drift case (Granite in the dev DB).

### Part 7: Measuring it (Insights, costs, evals)

*Module: Insights, Audit & usage, Evals.*

- Insights: cost split between extraction and training, reconciliation rate, cost by model and by supplier, "ran at $0" share rising month over month.
- Evals: 42 labelled invoices across 10 layouts. Run a prompt change, compare against the baseline: F1, hallucinations, reconciliation, cost. "We do not guess whether a prompt change helped."
- Open the HTML report grouped by profile.

Prep: valid key for a live eval run (or show an existing run and its compare view); seeded month-over-month data for the charts.

### Part 8: Running it for real (ops, security, deployment)

*Module: users and roles, keys, watcher, folders, Docker, CI.*

- Users and roles; what only admins can do; audit blame on every change.
- Keys stored encrypted in the database; switching provider between OpenAI and Anthropic.
- The two folder roots and why operational state never touches supplier folders; the manifest-last ready signal a downstream bot can poll.
- `docker compose up` with the dev overlay; the production topology with an external MySQL (the Windows Server guide).
- CI: four offline jobs on every change; AI authoring snapshots refreshed on demand.

Prep: a second user account to show the role difference; the CI workflow on a GitHub remote so the checks are real.

## Needs re-recording (profile contract change, 4 Nov 2026)

The shared Field schema and Output spec registries were folded into each supplier profile (a profile's `fields` and `output_columns`). The `/field-schemas` and `/output-specs` pages are gone. Anything already shot before that change is out of date:

- **Part 3** (profiles): re-record in full. It showed switching an output spec and opening the two registry editors; it now shows the profile's Setup tab (Fields to read, Delivered columns).
- **Part 5** (builder): re-record if shot. There is a new **Output** tab, and the saved template can carry its own columns.
- **Part 2** (first invoice): re-record the closing scene if shot. An invoice with no profile now delivers JSON plus a raw extraction workbook, not a configured spreadsheet.
- **Part 4** (training) and **Part 6** (exceptions): re-record only the affected scenes if shot. Training is gated on the profile having fields and columns, and re-keying after a profile edit is now automatic.

Parts 1, 7 and 8 are unaffected.

Silent 1080p footage of these changed scenes (dark theme, 125%, drawn cursor, no voice) can be regenerated for a voice-over with `frontend/scripts/record-episode-scenes.mjs` against a production build of the demo stack; its header lists the scenes, the demo data each needs and how to restore the demo afterwards. Output goes to the gitignored `recordings/` folder.

## Optional parts if the series runs longer

- **The AI profile assistant**: drafting a whole supplier profile from two invoices and a blueprint XLSX.
- **Long documents**: the 656-page invoice, rules-first authoring from a page sample, and why that matters for cost.
- **Behind the scenes**: the golden corpus and how a change to the interpreter is proven not to break a single delivered cell.

## Episode checklist (use for every recording)

- Stack running from Docker; debug on only for the episodes that need it.
- Browser at 125%, no bookmarks bar, a clean profile without extensions.
- Queue filtered so the first screen is not a wall of red.
- The "ran free" counter visible at the end of every episode.
- Script the first sentence and the last sentence; improvise the middle.
