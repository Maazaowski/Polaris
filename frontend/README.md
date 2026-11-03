# Stencil frontend

The operator UI for Stencil: a Next.js 16 (App Router) app that talks to the
FastAPI backend over `/api/v1`. Everything a user does with Stencil, from
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
| `src/app/` | One folder per route. Three sections: **Work** (`/invoices`, `/exceptions`, `/upload`), **Suppliers** (`/profiles`, `/accounts`, `/models`, `/field-schemas`, `/output-specs`), **System** (`/settings`, `/insights`, `/logs`, `/users`, `/account`, plus `/ai-calls` and `/evals` when debug is on). |
| `src/components/layout/` | The shell: section rail, sidebar, header, command palette (`Ctrl/Cmd+K`). `nav-config.ts` is the single source of navigation. |
| `src/components/builder/` | The visual model builder (`/models/builder`): layout canvas plus editors for regions, columns, row classifiers, headers, grouping, tax and computed values. |
| `src/components/profiles/` | Profile editor tabs and the AI profile assistant. |
| `src/components/ui/` | shadcn/ui v4 primitives on top of Base UI. `data-table.tsx` is the one table every list goes through. |
| `src/hooks/` | TanStack Query hooks, one file per API area (`use-invoices`, `use-models`, …). |
| `src/lib/api/` | The typed fetch client. `src/types/` mirrors the backend schemas by hand; the profile type must be updated together with the backend (see the root `CLAUDE.md`). |
| `e2e/` | Playwright suite (see below). |
| `scripts/` | Screenshot and accessibility audit tooling (`shots.mjs`, `a11y-audit.mjs`, `portfolio-shots.mjs`), and the e2e runner. |

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
# through the repo's .venv Python against ST_DATABASE_URL (export it for a
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
