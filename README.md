# Kosovo Gap Scout

Daily AI research engine that looks for business models proven elsewhere and missing in Kosovo.
Spec: docs/superpowers/specs/2026-10-09-kosovo-gap-scout-design.md

## Local setup
    uv sync --extra dev
    cp .env.example .env   # fill in keys
    uv run scout init-db
    uv run scout seed
    uv run scout run --budget 0.50 --dry-run
    uv run scout run --budget 0.50

## Tests
    uv run pytest                 # unit tests, no network
    TEST_DATABASE_URL=... uv run pytest -m db
    uv run pytest -m network      # live smoke tests, by hand

## Source notes

- **Google Play top-free chart (checked 2026-10-09):** `store/apps/collection/topselling_free?gl=XK` now returns a page with no app links. `scout.sources.play` reads `store/apps/top?gl=XK&hl=en` instead. That page lists the top-free chart first, in rank order. It also contains other charts further down, so keep `limit` at 25 or below. Re-check this if `fetch_top_free` starts returning 0 entries.

## Deployment (Render cron + Neon)
- Blueprint: `render.yaml` (cron `0 6 * * *`, `uv run scout run`).
- Secrets live only in Render env vars and `.env` (never committed).
- Database setup runs **from your machine**, not on Render (there is no pre-deploy migration step): put the
  Neon `DATABASE_URL` in your local `.env`, then run `uv run scout init-db` and `uv run scout seed`. Re-run
  `init-db` locally after pulling a new migration.
- Hand runs (Phase 0, until 2026-10-18): press **Trigger Run** on the `scout-daily` cron job in the Render
  dashboard, or run `uv run scout run --budget 1.00` locally against Neon; then read `scout brief`.
- Budget: `render.yaml` starts at `SCOUT_DAILY_BUDGET_EUR=1.00`; raise it to `3.00` in the Render dashboard on
  2026-10-19 when Foundation starts.
- Daily: read the brief (10 min). Sunday: `scout field-check answer <id> "<text>"` for each open check.
- Phase changes: `scout set-phase verification` (2026-11-16), `scout set-phase maintenance` (2026-12-14).
  A phase set with `scout set-phase` is stored in the database and overrides the `SCOUT_PHASE` env var
  (only `scout run --phase` takes precedence over it).
- Source notes: record here any live deviation found by `tests/test_live.py` (Places region code, Play chart HTML).

## Dashboard (Render web service `scout-dashboard`)

Mobile-first pages: Today, Gaps, Field checks, Pipeline, Knowledge, Journal, Costs and Settings.
Every button goes through `scout/founder.py` and is journaled, and the CLI uses the same functions.

- Local: `DASHBOARD_TOKEN=dev uv run uvicorn scout.web.main:app --reload`, then open http://127.0.0.1:8000.
- Render: set `DATABASE_URL` and `DASHBOARD_TOKEN`. Generate the token with
  `python -c "import secrets; print(secrets.token_urlsafe(32))"`. The dashboard does not need
  `ANTHROPIC_API_KEY`.
- Changing `DASHBOARD_TOKEN` logs out every browser.
- "Verify" queues one re-verification of the gap; it never marks a gap verified by hand (spec A10).
  "Kill" sticks until you press "Reopen".
- Today's cap (Costs page or `scout set-cap 1.50`) replaces the phase cap for that Kosovo day only.
