# Polaris frontend

The operator UI for Polaris: a Next.js 16 (App Router) app that talks to the
FastAPI backend over `/api/v1`. Everything a user does, from
dropping an invoice to approving a template, happens here.

**Read [`AGENTS.md`](AGENTS.md) before writing code.** This is a pre-release
Next.js with breaking changes from the conventions in most training data and
tutorials; the authoritative API docs live in `node_modules/next/dist/docs/`.

## Run it

```bash
npm install
npm run dev        # http://localhost:3000, hot reload
```

`/api/v1/*` is proxied to the backend on `:8000` by a plain rewrite in
[`next.config.ts`](next.config.ts). Override the target with
`NEXT_PUBLIC_API_URL` in `.env.local`. The live pipeline socket is not
proxied (rewrites do not carry WebSocket upgrades); it connects straight to
`NEXT_PUBLIC_WS_URL`, default `ws://localhost:8000`.

```bash
npm run build      # production build; this is the CI gate together with lint
npm run lint       # eslint
npm start          # serve the production build
```

## Structure

| Path | What lives there |
|---|---|
| `src/app/` | One folder per route. Four sections: **Work** (`/invoices`, `/exceptions`, `/upload`), **Suppliers** (`/profiles`, `/accounts`), **Templates** (`/models`, `/models/builder`), **System** (`/insights`, `/settings`, `/logs`, `/users`, `/account`, plus `/ai-calls` and `/evals` when debug is on). |
| `src/components/layout/` | The shell: a 240px sidebar that lists every section, a phone-only top bar, the command palette (`Ctrl/Cmd+K`). `nav-config.ts` is the single source of navigation. |
| `src/components/brand/` | The star mark, the wordmark, and the mascot plus confetti used in empty states and on sign in. |
| `src/components/builder/` | The visual model builder (`/models/builder`): layout canvas plus editors for regions, columns, row classifiers, headers, grouping, tax and computed values. |
| `src/components/profiles/` | Profile editor tabs and the AI profile assistant. |
| `src/components/ui/` | shadcn/ui v4 primitives on top of Base UI. `data-table.tsx` is the one table every list goes through. |
| `src/hooks/` | TanStack Query hooks, one file per API area (`use-invoices`, `use-models`, …). |
| `src/lib/api/` | The typed fetch client. `src/types/` mirrors the backend schemas by hand; the profile type must be updated together with the backend (see the root `CLAUDE.md`). |
| `e2e/` | Playwright suite (see below). |
| `scripts/` | Screenshot and accessibility audit tooling (`shots.mjs`, `a11y-audit.mjs`, `portfolio-shots.mjs`), and the e2e runner. |

## Design language

Measured from family.co and documented on the design canvas's Foundations board.
The tokens live in `src/app/globals.css`; the primitives in `src/components/ui/`
wear them, so a page rarely needs its own colours.

- A white page. Surfaces are beige (`bg-card`) with a 1px inset ring
  (`shadow-[inset_0_0_0_1px_var(--ring-card)]`), never a drop shadow. The one
  floating shadow (`--shadow-overlay`) is for a single callout per screen.
- Corners: `rounded-3xl` (24px) cards, `rounded-full` pills, `rounded-md` (8px)
  inputs, `rounded-sm` (6px) sidebar rows.
- Buttons are pills. `variant="solid"` is the black pill, one per screen;
  `hairline` is the beige pill for everything else; `text` is quiet.
- Status is always a pill (`Badge`): `success` for free and done, `warning` for
  paid and drift, `destructive` when a person is needed, `cut` for in progress.
- One accent per section, spent only on the eyebrow label above the page title
  and on check lists: `text-section-work`, `-suppliers`, `-templates`, `-system`.
  `PageHeader` derives the eyebrow from the route.
- Type: Inter for the UI (`--font-sans`), Plus Jakarta Sans for hero copy and
  big numbers (`font-display`), JetBrains Mono for ids, filenames and money.
- Motion: `.fade-up` entrances on the expo-out curve (`ease-out-expo`), 100ms
  colour changes, buttons press to 97%. `prefers-reduced-motion` turns it off.
- The mascot (`Mascot`, `Confetti`) belongs in empty states, the upload zone and
  sign in. Never beside data.

Conventions worth knowing:

- A `Button` given `render={<Link …/>}` or `render={<a download …/>}` renders
  as that element; the wrapper sets Base UI's `nativeButton` for you.
- Every table route goes through `DataTable`; do not hand-roll a `<table>`.
- Pages poll every 3 s while any invoice is `received`/`processing`, and the
  invoice detail also subscribes to the pipeline WebSocket.
- Accessibility is tested: every focusable control needs an accessible name,
  and no route may scroll horizontally on a phone.

## End-to-end tests

The Playwright suite runs against an already running stack (backend, worker,
Redis, MySQL and this dev server or the Docker frontend). It never starts one.

```bash
# One command for either stack. It seeds a throwaway admin first: through
# `docker compose exec backend` when the Docker dev stack is up, otherwise
# through the repo's .venv Python against POLARIS_DATABASE_URL (export it for a
# native stack), then runs the suite.
npm run test:e2e

# Or skip seeding and use an existing admin account.
E2E_EMAIL=you@example.com E2E_PASSWORD=… npx playwright test
```

Projects: `setup` logs in once and stores the cookie; `chromium` runs the
authenticated specs; `chromium-anonymous` checks the login boundary;
`mobile` runs the responsive checks on a Pixel 7 profile.

Against `next dev` the suite is slower than against a production build
because routes compile on first visit. If navigation specs time out under
the default parallelism, run them serially (`--workers=1`); that is load,
not a product failure.

`npm run test:e2e:ui` opens the Playwright UI; `npm run test:e2e:report`
opens the last HTML report. Traces and screenshots for failures land in
`e2e/.artifacts/`.
