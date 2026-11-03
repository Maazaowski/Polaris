# Polaris

**AI-powered invoice extraction that learns.** Drop a supplier's PDF invoice in a folder and get back the exact spreadsheet your downstream system expects. The first invoice from a new layout is read by AI; every invoice after that is read by a reusable template at **zero AI cost**.

Polaris replaces hand-built, per-supplier report templates (the Astera ReportMiner style of ETL) with a hybrid system: AI **authors** a declarative extraction model once per layout, and a generic **interpreter** runs that model on every subsequent invoice. No supplier-specific code, no per-invoice AI bill.

---

## Contents

- [How it works](#how-it-works)
- [What you get](#what-you-get)
- [Quick start (Docker)](#quick-start-docker)
- [Local development without Docker](#local-development-without-docker)
- [First run: from empty database to first invoice](#first-run-from-empty-database-to-first-invoice)
- [Processing pipeline, step by step](#processing-pipeline-step-by-step)
- [Templates: how the system gets cheaper over time](#templates-how-the-system-gets-cheaper-over-time)
- [The three configuration layers](#the-three-configuration-layers)
- [Folders on disk](#folders-on-disk)
- [The UI](#the-ui)
- [API](#api)
- [Testing and CI](#testing-and-ci)
- [Configuration reference](#configuration-reference)
- [Troubleshooting](#troubleshooting)
- [Further reading](#further-reading)

---

## How it works

```
                 ┌──────────────────┐
                 │   Invoice PDF    │  watched folder, upload page, or API
                 └────────┬─────────┘
                          │
                 ┌────────▼─────────┐
                 │ 1. INTAKE        │  register, archive the original, stage for processing
                 └────────┬─────────┘
                          │
                 ┌────────▼─────────┐
                 │ 2. FINGERPRINT   │  hash the page layout with pymupdf (deterministic, no AI)
                 └────────┬─────────┘
                          │
            ┌─────────────┴─────────────┐
    known layout                    new layout
   (approved template)          (no template yet)
            │                               │
   ┌────────▼─────────┐           ┌─────────▼────────┐
   │ 3a. TEMPLATE     │           │ 3b. AI           │
   │ interpreter runs │           │ classify + read  │
   │ the saved rules  │           │ the invoice,     │
   │ $0, no API call  │           │ then AUTHOR a    │
   │                  │           │ candidate model  │
   └────────┬─────────┘           └─────────┬────────┘
            └─────────────┬─────────────────┘
                          │
                 ┌────────▼─────────┐
                 │ 4. RECONCILE     │  line items must add up to the stated totals
                 └────────┬─────────┘
                          │
                 ┌────────▼─────────┐
                 │ 5. OUTPUT        │  XLSX in the customer's column spec + JSON + manifest
                 └──────────────────┘
```

**The key separation: AI is the model *author*, not the model *runner*.** For a new layout the AI extracts ground truth once, then writes an `ExtractionModel`: declarative JSON describing region anchors, row classifiers, column bands and transforms. A generic interpreter executes that JSON on every later invoice with the same supplier profile and layout fingerprint. The interpreter knows layout *primitives*; it knows nothing about any particular supplier.

Models are routed by **`supplier_profile_id` + `layout_fingerprint`**. Approved model with an exact match: template path, $0. Anything else: AI path, and the system records why (unknown layout, drifted layout, no profile).

## What you get

- **Three ways in.** A per-supplier watched folder, a drag-and-drop Upload page, or `POST /api/v1/invoices/upload`.
- **One deliverable contract.** An Output Spec defines the columns delivered (the historical default is an 8-column "TemForce standard" XLSX); several specs ship for wireless, time-and-material and Orange layouts, and you can define your own.
- **Two ways to build a template.** An AI training loop (author, execute, diff against the AI's answer, refine) and a **visual model builder** where you draw the same primitives by hand against a sample PDF. Both produce the same model JSON, run by the same interpreter.
- **An AI profile assistant** that drafts a supplier profile from one or more invoices and an optional blueprint of the expected output.
- **Deterministic safety nets.** Layout fingerprinting, arithmetic reconciliation against stated totals, self-checks inside each model, and a candidate/approved lifecycle with clone, rollback and retire.
- **Operations built in.** A processing queue with live timeline, an exception queue with retry/resolve, an Accounts view that maps folders on disk to profiles, cost and volume insights, an audit trail with per-call AI token usage, user management with roles, and encrypted in-app API-key storage for OpenAI or Anthropic.
- **An eval harness** (debug mode) that scores any prompt change against a labelled corpus of real invoices and compares it with an accepted baseline.

## Quick start (Docker)

Requires [Docker Desktop](https://www.docker.com/products/docker-desktop/) (or Docker Engine) and an OpenAI or Anthropic API key.

The base `docker-compose.yml` is the **production** topology: it expects an external MySQL via `POLARIS_DATABASE_URL`. For a laptop, layer the **dev overlay**, which adds a local MySQL container.

```bash
git clone <this repo> polaris && cd polaris

cp .env.example .env
# Edit .env:
#   POLARIS_OPENAI_API_KEY=sk-…          (or set a key later in Settings → AI Configuration)
#   POLARIS_ADMIN_EMAIL / POLARIS_ADMIN_PASSWORD   first admin, created on first boot
#   POLARIS_HOST_DATA_DIR   Windows/host folder with supplier subfolders (default C:\Polaris)
#   POLARIS_HOST_WORK_DIR   host folder for operational state      (default C:\PolarisWork)

docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --build
```

Then open <http://localhost:3000> and sign in with the admin you set. The API is on <http://localhost:8000> (`/docs` for OpenAPI). The dev MySQL is published on host port **3307** so a SQL client can inspect it.

| Task | Command |
|---|---|
| Update | `git pull && docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --build` |
| Logs | `docker compose logs -f backend worker watcher` |
| Stop | `docker compose down` (data stays in the `mysql_data` volume and host folders) |
| Production | `docker compose up -d` with `POLARIS_DATABASE_URL` pointing at the real MySQL; see [docs/DEPLOYMENT_WINDOWS_SERVER.md](docs/DEPLOYMENT_WINDOWS_SERVER.md) |

Containers: `backend` (API, runs `alembic upgrade head` on start), `worker` (Celery, the pipeline), `watcher` (folder watcher), `redis`, `frontend`, and `mysql` in the dev overlay.

## Local development without Docker

Use this when you want hot reload on the backend and frontend. You still need MySQL and Redis; the easiest way to get both is the two infrastructure containers from the dev overlay.

```bash
# Infrastructure only (MySQL on 3307, Redis on 6379)
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d mysql redis

# Backend (Python 3.12+; venv at .venv)
python -m venv .venv && .venv/Scripts/activate      # macOS/Linux: source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env                                 # fill in the key + admin
export POLARIS_DATABASE_URL=mysql+pymysql://polaris:polaris@127.0.0.1:3307/polaris
alembic upgrade head
uvicorn polaris.main:app --reload                    # :8000

# Pipeline worker (separate terminal, same env)
celery -A polaris.tasks.worker worker --loglevel=info --pool=solo   # --pool=solo on Windows

# Folder watcher (optional, separate terminal)
python -m polaris.intake.watcher

# Frontend
cd frontend && npm install && npm run dev            # :3000, proxies /api/v1 to :8000
```

Settings are read once at process start: after editing `.env`, restart the API, worker and watcher. The Settings page writes a DB-persisted runtime config that *is* picked up live by every process for the values it covers (models, thresholds, worker concurrency, log level, debug).

Two shortcuts for working on extraction without the whole stack:

```bash
python run_pipeline.py path/to/invoice.pdf   # run one PDF through the full pipeline synchronously
python run_pipeline.py                       # dev watcher: processes drops synchronously, no Celery
```

## First run: from empty database to first invoice

**Want a populated app first, with no AI key?** The demo seeder turns an empty database into a month of history in a few seconds, entirely offline: it loads the two golden-corpus profiles (Colt and euNetworks) as active suppliers with folders under `POLARIS_DATA_DIR`, approves their committed extraction models under the fingerprint the live fingerprinter computes, runs every corpus invoice through the real pipeline on the template path ($0, no AI), and spreads the results across the last 30 days. Re-running only fills gaps; `--reset` purges existing intakes first (it needs `POLARIS_DEBUG=true`, like the Settings danger zone) and `--dry-run` prints the plan without writing.

```bash
python scripts/seed_demo.py --reset
```

**A fresh database just for demos or recordings**, so the development data stays untouched:

```bash
# Native: a second MySQL beside the dev one (its own volume), then migrate and seed into it.
docker run -d --name polaris-demo-mysql -p 3308:3306 -v polaris_demo_mysql_data:/var/lib/mysql   -e MYSQL_ROOT_PASSWORD=polaris -e MYSQL_DATABASE=polaris_demo -e MYSQL_USER=polaris -e MYSQL_PASSWORD=polaris mysql:8.0
export POLARIS_DATABASE_URL=mysql+pymysql://polaris:polaris@127.0.0.1:3308/polaris_demo        POLARIS_REDIS_URL=redis://127.0.0.1:6379/1 POLARIS_DATA_DIR=C:/Polaris-demo POLARIS_WORK_DIR=C:/PolarisDemo
alembic upgrade head && python scripts/seed_demo.py
# then start the API, worker and frontend with the same variables; the first admin comes from POLARIS_ADMIN_EMAIL/PASSWORD.

# Docker: a separate Compose project gets its own MySQL volume, so it starts empty.
COMPOSE_PROJECT_NAME=polaris-demo MYSQL_DATABASE=polaris_demo   docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --build
docker compose -p polaris-demo exec backend python scripts/seed_demo.py
```

Stop the dev stack first in the Docker variant; both publish the same ports. Provider keys are encrypted with `POLARIS_SECRET_KEY`, so a key saved in one database can be carried to another only when both stacks share that secret.

To go from empty to a first invoice by hand instead:

1. **Sign in** with `POLARIS_ADMIN_EMAIL` / `POLARIS_ADMIN_PASSWORD`. The bootstrap only runs while the users table is empty; manage people afterwards under **System → Users**.
2. **Add an AI key** under **Settings → AI Configuration** if you did not put one in `.env`. Keys are stored encrypted in MySQL (`POLARIS_SECRET_KEY`), and you can switch provider between OpenAI and Anthropic there.
3. **Add a supplier.** **Suppliers → Add supplier** opens the AI profile assistant: pick the output spec and field schema, drop one or more of that supplier's invoices, and let it draft the profile. Save it, then activate it.
4. **Map a folder.** Under **Suppliers → Accounts**, assign the on-disk folder `<customer>/<account>/pdf` to the profile. The watcher picks up the folder within `POLARIS_WATCHER_REGISTRY_RESCAN_SECONDS`.
5. **Process invoices.** Drop PDFs in the folder or use **Work → Upload**. Watch the timeline on the invoice page.
6. **Cut a template.** From the profile's **Training** tab, upload a few training invoices, or build one by hand in **Templates → Build model**. When a candidate matches the AI's output exactly and passes its self-checks, **approve** it.
7. **Watch the cost go to zero.** Invoices with that layout now show *Using approved model (zero AI cost)* in their timeline, and the queue's "ran free" counter climbs.

## Processing pipeline, step by step

```
 1. INTAKE          PDF registered in `intake_records`, original archived under work_dir/archive/,
                    file staged in processing/. Source is recorded: watcher, upload, or API.

 2. FINGERPRINT     pymupdf reads block positions, labels and table headers from the first
                    pages. The hash is salted by the profile's fingerprint rules and document
                    category, so the same bytes under a different profile hash differently.

 3. ROUTING         profile + fingerprint decide the path:
                      approved model, exact fingerprint   → TEMPLATE  ($0)
                      candidate model, same fingerprint   → AI + side-by-side validation of the candidate
                      active profile, unknown fingerprint → AI + a "layout drift" exception
                      no profile                          → AI classification, then AI extraction
                    Very long documents (POLARIS_BLOCKING_CHECK_PAGE_THRESHOLD pages) try rules first,
                    authored from a page sample, and only read every page if the rules do not reconcile.

 4a. TEMPLATE       the interpreter executes the model JSON: header fields by label-relative
                    rules, line items from the layout geometry, then transforms and self-checks.
                    A failed self-check or low confidence falls back to AI.

 4b. AI             text-first extraction over the PDF's text layer in layout-preserving chunks
                    (page images only for pages with little text). Structured Outputs enforce
                    the field schema. Every call is priced and logged to `ai_cost_logs`.

 4c. TRAINING       on a profile in `training` status the AI output is ground truth; the authoring
                    loop writes rules, runs them, diffs the delivered rows, and refines up to
                    POLARIS_MODEL_AUTHORING_MAX_ATTEMPTS. A candidate is saved only on an exact match.
                    The intake still delivers the AI output even if authoring fails.

 5. RECONCILE       line items are summed and compared with the stated totals; variance above
                    POLARIS_RECONCILIATION_VARIANCE_THRESHOLD lands the invoice in Needs review.

 6. OUTPUT          work_dir/completed/<intake_id>/
                      <original name>.xlsx      the deliverable, in the profile's output spec
                      canonical_invoice.json    the full normalized extraction
                      extraction_log.json       path taken, tokens, cost, confidence, warnings
                      provenance.json           where each delivered cell was read from (page, printed row, box)
                      manifest.json             written LAST, the ready signal for pickup
                      model_review/             AI vs model comparison files, when training/validating
                    The XLSX is also copied to the profile's output folder under the same name;
                    a name collision delivers "name (2).xlsx" and logs a warning instead of overwriting.

 7. DONE            completed · completed_with_warnings · failed
```

## Templates: how the system gets cheaper over time

```
  FIRST invoice of a layout                 EVERY invoice after it
  ─────────────────────────                 ───────────────────────────
  1. no approved model                      1. fingerprint matches an approved model
  2. AI reads the invoice (cents to ~$0.50) 2. interpreter executes the model
  3. AI authors declarative rules           3. no API call, 0 tokens
  4. candidate saved on exact match         4. same XLSX contract
  5. a human approves it in the UI          5. cost: $0.00
```

**Lifecycle.** `candidate → approved → retired`, with `failed_validation` for candidates that could not reproduce the AI output. A candidate is validated side by side against the AI on live invoices until it has `POLARIS_MODEL_VALIDATION_REQUIRED_SUCCESSES` wins; `POLARIS_MODEL_VALIDATION_MAX_FAILURES` failures flag it. Approved models can be cloned to retrain (a new version), rolled back, or retired. Every change records who did it.

**Two authoring paths, one interpreter.**

- *AI training loop*: `models/authoring.py` + `models/training.py`. Author rules from layout evidence and profile hints, execute with `models/interpreter.py`, diff the delivered rows with `models/diff.py`, re-author with the diff as feedback.
- *Visual model builder* (**Templates → Build model**): upload a sample, see its rows and cells on a canvas, draw regions, column bands, row classifiers, header rules, grouping, tax and computed values. Live preview dry-runs the unsaved draft; a debug-only control scores it against a whole eval folder. Save creates the same candidate the AI would.

**Fingerprint drift.** A fingerprint depends on the profile's fingerprint rules and document category and on the fingerprinter itself. Change any of those after approving a model and the stored hash stops matching what the pipeline computes for the same PDF: every invoice then falls to AI with a layout-drift exception, and the "ran free" counter stays at zero. Re-key affected models from the invoice they were authored on:

```bash
python scripts/refingerprint_models.py              # dry run: shows which models would change
python scripts/refingerprint_models.py --apply      # write the recomputed fingerprints
```

## The three configuration layers

Polaris is domain-agnostic by design. Supplier knowledge never lives in code; it lives in three kinds of data, all editable in the UI and stored in MySQL.

| Layer | What it holds | Where |
|---|---|---|
| **Supplier profile** | Routing (aliases, folders), header and line-item hints for the AI, fingerprint rules, training settings, which field schema and output spec to use | **Suppliers → Profiles** (`profiles/schema.py`) |
| **Field schema** | The extraction contract: document-level and row-level fields the AI or interpreter must produce | **Suppliers → Field schemas** (`fields/`) |
| **Output spec** | The deliverable: columns, mappings from fields, formatting | **Suppliers → Output specs** (`specs/`, `output/mapper.py`) |

`validation/schema.py` defines `CanonicalInvoice`, the normalized form both extraction paths produce and everything downstream consumes.

The JSON files under `supplier_profiles/`, `field_schemas/` and `output_specs/` are **seed files only**: they are imported into MySQL on startup when a row is missing, and the database is the source of truth after that.

## Folders on disk

Two roots, kept separate on purpose.

```
POLARIS_DATA_DIR   (Docker: /data, host default C:\Polaris)        supplier data only
  <Supplier>/pdf/        inbound invoices for that account (watched)
  <Supplier>/xls/        delivered spreadsheets
  Invoices/              the <customer>/<account>/*.pdf tree the Accounts view scans

POLARIS_WORK_DIR   (Docker: /work, host default C:\PolarisWork)    operational state
  inbound/               uploads land here before intake
  processing/            in flight
  completed/<id>/        output packages (see step 6 above)
  exceptions/<id>/       failed or uncertain, with error_log.json
  archive/<id>/          every original PDF, untouched
  accounts/              the Accounts snapshot written by the background scan
  evals/, ai_debug/, builder_samples/, previews/   debug and tooling state
```

The dev reset in **Settings → Danger zone** wipes the work-dir lifecycle folders and intake tables. It never touches `POLARIS_DATA_DIR`.

The **Accounts** view does not walk the disk during a request (that hangs on large bind mounts). A Celery task scans `POLARIS_ACCOUNTS_SCAN_DIR` into a snapshot; the page reads the snapshot and recomputes each account's mapped/unmapped/conflict/missing state against the live profiles, so assigning a profile shows immediately.

## The UI

Three sections, reachable from the rail on the left or the command palette (`Ctrl/Cmd+K`).

| Section | Route | What it is for |
|---|---|---|
| **Work** | `/invoices` | The queue. Status chips, supplier filter, search and pagination survive reloads; headline counters for *need you*, *reconciled* and *ran free*. Stacked records on a phone. |
| | `/invoices/[id]` | One invoice: delivered rows, header fields, downloads, and a live processing timeline (polling plus WebSocket). Cancel or reject in flight. **Show on PDF** locates any delivered row or header field on the reconstructed page: template runs highlight the exact cells each value was read from; AI runs highlight the printed row they cited. |
| | `/exceptions` | Failed and variance invoices with the reason; retry or resolve. |
| | `/upload` | Drag-and-drop PDFs with per-file progress. |
| **Suppliers** | `/profiles` | Every supplier profile with its template state (none, cutting, ready, drifted) and delivery folder. |
| | `/profiles/[id]` | The editor: identify, output mapping, per-field hints, accounts, notes, advanced, preview output, training. **Edit with AI** opens the assistant on an existing profile. |
| | `/profiles/new/assistant` | AI profile authoring session from sample invoices and an optional blueprint. |
| | `/accounts` | Folders on disk vs profiles: unmapped, mapped, conflict, missing. Assign, unassign, create, rescan. |
| | `/models` | Templates by profile: candidates, approved, failed; confidence, usage, who created them. |
| | `/models/[id]` | A model's rules rendered as tables (header fields, region, columns, row classifiers, grouping, line-item fields), training set, versions, preview output. Clone, retire, delete. |
| | `/models/builder` | The visual builder. |
| | `/field-schemas`, `/output-specs` | Editors for the other two configuration layers, with clone and validate. |
| **System** | `/settings` | Provider and keys, models per task, thresholds, worker concurrency, watcher timing, log level, debug mode, danger zone. |
| | `/insights` | Totals, reconciliation rate, AI spend split into extraction vs training, 30-day volume and cost, monthly breakdown by model and by supplier. |
| | `/logs` | Processing audit trail and per-call token usage and cost. |
| | `/users`, `/account` | Admin user management; your own password and session. |
| | `/ai-calls`, `/evals` | Debug only: captured prompts and responses; the eval harness. |

Auth is a single layer: the user login. Sessions are HTTP-only cookies whose hash is stored in `auth_sessions` (`POLARIS_SESSION_TTL_DAYS`). Roles are `user` and `admin`; anything destructive or credential-touching requires admin. There is no machine API key on `/api/v1`; a service that calls the API signs in like a person.

## API

Interactive docs at <http://localhost:8000/docs>. The main groups:

| Group | Highlights |
|---|---|
| `/api/v1/auth` | `login`, `logout`, `me`, `change-password` |
| `/api/v1/invoices` | list with filters and facets, detail, jobs, logs, `upload`, `cancel`, `reject`, output and model-review downloads, `provenance` (where each delivered value came from), `purge` (debug) |
| `/api/v1/exceptions` | list, detail, partial output, PDF, `retry`, `resolve` |
| `/api/v1/profiles` | CRUD, `activate`/`retire`, `lint`, `validate`, `preview`, training invoices and status, `simple-hints`, and the `authoring/sessions` assistant |
| `/api/v1/models` | list, detail, `approve`/`activate`/`retire`, `clone`/`rollback`, `rules` (edit in place), training set, versions, usage, `draft/test` and `draft/eval-folder` for the builder |
| `/api/v1/intakes` | builder samples and the normalized page layout (`/{id}/layout`) the canvas renders |
| `/api/v1/accounts` | snapshot, `sync`, `assign`/`unassign`/`create` |
| `/api/v1/field-schemas`, `/api/v1/output-specs` | CRUD, clone, validate |
| `/api/v1/dashboard` | stats, volume, costs, monthly, by model, by supplier, AI calls |
| `/api/v1/settings` | runtime settings; `keys` to store or clear a provider key |
| `/api/v1/users` | admin user management |
| `/api/v1/pipeline` | jobs, logs, and the `live/{intake_id}` WebSocket |
| `/api/v1/debug` | `ai-calls` capture and the `evals` harness (debug only) |

Every `/api/v1` route except `auth/login` requires the session cookie.

## Testing and CI

```bash
ruff check src tests                 # lint (line length 120, py312)
pytest                               # unit + deterministic golden corpus; no AI key, SQLite in memory
pytest -m authoring                  # AI authoring end-to-end; needs a real key, spends money
pytest tests/test_fingerprint/       # one area
mypy src                             # strict; has a known backlog and is not a CI gate

cd frontend
npm run lint && npm run build        # the frontend CI gate
npm run test:e2e                     # Playwright against a running stack (see frontend/README.md)
```

**Golden corpus** (`tests/fixtures/corpus/<layout>/`): real PDFs, the correct deliverables, and a committed `model.json`. Three suites keep the engine honest: fingerprints are stable within a layout and distinct across layouts; the committed model reproduces the correct output for every PDF; and (manually) AI can author a model from one invoice that generalizes to the rest.

**Eval cases** (`eval_cases/<layout>/`): the larger labelled set the Evals page scores. Same folder shape plus `expected/*.xlsx` answer keys. The eval runner and the pipeline share one post-processing path, so a PDF plus a profile gives the same deliverable from either entry point.

**CI** (`.github/workflows/ci.yml`) runs four offline jobs on every push and pull request: `backend-lint`, `backend-test`, `frontend` (lint + build) and `docker-build`. AI authoring snapshots are refreshed on demand with `.github/workflows/authoring-manual.yml`, which needs the `POLARIS_OPENAI_API_KEY` repository secret and hands back the `model.json` files as an artifact for review.

## Configuration reference

All settings use the `ST_` prefix and come from the environment or `.env` (`src/polaris/config.py`). Values marked *runtime* can also be changed in **Settings** and are then stored in MySQL and applied live.

| Variable | Default | Purpose |
|---|---|---|
| `POLARIS_DATABASE_URL` | `mysql+pymysql://polaris:polaris@localhost:3306/polaris` | MySQL. Required in production; the Docker dev overlay sets it for you. |
| `POLARIS_REDIS_URL` | `redis://localhost:6379/0` | Celery broker and live-event pub/sub. |
| `POLARIS_SECRET_KEY` | empty | Fernet key that encrypts provider API keys stored in the DB. Generate once and keep. |
| `POLARIS_ADMIN_EMAIL`, `POLARIS_ADMIN_PASSWORD` | empty | First admin, created only while the users table is empty. |
| `POLARIS_SESSION_TTL_DAYS` | `7` | Login session lifetime. |
| `POLARIS_LLM_PROVIDER` | `openai` | `openai` or `anthropic` (*runtime*). |
| `POLARIS_OPENAI_API_KEY`, `POLARIS_ANTHROPIC_API_KEY` | empty | Environment fallback; a key saved in Settings wins. |
| `POLARIS_OPENAI_MODEL_EXTRACTION` / `_CLASSIFICATION` / `_MODEL_GENERATION` | `gpt-5.5` | Model per task (*runtime*). Used for either provider. |
| `POLARIS_OPENAI_MAX_OUTPUT_TOKENS` | `32768` | Must cover reasoning plus the JSON. |
| `POLARIS_AI_EXTRACTION_MODE` | `compact_chunked` | Chunked layout-text extraction; `legacy` sends whole pages. |
| `POLARIS_EXTRACTION_SEND_PAGE_IMAGES` | `true` | Attach page images only for pages with under `POLARIS_EXTRACTION_MIN_PAGE_TEXT_CHARS` characters. |
| `POLARIS_CONFIDENCE_THRESHOLD` | `0.75` | Minimum classification confidence (*runtime*). |
| `POLARIS_RECONCILIATION_VARIANCE_THRESHOLD` | `0.01` | Max line-item vs total variance before "needs review" (*runtime*). |
| `POLARIS_MODEL_AUTHORING_MAX_ATTEMPTS` | `3` | Author → execute → diff retries per training invoice. |
| `POLARIS_MODEL_VALIDATION_REQUIRED_SUCCESSES` / `_MAX_FAILURES` | `3` / `3` | Candidate validation policy (*runtime*). |
| `POLARIS_BLOCKING_CHECK_PAGE_THRESHOLD` | `100` | Page count above which rules are tried before reading every page. |
| `POLARIS_WORKER_CONCURRENCY` | `2` | Parallel pipeline jobs per worker (*runtime*). |
| `POLARIS_DATA_DIR`, `POLARIS_WORK_DIR` | `polaris_data`, `polaris_work` | The two roots above (Docker: `/data`, `/work`). |
| `POLARIS_ACCOUNTS_SCAN_DIR` | `<data_dir>/Invoices` | Root the Accounts scan walks. `POLARIS_ACCOUNTS_SYNC_TTL_HOURS` (`12`) controls the startup refresh. |
| `POLARIS_WATCHER_POLL_INTERVAL`, `POLARIS_WATCHER_STABLE_SECONDS` | `1.0`, `3.0` | Watcher timing (*runtime*). `POLARIS_WATCHER_REGISTRY_RESCAN_SECONDS` (`15`) re-reads profiles for new folders. |
| `POLARIS_MAX_UPLOAD_BYTES` | `100 MB` | Upload size cap. |
| `POLARIS_DEBUG` | `false` | Enables the purge endpoint, Danger zone, AI-call capture and the Evals page (*runtime*, admin only). |
| `POLARIS_LOG_LEVEL`, `POLARIS_LOG_FORMAT` | `INFO`, `json` | structlog output. |
| `POLARIS_PROFILE_DISCOVERY_*` | shadow on | A newer profile-authoring engine running alongside the current one during rollout. Leave as is unless working on it. |

`POLARIS_HOST_DATA_DIR`, `POLARIS_HOST_WORK_DIR`, `MYSQL_*` and `COMPOSE_PROJECT_NAME` are read by Docker Compose, not by the app.

**Debug mode is not a security control.** It is a DB-persisted runtime flag any admin can flip, so destructive and credential-touching routes are gated on the admin role, not on debug. Production is simply the default, `POLARIS_DEBUG=false`.

## Troubleshooting

| Symptom | What to check |
|---|---|
| Every invoice is *failed* with `401 … invalid_api_key` in the logs | The provider key is wrong or revoked. Replace it in **Settings → AI Configuration**, or in `.env` and restart. |
| The queue says *No invoice has run from a template yet* although a model is approved | The model's fingerprint no longer matches (profile fingerprint rules or document category edited after approval, or the fingerprinter changed). Run `python scripts/refingerprint_models.py` and apply. |
| Invoices land in *Needs review* with `layout drift` | The supplier changed the layout, or see the row above. Open the invoice, compare with the model's source, retrain or clone. |
| `Supplier profile has no output_path; output package was not copied` | The profile has no delivery folder. Assign one under **Accounts**; the package is still complete under `work_dir/completed/`. |
| Frontend shows 500s on `/api/v1/*` | The backend is not up on `:8000` yet, or `NEXT_PUBLIC_API_URL` points elsewhere. The dev proxy reports `ECONNREFUSED` in the Next.js terminal. |
| Playwright navigation specs time out against `npm run dev` | Routes compile on first visit; run with `--workers=1` or against the Docker frontend. |
| Celery on Windows exits immediately or never picks up tasks | Use `--pool=solo`. |
| `Access denied for user 'polaris'` | You are hitting a native MySQL on 3306; the Docker dev database is on **3307**. |
| Settings toggle for debug has no effect on the worker | Debug is a runtime setting read live; the `.env` value only seeds it. Give the worker a few seconds, or restart it. |
| Purge returns 403 | Debug mode is off, or you are not an admin. |
| Accounts page is stale after adding folders | Click **Sync**; discovery runs in the worker and the page reads the snapshot. |
| `Settings → Danger zone` is missing | Visible only when debug mode is on and you are an admin. |

## Further reading

- [`CLAUDE.md`](CLAUDE.md): architecture guide for working on the code.
- [`docs/DEPLOYMENT_WINDOWS_SERVER.md`](docs/DEPLOYMENT_WINDOWS_SERVER.md): production deployment on Windows Server with WSL2 and an external MySQL.
- [`docs/model-builder-guide-orange.md`](docs/model-builder-guide-orange.md) and [`docs/model-builder-guide-att.md`](docs/model-builder-guide-att.md): worked examples of building a template by hand.
- [`eval_cases/README.md`](eval_cases/README.md) and [`tests/fixtures/corpus/README.md`](tests/fixtures/corpus/README.md): how to add labelled invoices.
- [`frontend/README.md`](frontend/README.md): the UI codebase and the Playwright suite.

## License

Proprietary. Internal use only.
