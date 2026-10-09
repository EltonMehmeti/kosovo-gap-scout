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
