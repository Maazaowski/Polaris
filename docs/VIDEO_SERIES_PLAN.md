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

Prep: valid key, debug mode on, one invoice from a supplier that does not exist yet in the DB.

### Part 3: Supplier profiles and the three configuration layers

*Module: profiles, field schemas, output specs.*

- Open a profile: identify, output mapping, per-field hints, accounts, notes.
- Switch output spec from the 8-column standard to the wireless spec and show the delivered columns change in the preview tab, with no code.
- Open the field schema and the output spec editors briefly: "what we extract" and "what we deliver" are data, not code.
- Accounts view: map a folder on disk to the profile, show the state flip from unmapped to mapped without a rescan.

Prep: none beyond the current data.

### Part 4: Teaching Polaris a layout (AI training loop)

*Module: training, candidate models, approval.*

- Put a profile in training, upload three invoices from the same layout.
- Show the training progress: author rules, execute, diff against the AI's answer, refine. Open `training_report.json` and the AI-vs-model XLSX pair from the model review downloads.
- The candidate appears on Templates. Walk the model page: header rules, region, column bands, row classifiers, grouping, line-item fields. "This is the whole template. It is JSON. The interpreter runs it; the AI only wrote it."
- Approve. Drop a fourth invoice. It runs free.

Prep: valid key; a layout with four or more invoices (euNetworks corpus has nine).

### Part 5: Building a template by hand (the visual builder)

*Module: model builder.*

- Open the builder with a sample PDF. Draw the line-item region, the column bands, a row classifier for the lines that carry amounts, a header rule for the invoice number.
- Live preview after every edit. Score the draft against the eval folder for that layout.
- Save as candidate, approve, run an invoice. Same interpreter, same result, no AI involved at all.
- Follow the Orange or AT&T guides in `docs/` as the script; they already walk through the hard parts (two-column layouts, tax allocation).

Prep: valid key is not required for the builder itself; the eval-folder scoring needs debug mode.

### Part 6: When things go wrong (exceptions, drift, review)

*Module: exception queue, reconciliation, layout drift, reject and regenerate.*

- Show a variance exception: the line items do not add up to the stated total; open it, see the partial output, resolve or retry.
- Show layout drift: a supplier changed their invoice; the fingerprint no longer matches; Polaris falls back to AI and flags it instead of delivering wrong numbers silently.
- Clone the template to retrain, approve the new version, roll back if needed; versions tab.
- Mention the re-key script for the case where *you* changed the profile, not the supplier.

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
