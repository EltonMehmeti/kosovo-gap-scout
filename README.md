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
