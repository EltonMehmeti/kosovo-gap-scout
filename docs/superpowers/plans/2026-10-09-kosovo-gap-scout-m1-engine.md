# Kosovo Gap Scout — Milestone 1 (Engine) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the daily research engine — Director, budget guard, Tier A sources, research worker, chart diff, extractor, Strategist + Critic, Editor, CLI — running as a Render cron against Neon, so the scout starts learning Kosovo on 2026-10-18.

**Architecture:** One Python package `scout` with a Postgres-backed knowledge base and task queue. A cron entrypoint (`scout run`) plans the day's tasks deterministically, runs them one at a time through the Anthropic SDK tool runner (Sonnet 5.5 + server web tools + custom knowledge-base tools), scores gaps with Opus 5.5 structured outputs, and writes a Markdown brief and a journal entry. Every paid call passes through a budget guard that records actual cost from `response.usage`.

**Tech Stack:** Python 3.12, `uv`, `anthropic>=1,<2`, `httpx`, `pydantic` 2, `pydantic-settings`, SQLAlchemy 2, Alembic, `psycopg[binary]` 3, `typer`, `google-play-scraper`, `pytest`, `ruff`. Neon Postgres. Render cron.

**Spec:** `docs/superpowers/specs/2026-10-09-kosovo-gap-scout-design.md` (Part B is the platform design; this plan implements B1–B10, B12–B16 for Milestone 1; B11 dashboard and Tier B/C sources are M2/M4).

## Global Constraints

- Python `>=3.12`; `anthropic>=1,<2` (the SDK is built on `httpx2` — our own HTTP code imports `httpx`; never pass an `httpx` client to the Anthropic client).
- Model IDs exactly: `claude-sonnet-5-5` (worker, editor), `claude-opus-5-5` (strategist, critic, deep-dive, director review), `claude-haiku-5-5` (extractor). Never send `thinking: {"type": "disabled"}` or `budget_tokens`; control depth with `output_config={"effort": ...}` only. Never send `tool_choice` of type `any`/`tool`.
- Server tools exactly `{"type": "web_search_20260209", "name": "web_search", "max_uses": N}` and `{"type": "web_fetch_20260209", "name": "web_fetch", "max_uses": N}`.
- Every Claude call, Places call and (M2) Apify run goes through `BudgetGuard.check()` before and `BudgetGuard.record()` after. Costs are EUR `Decimal` with 6 decimal places; the ledger `day` is the run's Kosovo local date (`Europe/Belgrade`), never `datetime.now().date()` at insert time.
- System prompts contain no dates, UUIDs, counters or unsorted JSON; all `json.dumps` in prompt-building code use `sort_keys=True`. The date and volatile context go in the first user message.
- Public, logged-out data only; no personal data of natural persons is stored (no reviewer names, no commenters). Facts store business entities, statistics and the founder's own answers.
- Database URLs are normalised to `postgresql+psycopg://`. All timestamps stored UTC (`timezone=True`).
- Tests: `pytest` with no network by default (`-m "not network"`); DB tests need `TEST_DATABASE_URL` and skip with a message when it is missing.
- Commit after every task; `ruff check .` and `ruff format --check .` must pass before each commit.

## Review Focus

Failure modes the spec implies but the task tests would otherwise not exercise — each has a pinned test in the owning task:

1. **Hallucinated absence** — a gap with presence level `absent` but no `presence_check` fact must score ≤ 12 on Kosovo absence and confidence ≤ 0.5 (Task 17, `test_absence_capped_without_presence_check`).
2. **Budget breach inside a tool-runner task** — the worker must stop iterating when the remaining budget cannot pay for another step, and still record what was spent (Task 14, `test_worker_stops_when_budget_tight`).
3. **Duplicate knowledge** — the same claim observed on two days must refresh one `facts` row, not create two; a gap proposed twice with different capitalisation must be one gap (Task 4 `test_upsert_fact_refreshes_same_claim`, Task 4 `test_propose_gap_dedupes_by_title`).
4. **Day boundary / timezone** — spend is attributed to the run's local day passed explicitly; a cost recorded at 23:30 UTC on day D counts for day D+1 in Kosovo only if the run says so (Task 6, `test_spent_uses_explicit_day`).
5. **Truncated or paused model turns** — `pause_turn` restarts the runner with mirrored history (max 3 restarts) and `max_tokens` stops are reported, not silently accepted as results (Task 14, `test_worker_restarts_on_pause_turn`, `test_worker_reports_max_tokens`).
6. **Neon URL and driver** — `postgresql://…?sslmode=require&channel_binding=require` must become `postgresql+psycopg://…` with the query string intact (Task 1, `test_normalize_db_url_keeps_query`).
7. **Chart diff keying** — Apple and Play apps are compared only within the same store by store id, never by name across stores (Task 16, `test_chart_diff_never_mixes_stores`).

## File Structure

```
pyproject.toml                 project metadata, deps, ruff/pytest config, `scout` script
.env.example                   documented env vars
.gitignore
README.md                      how to run locally and deploy
alembic.ini
alembic/env.py                 reads SCOUT settings for the URL
alembic/versions/<rev>_init.py autogenerated from models
render.yaml                    cron service blueprint
scout/__init__.py
scout/config.py                Settings, normalize_db_url, get_settings
scout/seeds.py                 SECTORS, CULTURE_THEMES, SOURCES, seed_all
scout/cli.py                   typer app
scout/db/__init__.py
scout/db/base.py               Base, JSONType, make_engine, make_session_factory
scout/db/models.py             ORM models (B4)
scout/db/repo.py               repository functions, FactIn, CostRecord, ChartEntryIn
scout/budget/__init__.py
scout/budget/pricing.py        MODEL_PRICES_USD_PER_MTOK, usage_units, llm_cost_usd, to_eur
scout/budget/guard.py          BudgetGuard, BudgetExceeded
scout/llm/__init__.py
scout/llm/gateway.py           LLM: parse, create_text, record_message
scout/sources/__init__.py
scout/sources/types.py         ChartEntry, AppHit, PlaceHit, PlacesResult
scout/sources/askdata.py       AskDataClient
scout/sources/apple.py         fetch_top_free, search_apps
scout/sources/play.py          fetch_top_free, search_apps
scout/sources/places.py        PlacesClient
scout/sources/web.py           web_tools()
scout/worker/__init__.py
scout/worker/tools.py          ToolContext, *_impl functions, build_tools
scout/worker/profiles.py       Profile, PROFILES, WORKER_RULES, build_system, build_brief
scout/worker/research.py       ResearchWorker, TaskOutcome
scout/worker/chart_diff.py     run_chart_diff, classify_and_record
scout/extract/__init__.py
scout/extract/schemas.py       AppClassification
scout/extract/extractor.py     Extractor
scout/strategy/__init__.py
scout/strategy/schemas.py      ComponentScores, GapAssessment, StrategistOutput, CriticOutput, DirectorReview
scout/strategy/rubric.py       PRESENCE_CAP, HARD_FILTERS, score_gap, cap_confidence, needs_field_check
scout/strategy/strategist.py   Strategist
scout/editor/__init__.py
scout/editor/brief.py          collect_inputs, render_brief, write_brief
scout/director/__init__.py
scout/director/planner.py      PlannerState, PlannedTask, PHASE_RULES, plan_tasks
scout/director/run.py          run_once, RunSummary
tests/conftest.py              settings fixture, db fixtures (skip without TEST_DATABASE_URL)
tests/fakes.py                 FakeUsage, FakeMessage, FakeParsed, FakeClient, FakeRunner
tests/test_*.py                one file per module
```

---

### Task 1: Project scaffold and settings

**Files:**
- Create: `pyproject.toml`, `.env.example`, `.gitignore`, `README.md`, `scout/__init__.py`, `scout/config.py`
- Test: `tests/test_config.py`

**Interfaces:**
- Produces: `scout.config.Settings` (fields: `anthropic_api_key: str`, `database_url: str`, `google_places_api_key: str | None`, `apify_token: str | None`, `phase: str`, `daily_budget_eur: Decimal`, `run_max_minutes: int`, `usd_to_eur: Decimal`, `timezone: str`, `director_review: bool`), `normalize_db_url(url: str) -> str`, `get_settings() -> Settings`.

- [ ] **Step 1: Initialise the repository and tooling**

```bash
cd /home/elton/PycharmProjects/ideas
git init -b main
uv init --no-readme --package --name kosovo-gap-scout --python 3.12 .  # creates pyproject; we overwrite it next
```

If `uv init` complains that `pyproject.toml` exists, continue — Step 2 replaces it.

- [ ] **Step 2: Write `pyproject.toml`**

```toml
[project]
name = "kosovo-gap-scout"
version = "0.1.0"
description = "Daily AI scout that finds proven business models missing in Kosovo"
requires-python = ">=3.12"
dependencies = [
  "anthropic>=1,<2",
  "httpx>=0.27",
  "pydantic>=2.7",
  "pydantic-settings>=2.3",
  "sqlalchemy>=2.0.30",
  "alembic>=1.13",
  "psycopg[binary]>=3.1",
  "typer>=0.12",
  "rich>=13.7",
  "google-play-scraper>=1.2.7",
]

[project.optional-dependencies]
dev = ["pytest>=8", "pytest-cov>=5", "ruff>=0.5"]

[project.scripts]
scout = "scout.cli:app"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["scout"]

[tool.ruff]
line-length = 100
target-version = "py312"

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B"]

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-m 'not network'"
markers = [
  "network: hits real external services (skipped by default)",
  "db: needs TEST_DATABASE_URL",
]
```

- [ ] **Step 3: Write `.gitignore`, `.env.example`, `README.md`**

`.gitignore`:
```
.venv/
__pycache__/
*.pyc
.env
.pytest_cache/
.ruff_cache/
dist/
```

`.env.example`:
```
ANTHROPIC_API_KEY=sk-ant-...
DATABASE_URL=postgresql://user:pass@host/db?sslmode=require
TEST_DATABASE_URL=postgresql://user:pass@host/scout_test?sslmode=require
GOOGLE_PLACES_API_KEY=
APIFY_TOKEN=
SCOUT_PHASE=foundation
SCOUT_DAILY_BUDGET_EUR=3.00
SCOUT_RUN_MAX_MINUTES=50
SCOUT_USD_TO_EUR=0.92
SCOUT_TIMEZONE=Europe/Belgrade
SCOUT_DIRECTOR_REVIEW=true
```

`README.md`:
```markdown
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
```

- [ ] **Step 4: Write the failing test for settings**

`tests/test_config.py`:
```python
from decimal import Decimal

from scout.config import Settings, normalize_db_url


def test_normalize_db_url_keeps_query():
    url = "postgresql://u:p@ep-x.eu-central-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require"
    assert normalize_db_url(url) == (
        "postgresql+psycopg://u:p@ep-x.eu-central-1.aws.neon.tech/neondb"
        "?sslmode=require&channel_binding=require"
    )


def test_normalize_db_url_handles_postgres_scheme_and_idempotent():
    assert normalize_db_url("postgres://u:p@h/db") == "postgresql+psycopg://u:p@h/db"
    assert normalize_db_url("postgresql+psycopg://u:p@h/db") == "postgresql+psycopg://u:p@h/db"


def test_settings_read_env(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@h/db")
    monkeypatch.setenv("SCOUT_DAILY_BUDGET_EUR", "1.50")
    monkeypatch.setenv("SCOUT_PHASE", "verification")
    s = Settings(_env_file=None)
    assert s.anthropic_api_key == "sk-test"
    assert s.database_url == "postgresql+psycopg://u:p@h/db"
    assert s.daily_budget_eur == Decimal("1.50")
    assert s.phase == "verification"
    assert s.timezone == "Europe/Belgrade"
    assert s.director_review is True
```

- [ ] **Step 5: Run the test to verify it fails**

Run: `uv sync --extra dev && uv run pytest tests/test_config.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'scout.config'`

- [ ] **Step 6: Write `scout/__init__.py` and `scout/config.py`**

`scout/__init__.py`:
```python
"""Kosovo Gap Scout."""

__version__ = "0.1.0"
```

`scout/config.py`:
```python
from __future__ import annotations

from decimal import Decimal
from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def normalize_db_url(url: str) -> str:
    """Rewrite any Postgres URL so SQLAlchemy uses the psycopg 3 driver."""
    for prefix in ("postgresql://", "postgres://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix):]
    return url


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="SCOUT_", env_file=".env", extra="ignore", populate_by_name=True
    )

    anthropic_api_key: str = Field(alias="ANTHROPIC_API_KEY")
    database_url: str = Field(alias="DATABASE_URL")
    google_places_api_key: str | None = Field(default=None, alias="GOOGLE_PLACES_API_KEY")
    apify_token: str | None = Field(default=None, alias="APIFY_TOKEN")

    phase: str = "foundation"
    daily_budget_eur: Decimal = Decimal("3.00")
    run_max_minutes: int = 50
    usd_to_eur: Decimal = Decimal("0.92")
    timezone: str = "Europe/Belgrade"
    director_review: bool = True

    @field_validator("database_url")
    @classmethod
    def _normalize(cls, v: str) -> str:
        return normalize_db_url(v)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
```

- [ ] **Step 7: Run the tests to verify they pass**

Run: `uv run pytest tests/test_config.py -v`
Expected: 3 PASSED

- [ ] **Step 8: Lint and commit**

```bash
uv run ruff check . && uv run ruff format .
git add -A
git commit -m "chore: scaffold kosovo-gap-scout with settings"
```

---

### Task 2: Pricing and cost arithmetic

**Files:**
- Create: `scout/budget/__init__.py`, `scout/budget/pricing.py`
- Test: `tests/test_pricing.py`

**Interfaces:**
- Produces: `ModelPrices` dataclass; `MODEL_PRICES_USD_PER_MTOK: dict[str, ModelPrices]`; `WEB_SEARCH_USD_PER_CALL: Decimal`; `usage_units(usage: object) -> dict[str, int]` (keys `input_tokens, output_tokens, cache_write_tokens, cache_read_tokens, web_search_requests`); `llm_cost_usd(model: str, units: dict[str, int]) -> Decimal`; `to_eur(usd: Decimal, usd_to_eur: Decimal) -> Decimal` (quantised to 6 dp).

- [ ] **Step 1: Write the failing tests**

`tests/test_pricing.py`:
```python
from decimal import Decimal
from types import SimpleNamespace

import pytest

from scout.budget.pricing import llm_cost_usd, to_eur, usage_units


def test_usage_units_reads_sdk_usage_defensively():
    usage = SimpleNamespace(
        input_tokens=1000,
        output_tokens=200,
        cache_creation_input_tokens=300,
        cache_read_input_tokens=5000,
        server_tool_use=SimpleNamespace(web_search_requests=3),
    )
    assert usage_units(usage) == {
        "input_tokens": 1000,
        "output_tokens": 200,
        "cache_write_tokens": 300,
        "cache_read_tokens": 5000,
        "web_search_requests": 3,
    }


def test_usage_units_missing_fields_default_zero():
    usage = SimpleNamespace(input_tokens=10, output_tokens=5)
    units = usage_units(usage)
    assert units["cache_read_tokens"] == 0
    assert units["web_search_requests"] == 0


def test_sonnet_cost_arithmetic():
    units = {
        "input_tokens": 1_000_000,
        "output_tokens": 100_000,
        "cache_write_tokens": 0,
        "cache_read_tokens": 1_000_000,
        "web_search_requests": 10,
    }
    # 2.00 + 1.00 + 0.20 + 0.10
    assert llm_cost_usd("claude-sonnet-5-5", units) == Decimal("3.300000")


def test_haiku_and_opus_prices():
    units = {"input_tokens": 1_000_000, "output_tokens": 0, "cache_write_tokens": 0,
             "cache_read_tokens": 0, "web_search_requests": 0}
    assert llm_cost_usd("claude-haiku-5-5", units) == Decimal("0.100000")
    assert llm_cost_usd("claude-opus-5-5", units) == Decimal("4.000000")


def test_unknown_model_raises():
    with pytest.raises(KeyError):
        llm_cost_usd("claude-unknown", {"input_tokens": 1})


def test_to_eur_quantises():
    assert to_eur(Decimal("1"), Decimal("0.92")) == Decimal("0.920000")
    assert to_eur(Decimal("0.0000001"), Decimal("0.92")) == Decimal("0.000000")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_pricing.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'scout.budget'`

- [ ] **Step 3: Write the pricing module**

`scout/budget/__init__.py`: empty file.

`scout/budget/pricing.py`:
```python
"""Unit prices and cost arithmetic.

Prices are USD per million tokens as published for the Claude 5.5 family on
2026-10-09 (claude-api skill). Check platform.claude.com/pricing monthly; the
Costs page compares these estimates with the console bill.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

MTOK = Decimal(1_000_000)
SIX_DP = Decimal("0.000001")


@dataclass(frozen=True)
class ModelPrices:
    input_usd: Decimal
    output_usd: Decimal
    cache_write_usd: Decimal
    cache_read_usd: Decimal


MODEL_PRICES_USD_PER_MTOK: dict[str, ModelPrices] = {
    "claude-opus-5-5": ModelPrices(Decimal("4"), Decimal("20"), Decimal("5"), Decimal("0.20")),
    "claude-sonnet-5-5": ModelPrices(Decimal("2"), Decimal("10"), Decimal("2.5"), Decimal("0.20")),
    "claude-haiku-5-5": ModelPrices(
        Decimal("0.10"), Decimal("0.50"), Decimal("0.125"), Decimal("0.01")
    ),
}

WEB_SEARCH_USD_PER_CALL = Decimal("0.01")  # $10 per 1,000 searches

UNIT_KEYS = (
    "input_tokens",
    "output_tokens",
    "cache_write_tokens",
    "cache_read_tokens",
    "web_search_requests",
)


def usage_units(usage: object) -> dict[str, int]:
    """Flatten an SDK `usage` object into integer units, tolerating missing fields."""
    server = getattr(usage, "server_tool_use", None)
    return {
        "input_tokens": int(getattr(usage, "input_tokens", 0) or 0),
        "output_tokens": int(getattr(usage, "output_tokens", 0) or 0),
        "cache_write_tokens": int(getattr(usage, "cache_creation_input_tokens", 0) or 0),
        "cache_read_tokens": int(getattr(usage, "cache_read_input_tokens", 0) or 0),
        "web_search_requests": int(getattr(server, "web_search_requests", 0) or 0),
    }


def llm_cost_usd(model: str, units: dict[str, int]) -> Decimal:
    p = MODEL_PRICES_USD_PER_MTOK[model]  # KeyError on unknown model is intentional
    g = units.get
    usd = (
        Decimal(g("input_tokens", 0)) * p.input_usd
        + Decimal(g("output_tokens", 0)) * p.output_usd
        + Decimal(g("cache_write_tokens", 0)) * p.cache_write_usd
        + Decimal(g("cache_read_tokens", 0)) * p.cache_read_usd
    ) / MTOK
    usd += Decimal(g("web_search_requests", 0)) * WEB_SEARCH_USD_PER_CALL
    return usd.quantize(SIX_DP, rounding=ROUND_HALF_UP)


def to_eur(usd: Decimal, usd_to_eur: Decimal) -> Decimal:
    return (usd * usd_to_eur).quantize(SIX_DP, rounding=ROUND_HALF_UP)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_pricing.py -v`
Expected: 6 PASSED

- [ ] **Step 5: Commit**

```bash
uv run ruff check . && uv run ruff format .
git add -A && git commit -m "feat(budget): model price table and cost arithmetic"
```

---

### Task 3: Database models, Alembic, test database fixtures

**Files:**
- Create: `scout/db/__init__.py`, `scout/db/base.py`, `scout/db/models.py`, `alembic.ini`, `alembic/env.py`, `alembic/script.py.mako` (generated), `alembic/versions/<rev>_init.py` (generated), `tests/conftest.py`, `docker-compose.test.yml`
- Test: `tests/test_models.py`

**Interfaces:**
- Produces: `scout.db.base.Base`, `JSONType`, `make_engine(url: str)`, `make_session_factory(engine) -> sessionmaker[Session]`; ORM classes in `scout.db.models`: `Source, Digest, Sector, Business, ProvenModel, Gap, GapAssessment, FieldCheck, Fact, Task, Run, Cost, JournalEntry, Scorecard, AppChartSnapshot, Brief, Setting` with the columns below.
- Test fixtures: `db_engine`, `db_session` (function-scoped, tables truncated before each test), `settings` (Settings with dummy key and the test URL).

- [ ] **Step 1: Provide a test database**

Option A (Neon): in the Neon console create branch `test` of the project database and copy its connection string into `.env` as `TEST_DATABASE_URL`.
Option B (local):

`docker-compose.test.yml`:
```yaml
services:
  db:
    image: postgres:16
    environment:
      POSTGRES_USER: scout
      POSTGRES_PASSWORD: scout
      POSTGRES_DB: scout_test
    ports: ["55432:5432"]
```
Run `docker compose -f docker-compose.test.yml up -d` and set `TEST_DATABASE_URL=postgresql://scout:scout@localhost:55432/scout_test`.

- [ ] **Step 2: Write the failing test**

`tests/test_models.py`:
```python
import pytest
from sqlalchemy import inspect

pytestmark = pytest.mark.db

EXPECTED_TABLES = {
    "sources", "digests", "sectors", "businesses", "proven_models", "gaps",
    "gap_assessments", "field_checks", "facts", "tasks", "runs", "costs",
    "journal", "scorecard", "app_chart_snapshots", "briefs", "settings",
}


def test_all_tables_exist(db_engine):
    names = set(inspect(db_engine).get_table_names())
    assert EXPECTED_TABLES <= names


def test_facts_hash_is_unique(db_session):
    from datetime import UTC, datetime, timedelta

    from sqlalchemy.exc import IntegrityError

    from scout.db.models import Fact

    now = datetime.now(UTC)
    kwargs = dict(hash="h1", entity_type="sector", entity_key="pets", claim="c",
                  confidence=0.5, source_name="web", observed_at=now,
                  expires_at=now + timedelta(days=1))
    db_session.add(Fact(**kwargs))
    db_session.commit()
    db_session.add(Fact(**kwargs))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()
```

- [ ] **Step 3: Write `tests/conftest.py`**

```python
import os
from decimal import Decimal

import pytest
from sqlalchemy import text

from scout.config import Settings, normalize_db_url
from scout.db.base import Base, make_engine, make_session_factory


def pytest_collection_modifyitems(config, items):
    if os.environ.get("TEST_DATABASE_URL"):
        return
    skip = pytest.mark.skip(reason="TEST_DATABASE_URL not set; database tests skipped")
    for item in items:
        if "db" in item.keywords:
            item.add_marker(skip)


@pytest.fixture(scope="session")
def test_db_url() -> str:
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL not set")
    return normalize_db_url(url)


@pytest.fixture(scope="session")
def db_engine(test_db_url):
    engine = make_engine(test_db_url)
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def db_session(db_engine):
    factory = make_session_factory(db_engine)
    with db_engine.begin() as conn:
        tables = ", ".join(t.name for t in Base.metadata.sorted_tables)
        conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
    session = factory()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture
def settings(test_db_url) -> Settings:
    return Settings(
        _env_file=None,
        ANTHROPIC_API_KEY="sk-test",
        DATABASE_URL=test_db_url,
        daily_budget_eur=Decimal("3.00"),
    )
```

- [ ] **Step 4: Run the test to verify it fails**

Run: `TEST_DATABASE_URL=<url> uv run pytest tests/test_models.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'scout.db'`

- [ ] **Step 5: Write `scout/db/base.py`**

```python
from __future__ import annotations

from sqlalchemy import JSON, create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

JSONType = JSON().with_variant(JSONB(), "postgresql")


class Base(DeclarativeBase):
    pass


def make_engine(url: str):
    return create_engine(url, pool_pre_ping=True, future=True)


def make_session_factory(engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False, class_=Session)
```

- [ ] **Step 6: Write `scout/db/models.py`**

```python
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from scout.db.base import Base, JSONType

MONEY = Numeric(12, 6)


class Source(Base):
    __tablename__ = "sources"
    id: Mapped[int] = mapped_column(primary_key=True)
    tier: Mapped[str] = mapped_column(String(1))
    name: Mapped[str] = mapped_column(String(80), unique=True)
    kind: Mapped[str] = mapped_column(String(40))
    base_url: Mapped[str | None] = mapped_column(Text)
    ttl_hours: Mapped[int] = mapped_column(Integer, default=24 * 30)
    cost_per_call_eur: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0"))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    config: Mapped[dict | None] = mapped_column(JSONType)
    last_ok_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failure_count: Mapped[int] = mapped_column(Integer, default=0)


class Digest(Base):
    __tablename__ = "digests"
    key: Mapped[str] = mapped_column(String(120), primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    body_md: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    token_estimate: Mapped[int] = mapped_column(Integer, default=0)


class Sector(Base):
    __tablename__ = "sectors"
    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(80), unique=True)
    name_en: Mapped[str] = mapped_column(String(200))
    name_sq: Mapped[str | None] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(20), default="unmapped")
    presence_level: Mapped[str | None] = mapped_column(String(20))
    priority: Mapped[int] = mapped_column(Integer, default=50)
    last_mapped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_hunted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Business(Base):
    __tablename__ = "businesses"
    __table_args__ = (Index("ux_business_sector_name", "sector_id", func.lower("name"), unique=True),)
    id: Mapped[int] = mapped_column(primary_key=True)
    sector_id: Mapped[int] = mapped_column(ForeignKey("sectors.id"))
    name: Mapped[str] = mapped_column(String(200))
    kind: Mapped[str] = mapped_column(String(20), default="local")
    city: Mapped[str | None] = mapped_column(String(80))
    channels: Mapped[dict | None] = mapped_column(JSONType)
    note: Mapped[str | None] = mapped_column(Text)
    first_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ProvenModel(Base):
    __tablename__ = "proven_models"
    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(120), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    sector_id: Mapped[int] = mapped_column(ForeignKey("sectors.id"))
    description: Mapped[str] = mapped_column(Text)
    markets: Mapped[list] = mapped_column(JSONType, default=list)
    business_model: Mapped[str | None] = mapped_column(Text)
    source_urls: Mapped[list] = mapped_column(JSONType, default=list)
    nearby_count: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Gap(Base):
    __tablename__ = "gaps"
    __table_args__ = (Index("ux_gap_sector_title", "sector_id", func.lower("title"), unique=True),)
    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    sector_id: Mapped[int] = mapped_column(ForeignKey("sectors.id"))
    proven_model_id: Mapped[int | None] = mapped_column(ForeignKey("proven_models.id"))
    hypothesis_md: Mapped[str] = mapped_column(Text, default="")
    presence_level: Mapped[str] = mapped_column(String(20), default="unknown")
    why_not_yet_md: Mapped[str] = mapped_column(Text, default="")
    test_plan_md: Mapped[str] = mapped_column(Text, default="")
    score_total: Mapped[int] = mapped_column(Integer, default=0)
    score_components: Mapped[dict | None] = mapped_column(JSONType)
    confidence: Mapped[float] = mapped_column(default=0.3)
    status: Mapped[str] = mapped_column(String(20), default="candidate")
    critic_flag: Mapped[str | None] = mapped_column(String(40))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_assessed_run_id: Mapped[int | None] = mapped_column(Integer)


class GapAssessment(Base):
    __tablename__ = "gap_assessments"
    id: Mapped[int] = mapped_column(primary_key=True)
    gap_id: Mapped[int] = mapped_column(ForeignKey("gaps.id"))
    run_id: Mapped[int | None] = mapped_column(Integer)
    model: Mapped[str] = mapped_column(String(60))
    strategist: Mapped[dict | None] = mapped_column(JSONType)
    critic: Mapped[dict | None] = mapped_column(JSONType)
    score_total: Mapped[int] = mapped_column(Integer)
    confidence: Mapped[float] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class FieldCheck(Base):
    __tablename__ = "field_checks"
    id: Mapped[int] = mapped_column(primary_key=True)
    gap_id: Mapped[int | None] = mapped_column(ForeignKey("gaps.id"))
    question: Mapped[str] = mapped_column(Text)
    why: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(12), default="open")
    answer: Mapped[str | None] = mapped_column(Text)
    due: Mapped[date | None] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    answered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Fact(Base):
    __tablename__ = "facts"
    id: Mapped[int] = mapped_column(primary_key=True)
    hash: Mapped[str] = mapped_column(String(64), unique=True)
    entity_type: Mapped[str] = mapped_column(String(30))
    entity_key: Mapped[str] = mapped_column(String(160))
    sector_id: Mapped[int | None] = mapped_column(ForeignKey("sectors.id"))
    claim: Mapped[str] = mapped_column(Text)
    value: Mapped[dict | None] = mapped_column(JSONType)
    confidence: Mapped[float] = mapped_column()
    source_name: Mapped[str] = mapped_column(String(80), default="web")
    source_url: Mapped[str | None] = mapped_column(Text)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    run_id: Mapped[int | None] = mapped_column(Integer)


class Task(Base):
    __tablename__ = "tasks"
    id: Mapped[int] = mapped_column(primary_key=True)
    profile: Mapped[str] = mapped_column(String(30))
    payload: Mapped[dict] = mapped_column(JSONType, default=dict)
    status: Mapped[str] = mapped_column(String(12), default="queued")
    priority: Mapped[int] = mapped_column(Integer, default=50)
    est_cost_eur: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0"))
    actual_cost_eur: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0"))
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text)
    result_md: Mapped[str | None] = mapped_column(Text)
    run_id: Mapped[int | None] = mapped_column(Integer)
    locked_by: Mapped[str | None] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Run(Base):
    __tablename__ = "runs"
    id: Mapped[int] = mapped_column(primary_key=True)
    day: Mapped[date] = mapped_column(Date)
    phase: Mapped[str] = mapped_column(String(20))
    budget_cap_eur: Mapped[Decimal] = mapped_column(MONEY)
    spent_eur: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0"))
    tasks_done: Mapped[int] = mapped_column(Integer, default=0)
    tasks_failed: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(12), default="running")
    summary_md: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Cost(Base):
    __tablename__ = "costs"
    __table_args__ = (Index("ix_costs_day", "day"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    day: Mapped[date] = mapped_column(Date)
    run_id: Mapped[int | None] = mapped_column(Integer)
    task_id: Mapped[int | None] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String(12))
    provider: Mapped[str] = mapped_column(String(30))
    model: Mapped[str | None] = mapped_column(String(60))
    units: Mapped[dict] = mapped_column(JSONType, default=dict)
    cost_eur: Mapped[Decimal] = mapped_column(MONEY)
    request_id: Mapped[str | None] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class JournalEntry(Base):
    __tablename__ = "journal"
    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int | None] = mapped_column(Integer)
    day: Mapped[date] = mapped_column(Date)
    did_md: Mapped[str] = mapped_column(Text, default="")
    learned_md: Mapped[str] = mapped_column(Text, default="")
    tomorrow_md: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Scorecard(Base):
    __tablename__ = "scorecard"
    id: Mapped[int] = mapped_column(primary_key=True)
    day: Mapped[date] = mapped_column(Date, unique=True)
    metrics: Mapped[dict] = mapped_column(JSONType, default=dict)


class AppChartSnapshot(Base):
    __tablename__ = "app_chart_snapshots"
    __table_args__ = (
        UniqueConstraint("store", "country", "chart", "app_key", "captured_on", name="ux_chart_row"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    store: Mapped[str] = mapped_column(String(10))
    country: Mapped[str] = mapped_column(String(2))
    chart: Mapped[str] = mapped_column(String(20), default="top-free")
    rank: Mapped[int] = mapped_column(Integer)
    app_key: Mapped[str] = mapped_column(String(200))
    app_name: Mapped[str] = mapped_column(String(200), default="")
    captured_on: Mapped[date] = mapped_column(Date)


class Brief(Base):
    __tablename__ = "briefs"
    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int | None] = mapped_column(Integer)
    day: Mapped[date] = mapped_column(Date)
    markdown: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Setting(Base):
    __tablename__ = "settings"
    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    value: Mapped[dict | None] = mapped_column(JSONType)
```

`scout/db/__init__.py`: empty file.

- [ ] **Step 7: Run the tests to verify they pass**

Run: `TEST_DATABASE_URL=<url> uv run pytest tests/test_models.py -v`
Expected: 2 PASSED

- [ ] **Step 8: Set up Alembic and generate the initial migration**

```bash
uv run alembic init alembic
```

Replace the generated `alembic/env.py` with:
```python
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from scout.config import get_settings
from scout.db.base import Base
import scout.db.models  # noqa: F401  (registers tables on Base.metadata)

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)
config.set_main_option("sqlalchemy.url", get_settings().database_url)
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(url=config.get_main_option("sqlalchemy.url"),
                      target_metadata=target_metadata, literal_binds=True,
                      dialect_opts={"paramstyle": "named"})
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(config.get_section(config.config_ini_section, {}),
                                     prefix="sqlalchemy.", poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

In `alembic.ini` delete the `sqlalchemy.url = ...` line (env.py sets it). Then, with `DATABASE_URL` in `.env` pointing at the **development** Neon database:
```bash
uv run alembic revision --autogenerate -m "init"
uv run alembic upgrade head
```
Open the generated file under `alembic/versions/` and confirm it creates the 17 tables and the two functional unique indexes (`ux_business_sector_name`, `ux_gap_sector_title`). If autogenerate rendered the functional indexes incorrectly, replace those two `create_index` calls with `op.execute("CREATE UNIQUE INDEX ux_business_sector_name ON businesses (sector_id, lower(name))")` and `op.execute("CREATE UNIQUE INDEX ux_gap_sector_title ON gaps (sector_id, lower(title))")`.

- [ ] **Step 9: Commit**

```bash
uv run ruff check . && uv run ruff format .
git add -A && git commit -m "feat(db): knowledge-base schema, alembic, test fixtures"
```

---

### Task 4: Knowledge-base repository — facts, sectors, digests, businesses, models, gaps

**Files:**
- Create: `scout/db/repo.py`
- Test: `tests/test_repo_kb.py`

**Interfaces:**
- Produces (all take a `Session` first):
  - `@dataclass FactIn(claim: str, entity_type: str, entity_key: str, confidence: float, source_url: str | None = None, sector_slug: str | None = None, value: dict | None = None, ttl_days: int = 90, source_name: str = "web")`
  - `fact_hash(entity_type: str, entity_key: str, claim: str) -> str`
  - `upsert_fact(session, f: FactIn, *, run_id: int | None, observed_at: datetime) -> Fact`
  - `search_facts(session, query: str, *, sector_slug: str | None = None, limit: int = 20, now: datetime) -> list[Fact]`
  - `fresh_facts_since(session, since: datetime, *, sector_slugs: list[str] | None = None, min_confidence: float = 0.0, now: datetime) -> list[Fact]`
  - `has_presence_check(session, gap: Gap, *, now: datetime, max_age_days: int = 60) -> bool`
  - `get_sector(session, slug) -> Sector | None`; `get_or_create_sector(session, slug, name_en, name_sq=None, priority=50) -> Sector`; `list_sectors(session) -> list[Sector]`; `set_sector_status(session, slug, status, *, now) -> None`
  - `get_digest(session, key) -> str | None`; `set_digest(session, key, title, body_md, *, now) -> Digest`; `list_digests(session, prefix: str) -> list[Digest]`
  - `upsert_business(session, *, name, sector_slug, kind="local", city=None, channels=None, note=None, seen_at) -> Business`; `list_businesses(session, sector_slug) -> list[Business]`
  - `upsert_proven_model(session, *, slug, name, sector_slug, description, markets: list[dict], business_model=None, source_urls: list[str] | None = None) -> ProvenModel`
  - `propose_gap(session, *, title, sector_slug, proven_model_slug=None, hypothesis_md="", presence_level="unknown", why_not_yet_md="", run_id=None) -> tuple[Gap, bool]` (bool = created)
  - `list_gaps(session, *, statuses: list[str] | None = None, min_score: int | None = None, sector_slugs: list[str] | None = None) -> list[Gap]`; `get_gap(session, gap_id) -> Gap | None`; `get_gap_by_title(session, sector_slug, title) -> Gap | None`
  - `slugify(text: str) -> str`

- [ ] **Step 1: Write the failing tests**

`tests/test_repo_kb.py`:
```python
from datetime import UTC, datetime, timedelta

import pytest

from scout.db import repo
from scout.db.repo import FactIn

pytestmark = pytest.mark.db
NOW = datetime(2026, 10, 19, 6, 0, tzinfo=UTC)


def test_slugify():
    assert repo.slugify("Home Services — Booking!") == "home-services-booking"


def test_upsert_fact_refreshes_same_claim(db_session):
    repo.get_or_create_sector(db_session, "pets", "Pets")
    f = FactIn(claim="There are 3 pet shops in Prizren", entity_type="sector", entity_key="pets",
               confidence=0.5, sector_slug="pets", ttl_days=30)
    a = repo.upsert_fact(db_session, f, run_id=1, observed_at=NOW)
    later = NOW + timedelta(days=2)
    f2 = FactIn(claim="  there are 3 PET shops in Prizren ", entity_type="sector",
                entity_key="pets", confidence=0.8, sector_slug="pets", ttl_days=30)
    b = repo.upsert_fact(db_session, f2, run_id=2, observed_at=later)
    assert a.id == b.id
    assert b.confidence == 0.8
    assert b.observed_at == later
    assert b.expires_at == later + timedelta(days=30)
    assert len(repo.search_facts(db_session, "pet shops", now=later)) == 1


def test_search_excludes_expired(db_session):
    f = FactIn(claim="Old news about parking", entity_type="culture", entity_key="mobility",
               confidence=0.6, ttl_days=1)
    repo.upsert_fact(db_session, f, run_id=None, observed_at=NOW)
    assert repo.search_facts(db_session, "parking", now=NOW) != []
    assert repo.search_facts(db_session, "parking", now=NOW + timedelta(days=2)) == []


def test_sector_digest_business_model_roundtrip(db_session):
    s = repo.get_or_create_sector(db_session, "pets", "Pets", "Kafshë", priority=2)
    assert repo.get_or_create_sector(db_session, "pets", "Pets").id == s.id
    repo.set_digest(db_session, "sector:pets", "Pets", "# Pets\nsmall market", now=NOW)
    assert repo.get_digest(db_session, "sector:pets") == "# Pets\nsmall market"
    b = repo.upsert_business(db_session, name="PetShop KS", sector_slug="pets", city="Prishtinë",
                             channels={"instagram": "petshopks"}, seen_at=NOW)
    b2 = repo.upsert_business(db_session, name="petshop ks", sector_slug="pets",
                              seen_at=NOW + timedelta(days=1))
    assert b.id == b2.id and b2.channels == {"instagram": "petshopks"}
    assert b2.last_seen == NOW + timedelta(days=1)
    pm = repo.upsert_proven_model(
        db_session, slug="pet-sitting-marketplace", name="Pet sitting marketplace",
        sector_slug="pets", description="Rover-style",
        markets=[{"country": "HR", "example": "Pawshake", "url": "https://x"},
                 {"country": "DE", "example": "Pawshake", "url": "https://y"}])
    assert pm.nearby_count == 1


def test_propose_gap_dedupes_by_title(db_session):
    repo.get_or_create_sector(db_session, "pets", "Pets")
    g1, created1 = repo.propose_gap(db_session, title="Pet sitting marketplace", sector_slug="pets")
    g2, created2 = repo.propose_gap(db_session, title="PET SITTING marketplace", sector_slug="pets",
                                    hypothesis_md="x")
    assert created1 and not created2 and g1.id == g2.id
    assert repo.list_gaps(db_session, statuses=["candidate"])[0].id == g1.id


def test_has_presence_check(db_session):
    repo.get_or_create_sector(db_session, "pets", "Pets")
    gap, _ = repo.propose_gap(db_session, title="Pet sitting marketplace", sector_slug="pets")
    assert not repo.has_presence_check(db_session, gap, now=NOW)
    repo.upsert_fact(db_session, FactIn(
        claim="presence check: absent", entity_type="presence_check",
        entity_key=f"gap:{gap.id}", confidence=0.8, sector_slug="pets",
        value={"verdict": "absent"}, ttl_days=60), run_id=1, observed_at=NOW)
    assert repo.has_presence_check(db_session, gap, now=NOW)
    assert not repo.has_presence_check(db_session, gap, now=NOW + timedelta(days=61))
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `TEST_DATABASE_URL=<url> uv run pytest tests/test_repo_kb.py -v`
Expected: FAIL with `ImportError: cannot import name 'repo'`

- [ ] **Step 3: Write `scout/db/repo.py` (knowledge-base half)**

```python
"""Repository: every database read/write the engine needs, as plain functions."""

from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from scout.db.models import (
    AppChartSnapshot,
    Brief,
    Business,
    Cost,
    Digest,
    Fact,
    FieldCheck,
    Gap,
    JournalEntry,
    ProvenModel,
    Run,
    Scorecard,
    Sector,
    Setting,
    Task,
)

NEARBY = {"AL", "MK", "ME", "BA", "RS", "HR", "SI"}


# ---------- helpers ----------

def slugify(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    text = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    return text


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip()).lower()


def fact_hash(entity_type: str, entity_key: str, claim: str) -> str:
    raw = f"{entity_type}|{entity_key}|{_norm(claim)}"
    return hashlib.sha256(raw.encode()).hexdigest()


# ---------- facts ----------

@dataclass
class FactIn:
    claim: str
    entity_type: str
    entity_key: str
    confidence: float
    source_url: str | None = None
    sector_slug: str | None = None
    value: dict | None = None
    ttl_days: int = 90
    source_name: str = "web"


def upsert_fact(session: Session, f: FactIn, *, run_id: int | None, observed_at: datetime) -> Fact:
    h = fact_hash(f.entity_type, f.entity_key, f.claim)
    sector = get_sector(session, f.sector_slug) if f.sector_slug else None
    fact = session.scalars(select(Fact).where(Fact.hash == h)).first()
    expires = observed_at + timedelta(days=f.ttl_days)
    if fact is None:
        fact = Fact(hash=h, entity_type=f.entity_type, entity_key=f.entity_key,
                    sector_id=sector.id if sector else None, claim=f.claim.strip(),
                    value=f.value, confidence=f.confidence, source_name=f.source_name,
                    source_url=f.source_url, observed_at=observed_at, expires_at=expires,
                    run_id=run_id)
        session.add(fact)
    else:
        fact.observed_at = observed_at
        fact.expires_at = expires
        fact.confidence = max(fact.confidence, f.confidence)
        fact.source_url = f.source_url or fact.source_url
        fact.value = f.value if f.value is not None else fact.value
        fact.run_id = run_id
        if sector and fact.sector_id is None:
            fact.sector_id = sector.id
    session.commit()
    return fact


def search_facts(session: Session, query: str, *, sector_slug: str | None = None,
                 limit: int = 20, now: datetime) -> list[Fact]:
    words = [w for w in re.split(r"\s+", query.strip()) if len(w) >= 3][:6]
    stmt = select(Fact).where(Fact.expires_at > now)
    for w in words:
        stmt = stmt.where(or_(Fact.claim.ilike(f"%{w}%"), Fact.entity_key.ilike(f"%{w}%")))
    if sector_slug:
        sector = get_sector(session, sector_slug)
        if sector:
            stmt = stmt.where(Fact.sector_id == sector.id)
    stmt = stmt.order_by(Fact.confidence.desc(), Fact.observed_at.desc()).limit(limit)
    return list(session.scalars(stmt))


def fresh_facts_since(session: Session, since: datetime, *, sector_slugs: list[str] | None = None,
                      min_confidence: float = 0.0, now: datetime) -> list[Fact]:
    stmt = select(Fact).where(Fact.observed_at >= since, Fact.expires_at > now,
                              Fact.confidence >= min_confidence)
    if sector_slugs:
        ids = [s.id for s in session.scalars(select(Sector).where(Sector.slug.in_(sector_slugs)))]
        stmt = stmt.where(Fact.sector_id.in_(ids))
    return list(session.scalars(stmt.order_by(Fact.confidence.desc()).limit(400)))


def has_presence_check(session: Session, gap: Gap, *, now: datetime, max_age_days: int = 60) -> bool:
    stmt = select(Fact).where(
        Fact.entity_type == "presence_check",
        Fact.entity_key == f"gap:{gap.id}",
        Fact.observed_at >= now - timedelta(days=max_age_days),
    )
    return session.scalars(stmt).first() is not None


# ---------- sectors, digests ----------

def get_sector(session: Session, slug: str) -> Sector | None:
    return session.scalars(select(Sector).where(Sector.slug == slug)).first()


def get_or_create_sector(session: Session, slug: str, name_en: str, name_sq: str | None = None,
                         priority: int = 50) -> Sector:
    sector = get_sector(session, slug)
    if sector is None:
        sector = Sector(slug=slug, name_en=name_en, name_sq=name_sq, priority=priority)
        session.add(sector)
        session.commit()
    return sector


def list_sectors(session: Session) -> list[Sector]:
    return list(session.scalars(select(Sector).order_by(Sector.priority, Sector.slug)))


def set_sector_status(session: Session, slug: str, status: str, *, now: datetime) -> None:
    sector = get_sector(session, slug)
    if sector is None:
        return
    sector.status = status
    if status == "mapped":
        sector.last_mapped_at = now
    if status == "hunted":
        sector.last_hunted_at = now
    session.commit()


def get_digest(session: Session, key: str) -> str | None:
    d = session.get(Digest, key)
    return d.body_md if d else None


def set_digest(session: Session, key: str, title: str, body_md: str, *, now: datetime) -> Digest:
    d = session.get(Digest, key)
    if d is None:
        d = Digest(key=key, title=title)
        session.add(d)
    d.title = title
    d.body_md = body_md
    d.updated_at = now
    d.token_estimate = max(1, len(body_md) // 4)
    session.commit()
    return d


def list_digests(session: Session, prefix: str) -> list[Digest]:
    return list(session.scalars(select(Digest).where(Digest.key.like(f"{prefix}%")).order_by(Digest.key)))


# ---------- businesses, proven models, gaps ----------

def upsert_business(session: Session, *, name: str, sector_slug: str, kind: str = "local",
                    city: str | None = None, channels: dict | None = None, note: str | None = None,
                    seen_at: datetime) -> Business:
    sector = get_or_create_sector(session, sector_slug, sector_slug.replace("-", " ").title())
    stmt = select(Business).where(Business.sector_id == sector.id,
                                  func.lower(Business.name) == name.strip().lower())
    b = session.scalars(stmt).first()
    if b is None:
        b = Business(sector_id=sector.id, name=name.strip(), kind=kind, city=city,
                     channels=channels or {}, note=note, first_seen=seen_at, last_seen=seen_at)
        session.add(b)
    else:
        b.last_seen = max(b.last_seen, seen_at)
        b.city = city or b.city
        b.note = note or b.note
        merged = dict(b.channels or {})
        merged.update({k: v for k, v in (channels or {}).items() if v})
        b.channels = merged
    session.commit()
    return b


def list_businesses(session: Session, sector_slug: str) -> list[Business]:
    sector = get_sector(session, sector_slug)
    if sector is None:
        return []
    return list(session.scalars(select(Business).where(Business.sector_id == sector.id)
                                .order_by(Business.name)))


def upsert_proven_model(session: Session, *, slug: str, name: str, sector_slug: str, description: str,
                        markets: list[dict], business_model: str | None = None,
                        source_urls: list[str] | None = None) -> ProvenModel:
    sector = get_or_create_sector(session, sector_slug, sector_slug.replace("-", " ").title())
    pm = session.scalars(select(ProvenModel).where(ProvenModel.slug == slug)).first()
    if pm is None:
        pm = ProvenModel(slug=slug, name=name, sector_id=sector.id, description=description)
        session.add(pm)
    pm.name = name
    pm.description = description
    existing = {(m.get("country"), m.get("example")) for m in (pm.markets or [])}
    merged = list(pm.markets or [])
    for m in markets:
        if (m.get("country"), m.get("example")) not in existing:
            merged.append(m)
    pm.markets = merged
    pm.business_model = business_model or pm.business_model
    pm.source_urls = sorted(set(pm.source_urls or []) | set(source_urls or []))
    pm.nearby_count = sum(1 for m in merged if str(m.get("country", "")).upper() in NEARBY)
    session.commit()
    return pm


def get_gap(session: Session, gap_id: int) -> Gap | None:
    return session.get(Gap, gap_id)


def get_gap_by_title(session: Session, sector_slug: str, title: str) -> Gap | None:
    sector = get_sector(session, sector_slug)
    if sector is None:
        return None
    return session.scalars(select(Gap).where(Gap.sector_id == sector.id,
                                             func.lower(Gap.title) == title.strip().lower())).first()


def propose_gap(session: Session, *, title: str, sector_slug: str, proven_model_slug: str | None = None,
                hypothesis_md: str = "", presence_level: str = "unknown", why_not_yet_md: str = "",
                run_id: int | None = None) -> tuple[Gap, bool]:
    sector = get_or_create_sector(session, sector_slug, sector_slug.replace("-", " ").title())
    gap = get_gap_by_title(session, sector_slug, title)
    pm = (session.scalars(select(ProvenModel).where(ProvenModel.slug == proven_model_slug)).first()
          if proven_model_slug else None)
    if gap is not None:
        gap.hypothesis_md = hypothesis_md or gap.hypothesis_md
        gap.why_not_yet_md = why_not_yet_md or gap.why_not_yet_md
        if presence_level != "unknown":
            gap.presence_level = presence_level  # verify-gap reports its verdict through this path
        if pm and gap.proven_model_id is None:
            gap.proven_model_id = pm.id
        session.commit()
        return gap, False
    gap = Gap(title=title.strip(), sector_id=sector.id, proven_model_id=pm.id if pm else None,
              hypothesis_md=hypothesis_md, presence_level=presence_level,
              why_not_yet_md=why_not_yet_md, status="candidate", last_assessed_run_id=run_id)
    session.add(gap)
    session.commit()
    return gap, True


def list_gaps(session: Session, *, statuses: list[str] | None = None, min_score: int | None = None,
              sector_slugs: list[str] | None = None) -> list[Gap]:
    stmt = select(Gap)
    if statuses:
        stmt = stmt.where(Gap.status.in_(statuses))
    if min_score is not None:
        stmt = stmt.where(Gap.score_total >= min_score)
    if sector_slugs:
        ids = [s.id for s in session.scalars(select(Sector).where(Sector.slug.in_(sector_slugs)))]
        stmt = stmt.where(Gap.sector_id.in_(ids))
    return list(session.scalars(stmt.order_by(Gap.score_total.desc(), Gap.confidence.desc(), Gap.id)))
```

(The queue/run/cost/journal half of this file is added in Task 5; keep the imports above — they already cover it.)

- [ ] **Step 4: Run the tests to verify they pass**

Run: `TEST_DATABASE_URL=<url> uv run pytest tests/test_repo_kb.py -v`
Expected: 6 PASSED

- [ ] **Step 5: Commit**

```bash
uv run ruff check . && uv run ruff format .
git add -A && git commit -m "feat(db): knowledge-base repository (facts, sectors, digests, gaps)"
```

---

### Task 5: Repository — task queue, runs, costs, journal, charts, field checks, settings

**Files:**
- Modify: `scout/db/repo.py` (append)
- Test: `tests/test_repo_ops.py`

**Interfaces:**
- Produces:
  - `@dataclass CostRecord(kind: str, provider: str, model: str | None, units: dict, cost_eur: Decimal, request_id: str | None = None, task_id: int | None = None)`
  - `@dataclass ChartEntryIn(rank: int, app_key: str, app_name: str)`
  - `enqueue_task(session, *, profile, payload, priority=50, est_cost_eur=Decimal("0"), run_id=None) -> Task`; `claim_next_task(session, worker_id: str, *, now) -> Task | None`; `finish_task(session, task, *, result_md, actual_cost_eur, now)`; `fail_task(session, task, *, error, now, requeue: bool)`; `queued_tasks(session) -> list[Task]`; `tasks_for_run(session, run_id) -> list[Task]`; `task_exists_today(session, profile, payload_key: str, payload_value: str, day: date) -> bool`
  - `start_run(session, *, day, phase, budget_cap_eur, started_at) -> Run`; `finish_run(session, run, *, spent_eur, tasks_done, tasks_failed, summary_md, finished_at, status="done")`; `last_run(session) -> Run | None`
  - `record_cost(session, rec: CostRecord, *, day, run_id) -> Cost`; `spent_on(session, day) -> Decimal`; `spent_between(session, start, end) -> Decimal`; `places_calls_in_month(session, day) -> int`
  - `write_journal(session, *, run_id, day, did_md, learned_md, tomorrow_md) -> JournalEntry`; `latest_journal(session, limit=3) -> list[JournalEntry]`
  - `save_brief(session, *, run_id, day, markdown) -> Brief`; `latest_brief(session) -> Brief | None`
  - `save_chart_snapshot(session, *, store, country, chart, entries: list[ChartEntryIn], captured_on) -> int`; `chart_snapshot(session, *, store, country, chart, captured_on) -> list[AppChartSnapshot]`; `latest_chart_date(session, *, store, country, chart, before: date) -> date | None`; `app_ever_in_chart(session, *, store, country, app_key) -> bool`
  - `add_field_check(session, *, gap_id, question, why, due) -> FieldCheck`; `open_field_checks(session) -> list[FieldCheck]`; `answer_field_check(session, fc, *, answer, answered_at)`
  - `save_scorecard(session, *, day, metrics) -> Scorecard`; `get_setting(session, key, default=None)`; `set_setting(session, key, value)`

- [ ] **Step 1: Write the failing tests**

`tests/test_repo_ops.py`:
```python
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from scout.db import repo
from scout.db.base import make_session_factory
from scout.db.repo import ChartEntryIn, CostRecord

pytestmark = pytest.mark.db
NOW = datetime(2026, 10, 19, 6, 0, tzinfo=UTC)
DAY = date(2026, 10, 19)


def test_queue_claims_highest_priority_and_skips_locked(db_session, db_engine):
    low = repo.enqueue_task(db_session, profile="news-scan", payload={}, priority=10)
    high = repo.enqueue_task(db_session, profile="map-sector", payload={"sector": "pets"}, priority=90)
    first = repo.claim_next_task(db_session, "w1", now=NOW)
    assert first.id == high.id and first.status == "running" and first.attempts == 1
    other = make_session_factory(db_engine)()
    try:
        second = repo.claim_next_task(other, "w2", now=NOW)
        assert second.id == low.id
        assert repo.claim_next_task(other, "w2", now=NOW) is None
    finally:
        other.close()
    repo.finish_task(db_session, first, result_md="ok", actual_cost_eur=Decimal("0.2"), now=NOW)
    assert repo.tasks_for_run(db_session, None) == []  # no run attached
    assert first.status == "done" and first.actual_cost_eur == Decimal("0.2")


def test_fail_task_requeues_until_two_attempts(db_session):
    t = repo.enqueue_task(db_session, profile="culture", payload={"theme": "payments"})
    t = repo.claim_next_task(db_session, "w", now=NOW)
    repo.fail_task(db_session, t, error="boom", now=NOW, requeue=True)
    assert t.status == "queued"
    t = repo.claim_next_task(db_session, "w", now=NOW)
    repo.fail_task(db_session, t, error="boom", now=NOW, requeue=True)
    assert t.status == "failed" and t.attempts == 2


def test_task_exists_today(db_session):
    run = repo.start_run(db_session, day=DAY, phase="foundation", budget_cap_eur=Decimal("3"),
                         started_at=NOW)
    repo.enqueue_task(db_session, profile="map-sector", payload={"sector": "pets"}, run_id=run.id)
    assert repo.task_exists_today(db_session, "map-sector", "sector", "pets", DAY)
    assert not repo.task_exists_today(db_session, "map-sector", "sector", "cars", DAY)


def test_costs_sum_per_explicit_day(db_session):
    run = repo.start_run(db_session, day=DAY, phase="foundation", budget_cap_eur=Decimal("3"),
                         started_at=NOW)
    repo.record_cost(db_session, CostRecord("llm", "anthropic", "claude-sonnet-5-5", {"input_tokens": 1},
                                            Decimal("0.10")), day=DAY, run_id=run.id)
    repo.record_cost(db_session, CostRecord("search", "anthropic", None, {"web_search_requests": 2},
                                            Decimal("0.02")), day=DAY, run_id=run.id)
    repo.record_cost(db_session, CostRecord("places", "google", None, {"calls": 1}, Decimal("0")),
                     day=date(2026, 10, 20), run_id=run.id)
    assert repo.spent_on(db_session, DAY) == Decimal("0.120000")
    assert repo.spent_on(db_session, date(2026, 10, 20)) == Decimal("0.000000")
    assert repo.places_calls_in_month(db_session, DAY) == 1
    repo.finish_run(db_session, run, spent_eur=Decimal("0.12"), tasks_done=2, tasks_failed=0,
                    summary_md="fine", finished_at=NOW)
    assert repo.last_run(db_session).status == "done"


def test_journal_brief_scorecard_settings(db_session):
    repo.write_journal(db_session, run_id=1, day=DAY, did_md="a", learned_md="b", tomorrow_md="c")
    repo.write_journal(db_session, run_id=2, day=date(2026, 10, 20), did_md="d", learned_md="e",
                       tomorrow_md="f")
    assert [j.did_md for j in repo.latest_journal(db_session, limit=1)] == ["d"]
    repo.save_brief(db_session, run_id=1, day=DAY, markdown="# Brief")
    assert repo.latest_brief(db_session).markdown == "# Brief"
    repo.save_scorecard(db_session, day=DAY, metrics={"gaps": 1})
    repo.save_scorecard(db_session, day=DAY, metrics={"gaps": 2})
    assert repo.set_setting(db_session, "phase", {"value": "verification"}) is None
    assert repo.get_setting(db_session, "phase") == {"value": "verification"}
    assert repo.get_setting(db_session, "missing", "x") == "x"


def test_chart_snapshots(db_session):
    n = repo.save_chart_snapshot(db_session, store="apple", country="xk", chart="top-free",
                                 entries=[ChartEntryIn(1, "123", "Wolt"), ChartEntryIn(2, "456", "APTV")],
                                 captured_on=DAY)
    assert n == 2
    # saving again the same day is idempotent
    assert repo.save_chart_snapshot(db_session, store="apple", country="xk", chart="top-free",
                                    entries=[ChartEntryIn(1, "123", "Wolt")], captured_on=DAY) == 0
    rows = repo.chart_snapshot(db_session, store="apple", country="xk", chart="top-free", captured_on=DAY)
    assert [r.app_key for r in rows] == ["123", "456"]
    assert repo.latest_chart_date(db_session, store="apple", country="xk", chart="top-free",
                                  before=date(2026, 10, 26)) == DAY
    assert repo.app_ever_in_chart(db_session, store="apple", country="xk", app_key="456")
    assert not repo.app_ever_in_chart(db_session, store="play", country="xk", app_key="456")


def test_field_checks(db_session):
    repo.get_or_create_sector(db_session, "pets", "Pets")
    gap, _ = repo.propose_gap(db_session, title="Pet sitting", sector_slug="pets")
    fc = repo.add_field_check(db_session, gap_id=gap.id, question="Any pet sitters in Prizren?",
                              why="confidence 0.4", due=date(2026, 10, 25))
    assert [f.id for f in repo.open_field_checks(db_session)] == [fc.id]
    repo.answer_field_check(db_session, fc, answer="No, only vets", answered_at=NOW)
    assert repo.open_field_checks(db_session) == [] and fc.status == "answered"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `TEST_DATABASE_URL=<url> uv run pytest tests/test_repo_ops.py -v`
Expected: FAIL with `ImportError: cannot import name 'ChartEntryIn'`

- [ ] **Step 3: Append the operations half to `scout/db/repo.py`**

```python
# ---------- task queue ----------

@dataclass
class CostRecord:
    kind: str
    provider: str
    model: str | None
    units: dict
    cost_eur: Decimal
    request_id: str | None = None
    task_id: int | None = None


@dataclass
class ChartEntryIn:
    rank: int
    app_key: str
    app_name: str


MAX_ATTEMPTS = 2


def enqueue_task(session: Session, *, profile: str, payload: dict, priority: int = 50,
                 est_cost_eur: Decimal = Decimal("0"), run_id: int | None = None) -> Task:
    t = Task(profile=profile, payload=payload, priority=priority, est_cost_eur=est_cost_eur, run_id=run_id)
    session.add(t)
    session.commit()
    return t


def claim_next_task(session: Session, worker_id: str, *, now: datetime) -> Task | None:
    stmt = (select(Task).where(Task.status == "queued")
            .order_by(Task.priority.desc(), Task.id).limit(1).with_for_update(skip_locked=True))
    task = session.scalars(stmt).first()
    if task is None:
        session.rollback()
        return None
    task.status = "running"
    task.started_at = now
    task.locked_by = worker_id
    task.attempts += 1
    session.commit()
    return task


def finish_task(session: Session, task: Task, *, result_md: str, actual_cost_eur: Decimal,
                now: datetime) -> None:
    task.status = "done"
    task.result_md = result_md
    task.actual_cost_eur = actual_cost_eur
    task.finished_at = now
    task.locked_by = None
    session.commit()


def fail_task(session: Session, task: Task, *, error: str, now: datetime, requeue: bool) -> None:
    task.error = error[:4000]
    task.finished_at = now
    task.locked_by = None
    task.status = "queued" if (requeue and task.attempts < MAX_ATTEMPTS) else "failed"
    session.commit()


def queued_tasks(session: Session) -> list[Task]:
    return list(session.scalars(select(Task).where(Task.status == "queued")
                                .order_by(Task.priority.desc(), Task.id)))


def tasks_for_run(session: Session, run_id: int | None) -> list[Task]:
    if run_id is None:
        return []
    return list(session.scalars(select(Task).where(Task.run_id == run_id).order_by(Task.id)))


def task_exists_today(session: Session, profile: str, payload_key: str, payload_value: str,
                      day: date) -> bool:
    run_ids = [r.id for r in session.scalars(select(Run).where(Run.day == day))]
    if not run_ids:
        return False
    for t in session.scalars(select(Task).where(Task.profile == profile, Task.run_id.in_(run_ids))):
        if str((t.payload or {}).get(payload_key)) == payload_value:
            return True
    return False


# ---------- runs, costs ----------

def start_run(session: Session, *, day: date, phase: str, budget_cap_eur: Decimal,
              started_at: datetime) -> Run:
    run = Run(day=day, phase=phase, budget_cap_eur=budget_cap_eur, started_at=started_at)
    session.add(run)
    session.commit()
    return run


def finish_run(session: Session, run: Run, *, spent_eur: Decimal, tasks_done: int, tasks_failed: int,
               summary_md: str, finished_at: datetime, status: str = "done") -> None:
    run.spent_eur = spent_eur
    run.tasks_done = tasks_done
    run.tasks_failed = tasks_failed
    run.summary_md = summary_md
    run.finished_at = finished_at
    run.status = status
    session.commit()


def last_run(session: Session) -> Run | None:
    return session.scalars(select(Run).order_by(Run.id.desc())).first()


def record_cost(session: Session, rec: CostRecord, *, day: date, run_id: int | None) -> Cost:
    c = Cost(day=day, run_id=run_id, task_id=rec.task_id, kind=rec.kind, provider=rec.provider,
             model=rec.model, units=rec.units, cost_eur=rec.cost_eur, request_id=rec.request_id)
    session.add(c)
    session.commit()
    return c


def spent_on(session: Session, day: date) -> Decimal:
    total = session.scalar(select(func.coalesce(func.sum(Cost.cost_eur), 0)).where(Cost.day == day))
    return Decimal(total).quantize(Decimal("0.000001"))


def spent_between(session: Session, start: date, end: date) -> Decimal:
    total = session.scalar(select(func.coalesce(func.sum(Cost.cost_eur), 0))
                           .where(Cost.day >= start, Cost.day <= end))
    return Decimal(total).quantize(Decimal("0.000001"))


def places_calls_in_month(session: Session, day: date) -> int:
    start = day.replace(day=1)
    rows = session.scalars(select(Cost).where(Cost.kind == "places", Cost.day >= start, Cost.day <= day))
    return sum(int((c.units or {}).get("calls", 1)) for c in rows)


# ---------- journal, briefs, scorecard, settings ----------

def write_journal(session: Session, *, run_id: int | None, day: date, did_md: str, learned_md: str,
                  tomorrow_md: str) -> JournalEntry:
    j = JournalEntry(run_id=run_id, day=day, did_md=did_md, learned_md=learned_md, tomorrow_md=tomorrow_md)
    session.add(j)
    session.commit()
    return j


def latest_journal(session: Session, limit: int = 3) -> list[JournalEntry]:
    return list(session.scalars(select(JournalEntry).order_by(JournalEntry.id.desc()).limit(limit)))


def save_brief(session: Session, *, run_id: int | None, day: date, markdown: str) -> Brief:
    b = Brief(run_id=run_id, day=day, markdown=markdown)
    session.add(b)
    session.commit()
    return b


def latest_brief(session: Session) -> Brief | None:
    return session.scalars(select(Brief).order_by(Brief.id.desc())).first()


def save_scorecard(session: Session, *, day: date, metrics: dict) -> Scorecard:
    sc = session.scalars(select(Scorecard).where(Scorecard.day == day)).first()
    if sc is None:
        sc = Scorecard(day=day, metrics=metrics)
        session.add(sc)
    else:
        sc.metrics = metrics
    session.commit()
    return sc


def get_setting(session: Session, key: str, default=None):
    s = session.get(Setting, key)
    return s.value if s is not None else default


def set_setting(session: Session, key: str, value) -> None:
    s = session.get(Setting, key)
    if s is None:
        session.add(Setting(key=key, value=value))
    else:
        s.value = value
    session.commit()


# ---------- app charts ----------

def save_chart_snapshot(session: Session, *, store: str, country: str, chart: str,
                        entries: list[ChartEntryIn], captured_on: date) -> int:
    existing = {r.app_key for r in chart_snapshot(session, store=store, country=country, chart=chart,
                                                  captured_on=captured_on)}
    added = 0
    for e in entries:
        if e.app_key in existing:
            continue
        session.add(AppChartSnapshot(store=store, country=country, chart=chart, rank=e.rank,
                                     app_key=e.app_key, app_name=e.app_name[:200], captured_on=captured_on))
        added += 1
    session.commit()
    return added


def chart_snapshot(session: Session, *, store: str, country: str, chart: str,
                   captured_on: date) -> list[AppChartSnapshot]:
    stmt = (select(AppChartSnapshot)
            .where(AppChartSnapshot.store == store, AppChartSnapshot.country == country,
                   AppChartSnapshot.chart == chart, AppChartSnapshot.captured_on == captured_on)
            .order_by(AppChartSnapshot.rank))
    return list(session.scalars(stmt))


def latest_chart_date(session: Session, *, store: str, country: str, chart: str, before: date) -> date | None:
    return session.scalar(select(func.max(AppChartSnapshot.captured_on))
                          .where(AppChartSnapshot.store == store, AppChartSnapshot.country == country,
                                 AppChartSnapshot.chart == chart, AppChartSnapshot.captured_on < before))


def app_ever_in_chart(session: Session, *, store: str, country: str, app_key: str) -> bool:
    stmt = select(AppChartSnapshot.id).where(AppChartSnapshot.store == store,
                                             AppChartSnapshot.country == country,
                                             AppChartSnapshot.app_key == app_key).limit(1)
    return session.scalar(stmt) is not None


# ---------- field checks ----------

def add_field_check(session: Session, *, gap_id: int | None, question: str, why: str, due: date) -> FieldCheck:
    fc = FieldCheck(gap_id=gap_id, question=question, why=why, due=due)
    session.add(fc)
    session.commit()
    return fc


def open_field_checks(session: Session) -> list[FieldCheck]:
    return list(session.scalars(select(FieldCheck).where(FieldCheck.status == "open")
                                .order_by(FieldCheck.due, FieldCheck.id)))


def answer_field_check(session: Session, fc: FieldCheck, *, answer: str, answered_at: datetime) -> None:
    fc.answer = answer
    fc.status = "answered"
    fc.answered_at = answered_at
    session.commit()
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `TEST_DATABASE_URL=<url> uv run pytest tests/test_repo_ops.py tests/test_repo_kb.py -v`
Expected: 13 PASSED

- [ ] **Step 5: Commit**

```bash
uv run ruff check . && uv run ruff format .
git add -A && git commit -m "feat(db): task queue, runs, cost ledger, journal, charts, field checks"
```

---

### Task 6: Budget guard

**Files:**
- Create: `scout/budget/guard.py`
- Test: `tests/test_guard.py`

**Interfaces:**
- Consumes: `repo.spent_on`, `repo.record_cost`, `CostRecord`.
- Produces: `class BudgetExceeded(RuntimeError)`; `class BudgetGuard(session, *, day: date, daily_cap_eur: Decimal, run_id: int | None = None)` with `spent() -> Decimal`, `remaining() -> Decimal`, `can_afford(est_eur) -> bool`, `check(est_eur: Decimal) -> None` (raises), `record(rec: CostRecord) -> Decimal` (returns new total).

- [ ] **Step 1: Write the failing tests**

`tests/test_guard.py`:
```python
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from scout.budget.guard import BudgetExceeded, BudgetGuard
from scout.db import repo
from scout.db.repo import CostRecord

pytestmark = pytest.mark.db
DAY = date(2026, 10, 19)


def _rec(eur: str) -> CostRecord:
    return CostRecord("llm", "anthropic", "claude-haiku-5-5", {"input_tokens": 1}, Decimal(eur))


def test_check_raises_when_estimate_exceeds_cap(db_session):
    g = BudgetGuard(db_session, day=DAY, daily_cap_eur=Decimal("1.00"))
    g.check(Decimal("0.90"))
    g.record(_rec("0.70"))
    assert g.remaining() == Decimal("0.300000")
    assert g.can_afford(Decimal("0.30")) and not g.can_afford(Decimal("0.31"))
    with pytest.raises(BudgetExceeded):
        g.check(Decimal("0.31"))


def test_spent_uses_explicit_day(db_session):
    run = repo.start_run(db_session, day=DAY, phase="foundation", budget_cap_eur=Decimal("3"),
                         started_at=datetime(2026, 10, 18, 23, 30, tzinfo=UTC))
    g_today = BudgetGuard(db_session, day=DAY, daily_cap_eur=Decimal("3"), run_id=run.id)
    g_today.record(_rec("0.50"))
    g_yesterday = BudgetGuard(db_session, day=date(2026, 10, 18), daily_cap_eur=Decimal("3"))
    assert g_today.spent() == Decimal("0.500000")
    assert g_yesterday.spent() == Decimal("0.000000")
    cost_rows = db_session.query(repo.Cost).all()
    assert cost_rows[0].run_id == run.id and cost_rows[0].day == DAY


def test_zero_cap_blocks_everything(db_session):
    g = BudgetGuard(db_session, day=DAY, daily_cap_eur=Decimal("0"))
    with pytest.raises(BudgetExceeded):
        g.check(Decimal("0.000001"))
    g.check(Decimal("0"))  # free calls are always allowed
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `TEST_DATABASE_URL=<url> uv run pytest tests/test_guard.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'scout.budget.guard'`

- [ ] **Step 3: Write `scout/budget/guard.py`**

```python
from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from scout.db import repo
from scout.db.repo import CostRecord


class BudgetExceeded(RuntimeError):
    pass


class BudgetGuard:
    """Hard stop before every paid call; ledger entry after it.

    `day` is the run's local (Kosovo) date, decided once by the Director — never
    derived from the wall clock at record time.
    """

    def __init__(self, session: Session, *, day: date, daily_cap_eur: Decimal,
                 run_id: int | None = None) -> None:
        self.session = session
        self.day = day
        self.cap = Decimal(daily_cap_eur)
        self.run_id = run_id

    def spent(self) -> Decimal:
        return repo.spent_on(self.session, self.day)

    def remaining(self) -> Decimal:
        return max(Decimal("0"), self.cap - self.spent()).quantize(Decimal("0.000001"))

    def can_afford(self, est_eur: Decimal) -> bool:
        return self.spent() + Decimal(est_eur) <= self.cap

    def check(self, est_eur: Decimal) -> None:
        spent = self.spent()
        if spent + Decimal(est_eur) > self.cap:
            raise BudgetExceeded(
                f"budget: spent {spent} + est {est_eur} > cap {self.cap} for {self.day}"
            )

    def record(self, rec: CostRecord) -> Decimal:
        repo.record_cost(self.session, rec, day=self.day, run_id=self.run_id)
        return self.spent()
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `TEST_DATABASE_URL=<url> uv run pytest tests/test_guard.py -v`
Expected: 3 PASSED

- [ ] **Step 5: Commit**

```bash
uv run ruff check . && uv run ruff format .
git add -A && git commit -m "feat(budget): daily budget guard over the cost ledger"
```

---

### Task 7: LLM gateway and test fakes

**Files:**
- Create: `scout/llm/__init__.py`, `scout/llm/gateway.py`, `tests/fakes.py`
- Test: `tests/test_gateway.py`

**Interfaces:**
- Consumes: `BudgetGuard.check/record` (Task 6), `usage_units`, `llm_cost_usd`, `to_eur` (Task 2), `CostRecord` (Task 5).
- Produces: `LLM(client, guard, usd_to_eur: Decimal)` with
  - `record_message(model: str, message, *, task_id: int | None = None) -> Decimal` (EUR recorded)
  - `create_text(*, model, system: str | list[dict], user: str, max_tokens: int = 1024, effort: str = "medium", est_eur: Decimal, task_id: int | None = None) -> LLMResult`
  - `parse(*, model, output_format: type, system, user, max_tokens: int = 4096, effort: str = "medium", est_eur: Decimal, task_id: int | None = None) -> LLMResult` (raises `LLMTruncated` when `parsed` is None)
  - `LLMResult(text: str, parsed: Any | None, stop_reason: str, cost_eur: Decimal, cache_read_tokens: int, request_id: str | None)`; exceptions `LLMError`, `LLMRefusal`, `LLMTruncated`; helper `message_text(message) -> str`.
- Test fakes (`tests/fakes.py`): `FakeUsage`, `text_block(text)`, `FakeMessage`, `FakeMessages` (`.calls` list; `.create`, `.parse` pop queued responses), `FakeClient(responses)`, `FakeGuard(cap)` (in-memory `BudgetGuard` stand-in with `.records`, `.day`).

- [ ] **Step 1: Write `tests/fakes.py`**

```python
"""Hand-rolled fakes for the Anthropic client and the budget guard (no network, no DB)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from typing import Any

from scout.budget.guard import BudgetExceeded


@dataclass
class FakeUsage:
    input_tokens: int = 1000
    output_tokens: int = 100
    cache_creation_input_tokens: int = 0
    cache_read_input_tokens: int = 0
    server_tool_use: Any = None


def text_block(text: str) -> SimpleNamespace:
    return SimpleNamespace(type="text", text=text)


def tool_use_block(name: str, input: dict, id: str = "toolu_1") -> SimpleNamespace:  # noqa: A002
    return SimpleNamespace(type="tool_use", name=name, input=input, id=id)


@dataclass
class FakeMessage:
    content: list = field(default_factory=list)
    stop_reason: str = "end_turn"
    usage: FakeUsage = field(default_factory=FakeUsage)
    parsed_output: Any = None
    _request_id: str | None = "req_fake"
    role: str = "assistant"


class FakeMessages:
    def __init__(self, responses) -> None:
        self._responses = list(responses)
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return self._responses.pop(0)

    def parse(self, **kwargs):
        self.calls.append(kwargs)
        return self._responses.pop(0)


class FakeClient:
    def __init__(self, responses=()) -> None:
        self.messages = FakeMessages(responses)


class FakeGuard:
    """In-memory stand-in for BudgetGuard."""

    def __init__(self, cap: Decimal = Decimal("10"), day: date = date(2026, 10, 19)) -> None:
        self.cap = Decimal(cap)
        self.day = day
        self.run_id = None
        self.records: list = []

    def spent(self) -> Decimal:
        return sum((r.cost_eur for r in self.records), Decimal("0"))

    def remaining(self) -> Decimal:
        return max(Decimal("0"), self.cap - self.spent())

    def can_afford(self, est_eur) -> bool:
        return self.spent() + Decimal(est_eur) <= self.cap

    def check(self, est_eur) -> None:
        if self.spent() + Decimal(est_eur) > self.cap:
            raise BudgetExceeded(f"fake guard: spent {self.spent()} + {est_eur} > {self.cap}")

    def record(self, rec) -> Decimal:
        self.records.append(rec)
        return self.spent()
```

- [ ] **Step 2: Write the failing tests**

`tests/test_gateway.py`:
```python
from decimal import Decimal
from types import SimpleNamespace

import pytest

from scout.budget.guard import BudgetExceeded
from scout.llm.gateway import LLM, LLMRefusal, LLMTruncated, message_text
from tests.fakes import FakeClient, FakeGuard, FakeMessage, FakeUsage, text_block


def test_parse_records_cost_and_returns_parsed():
    guard = FakeGuard()
    msg = FakeMessage(content=[text_block('{"a": 1}')], parsed_output={"a": 1},
                      usage=FakeUsage(input_tokens=1_000_000, output_tokens=0))
    llm = LLM(FakeClient([msg]), guard, Decimal("0.92"))
    res = llm.parse(model="claude-haiku-5-5", output_format=dict, system="s", user="u",
                    est_eur=Decimal("0.01"))
    assert res.parsed == {"a": 1}
    assert res.cost_eur == Decimal("0.092000")  # $0.10 * 0.92
    rec = guard.records[0]
    assert rec.model == "claude-haiku-5-5" and rec.request_id == "req_fake" and rec.kind == "llm"
    call = llm.client.messages.calls[0]
    assert call["output_config"] == {"effort": "medium"}
    assert call["output_format"] is dict
    assert "thinking" not in call and "tool_choice" not in call


def test_check_happens_before_the_call():
    guard = FakeGuard(cap=Decimal("0.005"))
    client = FakeClient([FakeMessage()])
    llm = LLM(client, guard, Decimal("0.92"))
    with pytest.raises(BudgetExceeded):
        llm.parse(model="claude-haiku-5-5", output_format=dict, system="s", user="u",
                  est_eur=Decimal("0.01"))
    assert client.messages.calls == []


def test_refusal_and_truncation_raise_but_still_record_cost():
    guard = FakeGuard()
    refusal = FakeMessage(content=[], stop_reason="refusal")
    truncated = FakeMessage(content=[text_block("partial")], stop_reason="max_tokens")
    no_parse = FakeMessage(content=[text_block("{")], stop_reason="max_tokens", parsed_output=None)
    llm = LLM(FakeClient([refusal, truncated, no_parse]), guard, Decimal("0.92"))
    with pytest.raises(LLMRefusal):
        llm.create_text(model="claude-sonnet-5-5", system="s", user="u", est_eur=Decimal("0.01"))
    with pytest.raises(LLMTruncated):
        llm.create_text(model="claude-sonnet-5-5", system="s", user="u", est_eur=Decimal("0.01"))
    with pytest.raises(LLMTruncated):
        llm.parse(model="claude-haiku-5-5", output_format=dict, system="s", user="u",
                  est_eur=Decimal("0.01"))
    assert len(guard.records) == 3


def test_message_text_joins_text_blocks_only():
    msg = FakeMessage(content=[text_block("a"), SimpleNamespace(type="tool_use"), text_block("b")])
    assert message_text(msg) == "a\nb"
    llm = LLM(FakeClient([msg]), FakeGuard(), Decimal("0.92"))
    res = llm.create_text(model="claude-sonnet-5-5", system=[{"type": "text", "text": "s"}],
                          user="u", est_eur=Decimal("0"))
    assert res.text == "a\nb" and res.cache_read_tokens == 0
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `uv run pytest tests/test_gateway.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'scout.llm'`

- [ ] **Step 4: Write `scout/llm/gateway.py`**

`scout/llm/__init__.py`: empty file.

```python
"""One door to the Anthropic API: budget check, call, cost record, stop-reason policing."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from scout.budget.pricing import llm_cost_usd, to_eur, usage_units
from scout.db.repo import CostRecord

SystemPrompt = str | list[dict[str, Any]]


class LLMError(RuntimeError):
    pass


class LLMRefusal(LLMError):
    pass


class LLMTruncated(LLMError):
    pass


@dataclass
class LLMResult:
    text: str
    parsed: Any | None
    stop_reason: str
    cost_eur: Decimal
    cache_read_tokens: int
    request_id: str | None


def message_text(message) -> str:
    parts = [b.text for b in (getattr(message, "content", None) or []) if getattr(b, "type", None) == "text"]
    return "\n".join(parts).strip()


class LLM:
    def __init__(self, client, guard, usd_to_eur: Decimal) -> None:
        self.client = client
        self.guard = guard
        self.usd_to_eur = Decimal(usd_to_eur)

    def record_message(self, model: str, message, *, task_id: int | None = None) -> Decimal:
        units = usage_units(message.usage)
        eur = to_eur(llm_cost_usd(model, units), self.usd_to_eur)
        self.guard.record(CostRecord("llm", "anthropic", model, units, eur,
                                     request_id=getattr(message, "_request_id", None), task_id=task_id))
        return eur

    def _finish(self, model: str, message, task_id: int | None) -> LLMResult:
        cost = self.record_message(model, message, task_id=task_id)
        units = usage_units(message.usage)
        result = LLMResult(text=message_text(message), parsed=getattr(message, "parsed_output", None),
                           stop_reason=message.stop_reason, cost_eur=cost,
                           cache_read_tokens=units["cache_read_tokens"],
                           request_id=getattr(message, "_request_id", None))
        if result.stop_reason == "refusal":
            raise LLMRefusal(f"{model} refused (request {result.request_id})")
        return result

    def create_text(self, *, model: str, system: SystemPrompt, user: str, max_tokens: int = 1024,
                    effort: str = "medium", est_eur: Decimal, task_id: int | None = None) -> LLMResult:
        self.guard.check(est_eur)
        message = self.client.messages.create(
            model=model, max_tokens=max_tokens, system=system,
            messages=[{"role": "user", "content": user}], output_config={"effort": effort},
        )
        result = self._finish(model, message, task_id)
        if result.stop_reason == "max_tokens":
            raise LLMTruncated(f"{model} hit max_tokens={max_tokens} (request {result.request_id})")
        return result

    def parse(self, *, model: str, output_format: type, system: SystemPrompt, user: str,
              max_tokens: int = 4096, effort: str = "medium", est_eur: Decimal,
              task_id: int | None = None) -> LLMResult:
        self.guard.check(est_eur)
        message = self.client.messages.parse(
            model=model, max_tokens=max_tokens, system=system,
            messages=[{"role": "user", "content": user}], output_format=output_format,
            output_config={"effort": effort},
        )
        result = self._finish(model, message, task_id)
        if result.parsed is None:
            raise LLMTruncated(
                f"{model} returned no parsed output (stop_reason={result.stop_reason}, "
                f"request {result.request_id})"
            )
        return result
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `uv run pytest tests/test_gateway.py -v`
Expected: 4 PASSED

- [ ] **Step 6: Commit**

```bash
uv run ruff check . && uv run ruff format .
git add -A && git commit -m "feat(llm): budget-aware gateway over messages.create/parse with fakes"
```

---

### Task 8: ASKdata (Kosovo statistics) client

**Files:**
- Create: `scout/sources/__init__.py`, `scout/sources/types.py`, `scout/sources/askdata.py`
- Test: `tests/test_askdata.py`

**Interfaces:**
- Produces (`scout/sources/types.py`): `ChartEntry(rank: int, app_key: str, name: str, publisher: str, genres: tuple[str, ...], url: str)` (frozen), `AppHit(store: str, app_key: str, name: str, publisher: str, url: str)` (frozen), `PlaceHit(place_id, name, address, primary_type: str | None, business_status: str | None, lat: float | None, lng: float | None)` (frozen), `PlacesResult(count: int, places: list[PlaceHit])`.
- Produces (`scout/sources/askdata.py`): `DEFAULT_BASE_URL`, `PxItem(id, text, kind)`, `PxVariable(code, text, values, value_texts)`, `PxTable(title, variables)`, `PxData(columns: list[str], rows: list[dict])`, `AskDataClient(http: httpx.Client | None = None, base_url: str = DEFAULT_BASE_URL)` with `.list(path: str = "") -> list[PxItem]`, `.metadata(path) -> PxTable`, `.fetch(path, selections: dict[str, list[str]]) -> PxData`.

- [ ] **Step 1: Write `scout/sources/types.py`**

`scout/sources/__init__.py`: empty file.

```python
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ChartEntry:
    rank: int
    app_key: str
    name: str
    publisher: str
    genres: tuple[str, ...]
    url: str


@dataclass(frozen=True)
class AppHit:
    store: str  # "apple" | "play"
    app_key: str
    name: str
    publisher: str
    url: str


@dataclass(frozen=True)
class PlaceHit:
    place_id: str
    name: str
    address: str
    primary_type: str | None
    business_status: str | None
    lat: float | None
    lng: float | None


@dataclass
class PlacesResult:
    count: int
    places: list[PlaceHit] = field(default_factory=list)
```

- [ ] **Step 2: Write the failing tests**

`tests/test_askdata.py`:
```python
import json

import httpx
import pytest

from scout.sources.askdata import DEFAULT_BASE_URL, AskDataClient


def _client(handler):
    return AskDataClient(http=httpx.Client(transport=httpx.MockTransport(handler)))


def test_list_root_parses_folders_and_tables():
    def handler(request):
        assert str(request.url) == DEFAULT_BASE_URL + "/"
        return httpx.Response(200, json=[{"id": "Population", "type": "l", "text": "Population"},
                                         {"id": "tbl01.px", "type": "t", "text": "Pop by municipality"}])
    items = _client(handler).list()
    assert [(i.id, i.kind) for i in items] == [("Population", "l"), ("tbl01.px", "t")]


def test_path_segments_are_url_encoded_including_trailing_space():
    seen = {}

    def handler(request):
        seen["url"] = str(request.url)
        return httpx.Response(200, json=[])
    _client(handler).list("Labour market /Wages")
    assert seen["url"] == DEFAULT_BASE_URL + "/Labour%20market%20/Wages"


def test_metadata_and_fetch_strip_bom_and_post_query():
    def handler(request):
        if request.method == "GET":
            return httpx.Response(200, json={"title": "Population by year", "variables": [
                {"code": "Year", "text": "Year", "values": ["2023", "2024"], "valueTexts": ["2023", "2024"]}]})
        body = json.loads(request.content)
        assert body["query"] == [{"code": "Year", "selection": {"filter": "item", "values": ["2024"]}}]
        assert body["response"] == {"format": "json"}
        payload = {"columns": [{"code": "Year", "text": "Year"}, {"code": "Pop", "text": "Population"}],
                   "data": [{"key": ["2024"], "values": ["1586659"]}]}
        return httpx.Response(200, content=("﻿" + json.dumps(payload)).encode("utf-8"))
    c = _client(handler)
    meta = c.metadata("Population/tbl01.px")
    assert meta.title == "Population by year" and meta.variables[0].values == ["2023", "2024"]
    data = c.fetch("Population/tbl01.px", {"Year": ["2024"]})
    assert data.columns == ["Year", "Population"] and data.rows[0]["values"] == ["1586659"]


def test_http_error_raises():
    def handler(request):
        return httpx.Response(500, text="boom")
    with pytest.raises(httpx.HTTPStatusError):
        _client(handler).list()


@pytest.mark.network
def test_live_root_lists_population_folder():
    ids = [i.id for i in AskDataClient().list()]
    assert "Population" in ids
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `uv run pytest tests/test_askdata.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'scout.sources.askdata'`

- [ ] **Step 4: Write `scout/sources/askdata.py`**

```python
"""Kosovo Agency of Statistics (ASK) PxWeb API v1 client — free, official numbers."""

from __future__ import annotations

import json
from dataclasses import dataclass
from urllib.parse import quote

import httpx

DEFAULT_BASE_URL = "https://askdata.rks-gov.net/api/v1/en/ASKdata"
USER_AGENT = "kosovo-gap-scout/0.1 (+research; contact via GitHub)"


@dataclass
class PxItem:
    id: str
    text: str
    kind: str  # "l" = folder, "t" = table


@dataclass
class PxVariable:
    code: str
    text: str
    values: list[str]
    value_texts: list[str]


@dataclass
class PxTable:
    title: str
    variables: list[PxVariable]


@dataclass
class PxData:
    columns: list[str]
    rows: list[dict]  # each {"key": [...], "values": [...]}


def _json(response: httpx.Response):
    response.raise_for_status()
    return json.loads(response.text.lstrip("﻿"))  # PxWeb prefixes JSON with a BOM


class AskDataClient:
    def __init__(self, http: httpx.Client | None = None, base_url: str = DEFAULT_BASE_URL,
                 timeout: float = 30.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.http = http or httpx.Client(timeout=timeout, headers={"User-Agent": USER_AGENT})

    def _url(self, path: str) -> str:
        segments = [quote(s, safe="") for s in path.split("/") if s != ""]
        if not segments:
            return self.base_url + "/"
        return "/".join([self.base_url, *segments])

    def list(self, path: str = "") -> list[PxItem]:
        items = _json(self.http.get(self._url(path)))
        return [PxItem(id=i["id"], text=i.get("text", ""), kind=i.get("type", "")) for i in items]

    def metadata(self, path: str) -> PxTable:
        d = _json(self.http.get(self._url(path)))
        return PxTable(
            title=d.get("title", ""),
            variables=[PxVariable(code=v["code"], text=v.get("text", ""), values=list(v.get("values", [])),
                                  value_texts=list(v.get("valueTexts", []))) for v in d.get("variables", [])],
        )

    def fetch(self, path: str, selections: dict[str, list[str]]) -> PxData:
        query = [{"code": code, "selection": {"filter": "item", "values": list(values)}}
                 for code, values in selections.items()]
        d = _json(self.http.post(self._url(path), json={"query": query, "response": {"format": "json"}}))
        return PxData(columns=[c.get("text", c.get("code", "")) for c in d.get("columns", [])],
                      rows=list(d.get("data", [])))
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `uv run pytest tests/test_askdata.py -v` (then once by hand: `uv run pytest tests/test_askdata.py -m network -v`)
Expected: 4 PASSED, 1 deselected; the network test passes when run by hand.

- [ ] **Step 6: Commit**

```bash
uv run ruff check . && uv run ruff format .
git add -A && git commit -m "feat(sources): ASKdata PxWeb client and shared source types"
```

---

### Task 9: Apple top charts and iTunes search

**Files:**
- Create: `scout/sources/apple.py`
- Test: `tests/test_apple.py`

**Interfaces:**
- Produces: `RSS_URL`, `SEARCH_URL`, `fetch_top_free(country: str, limit: int = 25, http: httpx.Client | None = None) -> list[ChartEntry]`, `search_apps(term: str, country: str = "xk", limit: int = 10, http: httpx.Client | None = None) -> list[AppHit]`.

- [ ] **Step 1: Write the failing tests**

`tests/test_apple.py`:
```python
import httpx
import pytest

from scout.sources import apple


def test_fetch_top_free_maps_rss_feed():
    def handler(request):
        assert str(request.url) == "https://rss.marketingtools.apple.com/api/v2/xk/apps/top-free/25/apps.json"
        return httpx.Response(200, json={"feed": {"results": [
            {"id": "1", "name": "Wolt", "artistName": "Wolt Enterprises", "genres": [{"name": "Food & Drink"}],
             "url": "https://apps.apple.com/xk/app/wolt/id1"},
            {"id": "2", "name": "APTV", "artistName": "Artmotion", "genres": [], "url": "u2"}]}})
    entries = apple.fetch_top_free("XK", http=httpx.Client(transport=httpx.MockTransport(handler)))
    assert [(e.rank, e.app_key, e.name) for e in entries] == [(1, "1", "Wolt"), (2, "2", "APTV")]
    assert entries[0].genres == ("Food & Drink",) and entries[0].publisher == "Wolt Enterprises"


def test_search_apps_uses_country_and_software_entity():
    def handler(request):
        assert request.url.params["country"] == "xk" and request.url.params["entity"] == "software"
        assert request.url.params["term"] == "dentist booking"
        return httpx.Response(200, json={"resultCount": 1, "results": [
            {"trackId": 99, "trackName": "DentApp", "sellerName": "X", "trackViewUrl": "https://a"}]})
    hits = apple.search_apps("dentist booking", http=httpx.Client(transport=httpx.MockTransport(handler)))
    assert hits == [apple.AppHit(store="apple", app_key="99", name="DentApp", publisher="X", url="https://a")]


@pytest.mark.network
def test_live_xk_chart_has_entries():
    assert len(apple.fetch_top_free("xk", limit=10)) >= 5
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_apple.py -v`
Expected: FAIL with `ImportError: cannot import name 'apple'`

- [ ] **Step 3: Write `scout/sources/apple.py`**

```python
"""Apple App Store signals: top-free charts (RSS, 8 countries) and keyword presence checks."""

from __future__ import annotations

import httpx

from scout.sources.askdata import USER_AGENT
from scout.sources.types import AppHit, ChartEntry

RSS_URL = "https://rss.marketingtools.apple.com/api/v2/{country}/apps/top-free/{limit}/apps.json"
SEARCH_URL = "https://itunes.apple.com/search"


def _http(http: httpx.Client | None) -> httpx.Client:
    return http or httpx.Client(timeout=30.0, headers={"User-Agent": USER_AGENT}, follow_redirects=True)


def fetch_top_free(country: str, limit: int = 25, http: httpx.Client | None = None) -> list[ChartEntry]:
    r = _http(http).get(RSS_URL.format(country=country.lower(), limit=limit))
    r.raise_for_status()
    results = r.json().get("feed", {}).get("results", [])
    return [
        ChartEntry(rank=i + 1, app_key=str(a["id"]), name=a.get("name", ""),
                   publisher=a.get("artistName", ""),
                   genres=tuple(g.get("name", "") for g in a.get("genres", [])), url=a.get("url", ""))
        for i, a in enumerate(results)
    ]


def search_apps(term: str, country: str = "xk", limit: int = 10,
                http: httpx.Client | None = None) -> list[AppHit]:
    r = _http(http).get(SEARCH_URL, params={"term": term, "country": country, "entity": "software",
                                             "limit": limit})
    r.raise_for_status()
    return [
        AppHit(store="apple", app_key=str(a["trackId"]), name=a.get("trackName", ""),
               publisher=a.get("sellerName", ""), url=a.get("trackViewUrl", ""))
        for a in r.json().get("results", [])
    ]
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_apple.py -v`
Expected: 2 PASSED, 1 deselected

- [ ] **Step 5: Commit**

```bash
uv run ruff check . && uv run ruff format .
git add -A && git commit -m "feat(sources): Apple top-free charts and iTunes search"
```

---

### Task 10: Google Play top charts and search

**Files:**
- Create: `scout/sources/play.py`
- Test: `tests/test_play.py`

**Interfaces:**
- Produces: `TOP_FREE_URL`, `APP_ID_RE`, `fetch_top_free(country: str = "XK", limit: int = 25, http: httpx.Client | None = None) -> list[ChartEntry]`, `search_apps(term: str, country: str = "xk", lang: str = "sq", limit: int = 10, search_fn=None) -> list[AppHit]`, `app_details(app_id: str, country: str = "xk", app_fn=None) -> AppHit`.

- [ ] **Step 1: Write the failing tests**

`tests/test_play.py`:
```python
import httpx
import pytest

from scout.sources import play

HTML = """
<a href="/store/apps/details?id=com.wolt.android&gl=XK">Wolt</a>
<a href="/store/apps/details?id=com.wolt.android">Wolt again</a>
<a href="/store/apps/details?id=al.gjirafa.mall">GjirafaMall</a>
<a href="/store/apps/details?id=com.aptv.app">APTV</a>
"""


def test_fetch_top_free_dedupes_and_limits():
    def handler(request):
        assert request.url.params["gl"] == "XK"
        return httpx.Response(200, text=HTML)
    entries = play.fetch_top_free("xk", limit=2, http=httpx.Client(transport=httpx.MockTransport(handler)))
    assert [(e.rank, e.app_key) for e in entries] == [(1, "com.wolt.android"), (2, "al.gjirafa.mall")]
    assert entries[0].url.endswith("details?id=com.wolt.android&gl=XK")


def test_regex_matches_dotted_ids_only():
    assert play.APP_ID_RE.findall("x /store/apps/details?id=com.a_b.c9&hl=en y") == ["com.a_b.c9"]


def test_search_apps_wraps_google_play_scraper():
    calls = {}

    def fake_search(term, n_hits, lang, country):
        calls.update(term=term, n_hits=n_hits, lang=lang, country=country)
        return [{"appId": "com.x", "title": "X", "developer": "Dev"}]
    hits = play.search_apps("dentist", search_fn=fake_search)
    assert calls == {"term": "dentist", "n_hits": 10, "lang": "sq", "country": "xk"}
    assert hits[0] == play.AppHit(store="play", app_key="com.x", name="X", publisher="Dev",
                                  url="https://play.google.com/store/apps/details?id=com.x")


def test_app_details_wraps_app_lookup():
    hit = play.app_details("com.x", app_fn=lambda app_id, lang, country: {"appId": app_id, "title": "X",
                                                                          "developer": "D"})
    assert hit.name == "X" and hit.store == "play"


@pytest.mark.network
def test_live_play_search_kosovo():
    assert play.search_apps("taxi", limit=3)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_play.py -v`
Expected: FAIL with `ImportError: cannot import name 'play'`

- [ ] **Step 3: Write `scout/sources/play.py`**

```python
"""Google Play signals for Kosovo (gl=XK): top-free chart ids by regex, search via google-play-scraper."""

from __future__ import annotations

import re
from collections.abc import Callable

import httpx

from scout.sources.askdata import USER_AGENT
from scout.sources.types import AppHit, ChartEntry

TOP_FREE_URL = "https://play.google.com/store/apps/collection/topselling_free"
APP_ID_RE = re.compile(r"/store/apps/details\?id=([\w.]+)")
DETAILS_URL = "https://play.google.com/store/apps/details?id={app_id}"
BROWSER_UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
              "Chrome/128.0 Safari/537.36 " + USER_AGENT)


def fetch_top_free(country: str = "XK", limit: int = 25, http: httpx.Client | None = None) -> list[ChartEntry]:
    client = http or httpx.Client(timeout=30.0, headers={"User-Agent": BROWSER_UA}, follow_redirects=True)
    r = client.get(TOP_FREE_URL, params={"gl": country.upper(), "hl": "en"})
    r.raise_for_status()
    ids: list[str] = []
    for m in APP_ID_RE.finditer(r.text):
        app_id = m.group(1)
        if app_id not in ids:
            ids.append(app_id)
        if len(ids) >= limit:
            break
    return [
        ChartEntry(rank=i + 1, app_key=app_id, name=app_id, publisher="", genres=(),
                   url=f"{DETAILS_URL.format(app_id=app_id)}&gl={country.upper()}")
        for i, app_id in enumerate(ids)
    ]


def _gps_search(term: str, n_hits: int, lang: str, country: str) -> list[dict]:
    from google_play_scraper import search

    return search(term, n_hits=n_hits, lang=lang, country=country)


def _gps_app(app_id: str, lang: str, country: str) -> dict:
    from google_play_scraper import app

    return app(app_id, lang=lang, country=country)


def _hit(d: dict) -> AppHit:
    app_id = d["appId"]
    return AppHit(store="play", app_key=app_id, name=d.get("title", ""), publisher=d.get("developer", ""),
                  url=DETAILS_URL.format(app_id=app_id))


def search_apps(term: str, country: str = "xk", lang: str = "sq", limit: int = 10,
                search_fn: Callable | None = None) -> list[AppHit]:
    fn = search_fn or _gps_search
    return [_hit(d) for d in fn(term, n_hits=limit, lang=lang, country=country)]


def app_details(app_id: str, country: str = "xk", app_fn: Callable | None = None) -> AppHit:
    fn = app_fn or _gps_app
    return _hit(fn(app_id, lang="en", country=country))
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_play.py -v`
Expected: 4 PASSED, 1 deselected

- [ ] **Step 5: Verify the chart HTML assumption live (spec B19 #2), then commit**

Run: `uv run python -c "from scout.sources import play; e = play.fetch_top_free('XK', 10); print(len(e), [x.app_key for x in e][:5])"`
Expected: 10 ids printed. If 0 ids are printed, Google changed the collection page: set `TOP_FREE_URL = "https://play.google.com/store/apps?gl=XK&hl=en"` style browsing URL and re-run; record the outcome in `README.md` under a "Source notes" heading.

```bash
uv run ruff check . && uv run ruff format .
git add -A && git commit -m "feat(sources): Google Play top-free chart ids and search wrappers"
```

---

### Task 11: Google Places text search (Pro field mask)

**Files:**
- Create: `scout/sources/places.py`
- Test: `tests/test_places.py`

**Interfaces:**
- Produces: `PLACES_URL`, `PRO_FIELD_MASK`, `PlacesError`, `PlacesClient(api_key: str, http: httpx.Client | None = None)` with `.text_search(query: str, *, region_code: str | None = "XK", language: str = "sq", page_size: int = 20) -> PlacesResult`.

- [ ] **Step 1: Write the failing tests**

`tests/test_places.py`:
```python
import json

import httpx
import pytest

from scout.sources.places import PRO_FIELD_MASK, PlacesClient, PlacesError

RESPONSE = {"places": [{
    "id": "ChIJ1", "displayName": {"text": "Klinika Dentare Smile", "languageCode": "sq"},
    "formattedAddress": "Rr. Agim Ramadani, Prishtinë", "primaryType": "dentist",
    "types": ["dentist", "health"], "businessStatus": "OPERATIONAL",
    "location": {"latitude": 42.66, "longitude": 21.16}}]}


def test_text_search_sends_pro_mask_and_parses():
    def handler(request):
        assert request.headers["X-Goog-Api-Key"] == "k"
        assert request.headers["X-Goog-FieldMask"] == PRO_FIELD_MASK
        body = json.loads(request.content)
        assert body == {"textQuery": "dentist Prishtinë", "languageCode": "sq", "pageSize": 20,
                        "regionCode": "XK"}
        return httpx.Response(200, json=RESPONSE)
    res = PlacesClient("k", http=httpx.Client(transport=httpx.MockTransport(handler))).text_search(
        "dentist Prishtinë")
    assert res.count == 1
    p = res.places[0]
    assert (p.name, p.primary_type, p.business_status, p.lat) == ("Klinika Dentare Smile", "dentist",
                                                                 "OPERATIONAL", 42.66)


def test_empty_result_and_errors():
    def handler(request):
        body = json.loads(request.content)
        if body["textQuery"] == "nothing":
            return httpx.Response(200, json={})
        return httpx.Response(403, json={"error": {"message": "API key not valid"}})
    c = PlacesClient("k", http=httpx.Client(transport=httpx.MockTransport(handler)))
    assert c.text_search("nothing").count == 0
    with pytest.raises(PlacesError):
        c.text_search("boom")


def test_region_code_rejected_falls_back_to_kosovo_in_query():
    bodies = []

    def handler(request):
        body = json.loads(request.content)
        bodies.append(body)
        if "regionCode" in body:
            return httpx.Response(400, json={"error": {"message": "Invalid value at 'region_code'"}})
        return httpx.Response(200, json=RESPONSE)
    res = PlacesClient("k", http=httpx.Client(transport=httpx.MockTransport(handler))).text_search("dentist")
    assert res.count == 1
    assert bodies[1]["textQuery"] == "dentist Kosovo" and "regionCode" not in bodies[1]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_places.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'scout.sources.places'`

- [ ] **Step 3: Write `scout/sources/places.py`**

```python
"""Google Places API (New) text search, restricted to the Pro SKU fields (5,000 free calls/month)."""

from __future__ import annotations

import httpx

from scout.sources.types import PlaceHit, PlacesResult

PLACES_URL = "https://places.googleapis.com/v1/places:searchText"
PRO_FIELD_MASK = ("places.id,places.displayName,places.formattedAddress,places.primaryType,"
                  "places.types,places.businessStatus,places.location")


class PlacesError(RuntimeError):
    pass


class PlacesClient:
    def __init__(self, api_key: str, http: httpx.Client | None = None, timeout: float = 20.0) -> None:
        self.api_key = api_key
        self.http = http or httpx.Client(timeout=timeout)

    def _post(self, body: dict) -> httpx.Response:
        return self.http.post(PLACES_URL, json=body, headers={
            "X-Goog-Api-Key": self.api_key, "X-Goog-FieldMask": PRO_FIELD_MASK,
            "Content-Type": "application/json"})

    def text_search(self, query: str, *, region_code: str | None = "XK", language: str = "sq",
                    page_size: int = 20) -> PlacesResult:
        body = {"textQuery": query, "languageCode": language, "pageSize": page_size}
        if region_code:
            body["regionCode"] = region_code
        r = self._post(body)
        if r.status_code == 400 and region_code and "region" in r.text.lower():
            # Spec B19 #1: if XK is not an accepted region code, anchor the query textually instead.
            body = {"textQuery": f"{query} Kosovo", "languageCode": language, "pageSize": page_size}
            r = self._post(body)
        if r.status_code >= 400:
            raise PlacesError(f"places {r.status_code}: {r.text[:300]}")
        places = r.json().get("places", [])
        hits = [
            PlaceHit(place_id=p.get("id", ""), name=(p.get("displayName") or {}).get("text", ""),
                     address=p.get("formattedAddress", ""), primary_type=p.get("primaryType"),
                     business_status=p.get("businessStatus"),
                     lat=(p.get("location") or {}).get("latitude"),
                     lng=(p.get("location") or {}).get("longitude"))
            for p in places
        ]
        return PlacesResult(count=len(hits), places=hits)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_places.py -v`
Expected: 3 PASSED

- [ ] **Step 5: Commit**

```bash
uv run ruff check . && uv run ruff format .
git add -A && git commit -m "feat(sources): Google Places text search with Pro field mask"
```

---

### Task 12: Web tool definitions and the worker's custom tools

**Files:**
- Create: `scout/sources/web.py`, `scout/worker/__init__.py`, `scout/worker/tools.py`
- Test: `tests/test_web.py`, `tests/test_worker_tools.py`

**Interfaces:**
- Consumes: `repo.*` (Tasks 4–5), `AskDataClient` (Task 8), `apple.search_apps` (Task 9), `play.search_apps` (Task 10), `PlacesClient` (Task 11), `CostRecord`.
- Produces (`scout/sources/web.py`): `web_tools(max_searches: int = 12, max_fetches: int = 8) -> list[dict]`.
- Produces (`scout/worker/tools.py`):
  - `ToolContext(session, guard, now: datetime, run_id: int | None, task_id: int | None, places: PlacesClient | None, askdata: AskDataClient, apple_search=apple.search_apps, play_search=play.search_apps, places_monthly_quota: int = 4500, events: list[dict])`
  - `FACT_ENTITY_TYPES`, `PRESENCE_LEVELS`, `DIGEST_PREFIXES`, `KB_RESULT_LIMIT = 2000`, `SOURCE_RESULT_LIMIT = 1200`
  - `*_impl(ctx, ...) -> str` for `kb_search, kb_record_fact, kb_record_business, kb_record_proven_model, kb_propose_gap, kb_write_digest, places_search, app_store_search, askdata_list, askdata_table, askdata_fetch`
  - `build_tools(ctx) -> list` of `@beta_tool` functions with exactly those eleven names; `TOOL_NAMES` tuple.

Note: `kb_write_digest` is an addition to the spec's B5 tool list — B5's `map-sector` and `culture` profiles must "build/refresh a digest" and B13 says the worker updates digests through `kb_*` tools, so the tool is required.

- [ ] **Step 1: Write the failing test for web tool definitions**

`tests/test_web.py`:
```python
from scout.sources.web import web_tools


def test_web_tools_use_dynamic_filtering_types_and_caps():
    assert web_tools(12, 8) == [
        {"type": "web_search_20260209", "name": "web_search", "max_uses": 12},
        {"type": "web_fetch_20260209", "name": "web_fetch", "max_uses": 8},
    ]
```

- [ ] **Step 2: Write `scout/sources/web.py`**

```python
"""Anthropic server tools (run on Anthropic's side; priced per search + tokens)."""

from __future__ import annotations


def web_tools(max_searches: int = 12, max_fetches: int = 8) -> list[dict]:
    return [
        {"type": "web_search_20260209", "name": "web_search", "max_uses": max_searches},
        {"type": "web_fetch_20260209", "name": "web_fetch", "max_uses": max_fetches},
    ]
```

Run: `uv run pytest tests/test_web.py -v` → 1 PASSED.

- [ ] **Step 3: Write the failing tests for the worker tools**

`tests/test_worker_tools.py`:
```python
import json
from datetime import UTC, date, datetime
from decimal import Decimal

import httpx
import pytest

from scout.budget.guard import BudgetGuard
from scout.db import repo
from scout.sources.askdata import AskDataClient
from scout.sources.places import PlacesClient
from scout.sources.types import AppHit
from scout.worker import tools as T

pytestmark = pytest.mark.db
NOW = datetime(2026, 10, 19, 6, 0, tzinfo=UTC)
DAY = date(2026, 10, 19)


def _places_http():
    def handler(request):
        return httpx.Response(200, json={"places": [{"id": "p1", "displayName": {"text": "Vet Prizren"},
                                                     "formattedAddress": "Prizren", "primaryType": "veterinary_care",
                                                     "businessStatus": "OPERATIONAL"}]})
    return httpx.Client(transport=httpx.MockTransport(handler))


def _askdata_http():
    def handler(request):
        if request.method == "POST":
            return httpx.Response(200, json={"columns": [{"code": "Y", "text": "Year"}],
                                             "data": [{"key": ["2024"], "values": ["1"]}]})
        if request.url.path.endswith(".px"):
            return httpx.Response(200, json={"title": "T", "variables": [
                {"code": "Y", "text": "Year", "values": ["2024"], "valueTexts": ["2024"]}]})
        return httpx.Response(200, json=[{"id": "Population", "type": "l", "text": "Population"}])
    return httpx.Client(transport=httpx.MockTransport(handler))


@pytest.fixture
def ctx(db_session):
    repo.get_or_create_sector(db_session, "pets", "Pets")
    run = repo.start_run(db_session, day=DAY, phase="foundation", budget_cap_eur=Decimal("3"), started_at=NOW)
    guard = BudgetGuard(db_session, day=DAY, daily_cap_eur=Decimal("3"), run_id=run.id)
    return T.ToolContext(
        session=db_session, guard=guard, now=NOW, run_id=run.id, task_id=None,
        places=PlacesClient("k", http=_places_http()), askdata=AskDataClient(http=_askdata_http()),
        apple_search=lambda term, country, limit: [AppHit("apple", "1", "PetApp", "X", "https://a")],
        play_search=lambda term, country, lang, limit: [],
    )


def test_record_fact_then_search_returns_it_with_digest(ctx):
    out = T.kb_record_fact_impl(ctx, claim="Prizren has 3 pet shops", entity_type="sector", entity_key="pets",
                                confidence=0.7, source_url="https://x", sector="pets", ttl_days=30,
                                value_json='{"count": 3}')
    assert out.startswith("fact #")
    T.kb_write_digest_impl(ctx, key="sector:pets", title="Pets", body_md="# Pets\nSmall but growing.")
    res = T.kb_search_impl(ctx, query="pet shops Prizren", sector="pets")
    assert "DIGEST:" in res and "[0.70] Prizren has 3 pet shops" in res and "<https://x>" in res
    assert len(res) <= T.KB_RESULT_LIMIT


def test_record_fact_rejects_bad_entity_type_and_clamps_confidence(ctx):
    assert T.kb_record_fact_impl(ctx, claim="x", entity_type="rumour", entity_key="k", confidence=0.5) \
        .startswith("error:")
    T.kb_record_fact_impl(ctx, claim="y", entity_type="culture", entity_key="k", confidence=7)
    assert repo.search_facts(ctx.session, "y", now=NOW)[0].confidence == 1.0


def test_business_model_gap_tools(ctx):
    assert T.kb_record_business_impl(ctx, name="PetShop KS", sector="pets", city="Prishtinë",
                                     instagram="petshopks").startswith("business #")
    assert repo.list_businesses(ctx.session, "pets")[0].channels == {"instagram": "petshopks"}
    out = T.kb_record_proven_model_impl(
        ctx, slug="pet-sitting-marketplace", name="Pet sitting marketplace", sector="pets",
        description="Rover-style", markets_json=json.dumps([{"country": "HR", "example": "Pawshake", "url": "u"}]))
    assert "nearby markets: 1" in out
    first = T.kb_propose_gap_impl(ctx, title="Pet sitting marketplace", sector="pets", hypothesis="h",
                                  presence_level="unknown", proven_model_slug="pet-sitting-marketplace")
    again = T.kb_propose_gap_impl(ctx, title="pet sitting MARKETPLACE", sector="pets", hypothesis="h2")
    assert "(new)" in first and "(existing)" in again
    assert T.kb_propose_gap_impl(ctx, title="x", sector="pets", hypothesis="h", presence_level="maybe") \
        .startswith("error:")


def test_write_digest_validates_key_and_length(ctx):
    assert T.kb_write_digest_impl(ctx, key="random", title="t", body_md="b").startswith("error:")
    long_body = "x" * 6000
    T.kb_write_digest_impl(ctx, key="culture:payments-and-trust", title="t", body_md=long_body)
    assert len(repo.get_digest(ctx.session, "culture:payments-and-trust")) == T.DIGEST_CHAR_LIMIT


def test_places_search_records_cost_and_respects_quota(ctx):
    out = T.places_search_impl(ctx, query="veteriner", city="Prizren")
    assert "Vet Prizren" in out and "veterinary_care" in out
    assert repo.places_calls_in_month(ctx.session, DAY) == 1
    ctx.places_monthly_quota = 1
    assert "quota" in T.places_search_impl(ctx, query="veteriner", city="Pejë")
    ctx.places = None
    assert "unavailable" in T.places_search_impl(ctx, query="x")


def test_app_store_search_merges_stores_and_survives_errors(ctx):
    out = T.app_store_search_impl(ctx, term="pet", store="both")
    assert "[apple] PetApp" in out and "play: 0 results" in out

    def boom(term, country, limit):
        raise RuntimeError("down")
    ctx.apple_search = boom
    assert "apple: error" in T.app_store_search_impl(ctx, term="pet", store="apple")


def test_askdata_tools(ctx):
    assert "Population" in T.askdata_list_impl(ctx, path="")
    assert "Year" in T.askdata_table_impl(ctx, path="Population/t.px")
    out = T.askdata_fetch_impl(ctx, path="Population/t.px", selections_json='{"Y": ["2024"]}')
    assert "2024" in out and "1" in out
    assert T.askdata_fetch_impl(ctx, path="Population/t.px", selections_json="not json").startswith("error:")


def test_build_tools_names_and_schemas(ctx):
    tools = T.build_tools(ctx)
    assert [t.name for t in tools] == list(T.TOOL_NAMES)
    schema = next(t for t in tools if t.name == "kb_record_fact").to_dict()["input_schema"]
    assert set(schema["required"]) >= {"claim", "entity_type", "entity_key", "confidence"}
    assert tools[0].call({"query": "pet", "sector": "pets"}).startswith(("DIGEST", "no facts", "- ["))
    assert len(ctx.events) == 1 and ctx.events[0]["tool"] == "kb_search"
```

- [ ] **Step 4: Run the tests to verify they fail**

Run: `TEST_DATABASE_URL=<url> uv run pytest tests/test_worker_tools.py -v`
Expected: FAIL with `ImportError: cannot import name 'tools'`

- [ ] **Step 5: Write `scout/worker/tools.py`**

`scout/worker/__init__.py`: empty file.

```python
"""Custom tools the research worker can call. Each tool is a thin closure over a testable *_impl."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

from anthropic import beta_tool
from sqlalchemy.orm import Session

from scout.db import repo
from scout.db.repo import CostRecord, FactIn
from scout.sources import apple, play
from scout.sources.askdata import AskDataClient
from scout.sources.places import PlacesClient

FACT_ENTITY_TYPES = ("sector", "business", "proven_model", "gap", "culture", "stat", "news",
                     "presence_check", "demand_test", "payment_path")
PRESENCE_LEVELS = ("absent", "exists-but-poor", "prishtina-only", "offline-only", "decent", "unknown")
DIGEST_PREFIXES = ("sector:", "culture:", "country")
KB_RESULT_LIMIT = 2000
SOURCE_RESULT_LIMIT = 1200
DIGEST_CHAR_LIMIT = 5000  # ≈ 1,200 tokens (spec B13)

TOOL_NAMES = ("kb_search", "kb_record_fact", "kb_record_business", "kb_record_proven_model",
              "kb_propose_gap", "kb_write_digest", "places_search", "app_store_search",
              "askdata_list", "askdata_table", "askdata_fetch")


@dataclass
class ToolContext:
    session: Session
    guard: object  # BudgetGuard or test fake: spent/remaining/can_afford/check/record/day
    now: datetime
    run_id: int | None
    task_id: int | None
    places: PlacesClient | None
    askdata: AskDataClient
    apple_search: Callable = apple.search_apps
    play_search: Callable = play.search_apps
    places_monthly_quota: int = 4500
    events: list[dict] = field(default_factory=list)


def _clip(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _or_none(value: str) -> str | None:
    return value.strip() or None


# ---------- knowledge base ----------

def kb_search_impl(ctx: ToolContext, query: str, sector: str = "") -> str:
    sector_slug = _or_none(sector)
    lines: list[str] = []
    if sector_slug:
        digest = repo.get_digest(ctx.session, f"sector:{sector_slug}")
        if digest:
            lines.append("DIGEST:\n" + digest[:800])
    facts = repo.search_facts(ctx.session, query, sector_slug=sector_slug, limit=15, now=ctx.now)
    for f in facts:
        line = f"- [{f.confidence:.2f}] {f.claim} ({f.source_name}; {f.observed_at.date().isoformat()})"
        if f.source_url:
            line += f" <{f.source_url}>"
        lines.append(line)
    return _clip("\n".join(lines) or "no facts yet", KB_RESULT_LIMIT)


def kb_record_fact_impl(ctx: ToolContext, claim: str, entity_type: str, entity_key: str, confidence: float,
                        source_url: str = "", sector: str = "", ttl_days: int = 90,
                        value_json: str = "") -> str:
    if entity_type not in FACT_ENTITY_TYPES:
        return f"error: entity_type must be one of {', '.join(FACT_ENTITY_TYPES)}"
    if not claim.strip():
        return "error: claim is empty"
    value = None
    if value_json.strip():
        try:
            value = json.loads(value_json)
        except json.JSONDecodeError:
            value = {"raw": value_json[:500]}
    fact = repo.upsert_fact(
        ctx.session,
        FactIn(claim=claim, entity_type=entity_type, entity_key=entity_key.strip(),
               confidence=min(max(float(confidence), 0.0), 1.0), source_url=_or_none(source_url),
               sector_slug=_or_none(sector), value=value, ttl_days=max(1, min(int(ttl_days), 365))),
        run_id=ctx.run_id, observed_at=ctx.now,
    )
    return f"fact #{fact.id} saved (confidence {fact.confidence:.2f}, expires {fact.expires_at.date()})"


def kb_record_business_impl(ctx: ToolContext, name: str, sector: str, kind: str = "local", city: str = "",
                            instagram: str = "", website: str = "", facebook: str = "", note: str = "") -> str:
    if not name.strip() or not sector.strip():
        return "error: name and sector are required"
    channels = {k: v.strip() for k, v in (("instagram", instagram), ("website", website),
                                          ("facebook", facebook)) if v.strip()}
    b = repo.upsert_business(ctx.session, name=name, sector_slug=sector.strip(), kind=kind or "local",
                             city=_or_none(city), channels=channels, note=_or_none(note), seen_at=ctx.now)
    return f"business #{b.id} saved ({b.name}, {b.city or 'city unknown'})"


def kb_record_proven_model_impl(ctx: ToolContext, slug: str, name: str, sector: str, description: str,
                                markets_json: str, business_model: str = "", source_urls_json: str = "") -> str:
    try:
        markets = json.loads(markets_json) if markets_json.strip() else []
        source_urls = json.loads(source_urls_json) if source_urls_json.strip() else []
    except json.JSONDecodeError as e:
        return f"error: invalid JSON ({e.msg})"
    if not isinstance(markets, list) or not all(isinstance(m, dict) and m.get("country") for m in markets):
        return 'error: markets_json must be a list of {"country": "HR", "example": "...", "url": "..."}'
    pm = repo.upsert_proven_model(ctx.session, slug=repo.slugify(slug), name=name, sector_slug=sector.strip(),
                                  description=description, markets=markets,
                                  business_model=_or_none(business_model),
                                  source_urls=[str(u) for u in source_urls])
    return f"proven model '{pm.slug}' saved (markets: {len(pm.markets)}, nearby markets: {pm.nearby_count})"


def kb_propose_gap_impl(ctx: ToolContext, title: str, sector: str, hypothesis: str,
                        presence_level: str = "unknown", proven_model_slug: str = "",
                        why_not_yet: str = "") -> str:
    if presence_level not in PRESENCE_LEVELS:
        return f"error: presence_level must be one of {', '.join(PRESENCE_LEVELS)}"
    if not title.strip() or not sector.strip():
        return "error: title and sector are required"
    gap, created = repo.propose_gap(ctx.session, title=title, sector_slug=sector.strip(),
                                    proven_model_slug=_or_none(proven_model_slug), hypothesis_md=hypothesis,
                                    presence_level=presence_level, why_not_yet_md=why_not_yet, run_id=ctx.run_id)
    return f"gap #{gap.id} {'(new)' if created else '(existing)'}: {gap.title} [status {gap.status}]"


def kb_write_digest_impl(ctx: ToolContext, key: str, title: str, body_md: str) -> str:
    key = key.strip()
    if not (key == "country" or key.startswith(("sector:", "culture:"))):
        return f"error: key must be 'country', 'sector:<slug>' or 'culture:<theme>' (got {key!r})"
    body = body_md.strip()[:DIGEST_CHAR_LIMIT]
    repo.set_digest(ctx.session, key, title.strip() or key, body, now=ctx.now)
    return f"digest {key} saved ({len(body)} chars; limit {DIGEST_CHAR_LIMIT})"


# ---------- Tier A sources ----------

def places_search_impl(ctx: ToolContext, query: str, city: str = "", language: str = "sq") -> str:
    if ctx.places is None:
        return "places_search unavailable (no GOOGLE_PLACES_API_KEY configured) — use web_search instead"
    if repo.places_calls_in_month(ctx.session, ctx.guard.day) >= ctx.places_monthly_quota:
        return "places_search quota exhausted for this month — use web_search instead"
    if not ctx.guard.can_afford(Decimal("0")):
        return "budget exhausted — stop researching and write your summary"
    q = f"{query.strip()} {city.strip()}".strip()
    result = ctx.places.text_search(q, language=language or "sq")
    ctx.guard.record(CostRecord("places", "google", None, {"calls": 1}, Decimal("0"), task_id=ctx.task_id))
    lines = [f"{result.count} places for {q!r}"]
    lines += [f"- {p.name} | {p.address} | {p.primary_type or '-'} | {p.business_status or '-'}"
              for p in result.places[:15]]
    return _clip("\n".join(lines), SOURCE_RESULT_LIMIT)


def app_store_search_impl(ctx: ToolContext, term: str, store: str = "both") -> str:
    lines: list[str] = []
    if store in ("apple", "both"):
        try:
            hits = ctx.apple_search(term, country="xk", limit=8)
            lines.append(f"apple: {len(hits)} results")
            lines += [f"- [apple] {h.name} — {h.publisher} <{h.url}>" for h in hits]
        except Exception as e:  # noqa: BLE001 — a dead source must not kill the task
            lines.append(f"apple: error {type(e).__name__}")
    if store in ("play", "both"):
        try:
            hits = ctx.play_search(term, country="xk", lang="sq", limit=8)
            lines.append(f"play: {len(hits)} results")
            lines += [f"- [play] {h.name} — {h.publisher} <{h.url}>" for h in hits]
        except Exception as e:  # noqa: BLE001
            lines.append(f"play: error {type(e).__name__}")
    return _clip("\n".join(lines) or "error: store must be apple, play or both", SOURCE_RESULT_LIMIT)


def askdata_list_impl(ctx: ToolContext, path: str = "") -> str:
    items = ctx.askdata.list(path)
    lines = [f"- {'[folder]' if i.kind == 'l' else '[table]'} {i.id} — {i.text}" for i in items[:60]]
    return _clip("\n".join(lines) or "empty folder", SOURCE_RESULT_LIMIT)


def askdata_table_impl(ctx: ToolContext, path: str) -> str:
    t = ctx.askdata.metadata(path)
    lines = [f"table: {t.title}"]
    for v in t.variables:
        sample = ", ".join(f"{c}={txt}" for c, txt in zip(v.values[:12], v.value_texts[:12], strict=False))
        lines.append(f"- {v.code} ({v.text}; {len(v.values)} values): {sample}")
    return _clip("\n".join(lines), SOURCE_RESULT_LIMIT)


def askdata_fetch_impl(ctx: ToolContext, path: str, selections_json: str) -> str:
    try:
        selections = json.loads(selections_json)
    except json.JSONDecodeError as e:
        return f"error: selections_json must be JSON like {{\"Year\": [\"2024\"]}} ({e.msg})"
    if not isinstance(selections, dict):
        return "error: selections_json must be a JSON object of variable code -> list of values"
    data = ctx.askdata.fetch(path, {k: [str(x) for x in v] for k, v in selections.items()})
    lines = [" | ".join(data.columns)]
    lines += [" | ".join([*map(str, r.get("key", [])), *map(str, r.get("values", []))]) for r in data.rows[:40]]
    return _clip("\n".join(lines), SOURCE_RESULT_LIMIT)


# ---------- tool objects ----------

def _run(ctx: ToolContext, name: str, fn: Callable, **kwargs) -> str:
    try:
        out = fn(ctx, **kwargs)
    except Exception as e:  # noqa: BLE001 — tool errors go back to the model as text
        out = f"error: {type(e).__name__}: {str(e)[:300]}"
    ctx.events.append({"tool": name, "chars": len(out), "error": out.startswith("error:")})
    return out


def build_tools(ctx: ToolContext) -> list:
    @beta_tool
    def kb_search(query: str, sector: str = "") -> str:
        """Search the scout's own knowledge base (saved facts and the sector digest). Call this FIRST,
        before any web search, so you build on what is already known.

        Args:
            query: Keywords in Albanian or English, e.g. "dentist booking Prishtina".
            sector: Optional sector slug to narrow the search, e.g. "health-booking".
        """
        return _run(ctx, "kb_search", kb_search_impl, query=query, sector=sector)

    @beta_tool
    def kb_record_fact(claim: str, entity_type: str, entity_key: str, confidence: float, source_url: str = "",
                       sector: str = "", ttl_days: int = 90, value_json: str = "") -> str:
        """Save one verifiable fact about Kosovo or a nearby market. One claim per call, with its source.

        Args:
            claim: One sentence stating the fact, with numbers and dates where possible.
            entity_type: One of sector, business, proven_model, gap, culture, stat, news, presence_check,
                demand_test, payment_path.
            entity_key: Slug of the thing the fact is about, e.g. "health-booking", "gap:12", "wolt".
            confidence: 0.0–1.0; official statistics 0.9, reputable press 0.7, a single forum post 0.3.
            source_url: Where you saw it.
            sector: Sector slug the fact belongs to, if any.
            ttl_days: How long it stays fresh (prices 30, statistics 180, culture 365).
            value_json: Optional JSON with structured values, e.g. {"count": 3, "cities": ["Prizren"]}.
        """
        return _run(ctx, "kb_record_fact", kb_record_fact_impl, claim=claim, entity_type=entity_type,
                    entity_key=entity_key, confidence=confidence, source_url=source_url, sector=sector,
                    ttl_days=ttl_days, value_json=value_json)

    @beta_tool
    def kb_record_business(name: str, sector: str, kind: str = "local", city: str = "", instagram: str = "",
                           website: str = "", facebook: str = "", note: str = "") -> str:
        """Record a business active in Kosovo (or a nearby market) in a sector — only businesses, never people.

        Args:
            name: Trading name as written on its site or profile.
            sector: Sector slug.
            kind: local, foreign (operating in Kosovo), or nearby (operating only in AL/MK/ME/BA/RS/HR/SI).
            city: Main city, e.g. "Prishtinë".
            instagram: Instagram handle without @.
            website: Website URL.
            facebook: Facebook page URL.
            note: One line: what it offers, prices, how it takes payment.
        """
        return _run(ctx, "kb_record_business", kb_record_business_impl, name=name, sector=sector, kind=kind,
                    city=city, instagram=instagram, website=website, facebook=facebook, note=note)

    @beta_tool
    def kb_record_proven_model(slug: str, name: str, sector: str, description: str, markets_json: str,
                               business_model: str = "", source_urls_json: str = "") -> str:
        """Record a business model that works somewhere else, with the markets where it is proven.

        Args:
            slug: Short id, e.g. "pet-sitting-marketplace".
            name: Human name.
            sector: Sector slug.
            description: Two or three sentences: what it is, who pays, why it works.
            markets_json: JSON list of {"country": "HR", "example": "Pawshake", "url": "https://..."}; use
                ISO-2 codes; nearby markets AL MK ME BA RS HR SI count three times in scoring.
            business_model: How it makes money (commission, subscription, ads, lead fees).
            source_urls_json: JSON list of URLs backing the evidence.
        """
        return _run(ctx, "kb_record_proven_model", kb_record_proven_model_impl, slug=slug, name=name,
                    sector=sector, description=description, markets_json=markets_json,
                    business_model=business_model, source_urls_json=source_urls_json)

    @beta_tool
    def kb_propose_gap(title: str, sector: str, hypothesis: str, presence_level: str = "unknown",
                       proven_model_slug: str = "", why_not_yet: str = "") -> str:
        """Propose a gap: a proven model that seems missing or weak in Kosovo. Duplicates are merged by title.

        Args:
            title: Short name, e.g. "Pet sitting marketplace".
            sector: Sector slug.
            hypothesis: Who in Kosovo would pay, for what, and the evidence so far.
            presence_level: absent, exists-but-poor, prishtina-only, offline-only, decent or unknown — say
                "unknown" unless you ran a presence check.
            proven_model_slug: Slug of the proven model it copies, if recorded.
            why_not_yet: The best reason nobody has done it (payments, trust, size, regulation, logistics).
        """
        return _run(ctx, "kb_propose_gap", kb_propose_gap_impl, title=title, sector=sector, hypothesis=hypothesis,
                    presence_level=presence_level, proven_model_slug=proven_model_slug, why_not_yet=why_not_yet)

    @beta_tool
    def kb_write_digest(key: str, title: str, body_md: str) -> str:
        """Write or replace a long-term digest the scout re-reads every day. Keep it under 5,000 characters,
        factual, with the most decision-relevant points first.

        Args:
            key: "sector:<slug>", "culture:<theme>" or "country".
            title: Digest title.
            body_md: Markdown body.
        """
        return _run(ctx, "kb_write_digest", kb_write_digest_impl, key=key, title=title, body_md=body_md)

    @beta_tool
    def places_search(query: str, city: str = "", language: str = "sq") -> str:
        """Google Places text search for real businesses in a Kosovo city (free quota, use for presence checks).

        Args:
            query: Service in Albanian or English, e.g. "veteriner" or "dog groomer".
            city: One of Prishtinë, Prizren, Pejë, Gjakovë, Mitrovicë, Ferizaj, Gjilan.
            language: "sq" or "en".
        """
        return _run(ctx, "places_search", places_search_impl, query=query, city=city, language=language)

    @beta_tool
    def app_store_search(term: str, store: str = "both") -> str:
        """Search the Kosovo App Store and Google Play storefronts for apps matching a keyword.

        Args:
            term: Keyword, e.g. "taxi", "dentist", "parking".
            store: apple, play or both.
        """
        return _run(ctx, "app_store_search", app_store_search_impl, term=term, store=store)

    @beta_tool
    def askdata_list(path: str = "") -> str:
        """List folders and tables of Kosovo's official statistics (ASKdata). Start with an empty path.

        Args:
            path: Folder path such as "Population" or "Household budget survey".
        """
        return _run(ctx, "askdata_list", askdata_list_impl, path=path)

    @beta_tool
    def askdata_table(path: str) -> str:
        """Show the variables and values of one ASKdata table so you can build a query.

        Args:
            path: Table path ending in .px, e.g. "Population/tbl01.px".
        """
        return _run(ctx, "askdata_table", askdata_table_impl, path=path)

    @beta_tool
    def askdata_fetch(path: str, selections_json: str) -> str:
        """Fetch numbers from one ASKdata table.

        Args:
            path: Table path ending in .px.
            selections_json: JSON object mapping variable code to the list of values, e.g.
                {"Year": ["2024"], "Municipality": ["Prizren"]}. Keep selections small.
        """
        return _run(ctx, "askdata_fetch", askdata_fetch_impl, path=path, selections_json=selections_json)

    return [kb_search, kb_record_fact, kb_record_business, kb_record_proven_model, kb_propose_gap,
            kb_write_digest, places_search, app_store_search, askdata_list, askdata_table, askdata_fetch]
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `TEST_DATABASE_URL=<url> uv run pytest tests/test_worker_tools.py tests/test_web.py -v`
Expected: 9 PASSED

- [ ] **Step 7: Commit**

```bash
uv run ruff check . && uv run ruff format .
git add -A && git commit -m "feat(worker): knowledge-base and Tier A source tools for the tool runner"
```

---

### Task 13: Task profiles, frozen system prompt, brief builder

**Files:**
- Create: `scout/worker/profiles.py`
- Test: `tests/test_profiles.py`

**Interfaces:**
- Consumes: `repo.get_digest`, `repo.list_digests` (Task 4), `JournalEntry` (Task 3).
- Produces: `Profile(name, model, est_cost_eur: Decimal, max_iterations: int, max_searches: int, max_fetches: int, max_tokens: int, effort: str, brief_template: str)` (frozen); `PROFILES: dict[str, Profile]` with keys `map-sector, hunt-models, verify-gap, culture, news-scan, deep-dive`; `WORKER_RULES: str`; `CONTRACT: str`; `build_system(session) -> list[dict]` (two text blocks, `cache_control` on the last, no dates); `journal_markdown(entries: list[JournalEntry], limit_chars: int = 6000) -> str`; `build_brief(profile: Profile, payload: dict, today: date, *, journal_md: str = "", sector_digest: str = "", gaps_md: str = "") -> str`.

- [ ] **Step 1: Write the failing tests**

`tests/test_profiles.py`:
```python
import re
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest

from scout.worker import profiles as P


def test_profiles_match_spec_table():
    assert set(P.PROFILES) == {"map-sector", "hunt-models", "verify-gap", "culture", "news-scan", "deep-dive"}
    ms = P.PROFILES["map-sector"]
    assert (ms.model, ms.max_searches, ms.max_fetches, ms.max_iterations, ms.est_cost_eur) == (
        "claude-sonnet-5-5", 12, 8, 14, Decimal("0.35"))
    vg = P.PROFILES["verify-gap"]
    assert (vg.max_searches, vg.max_fetches, vg.est_cost_eur) == (10, 6, Decimal("0.40"))
    ns = P.PROFILES["news-scan"]
    assert (ns.max_searches, ns.max_fetches, ns.max_iterations, ns.est_cost_eur) == (4, 4, 6, Decimal("0.10"))
    dd = P.PROFILES["deep-dive"]
    assert (dd.model, dd.effort, dd.est_cost_eur) == ("claude-opus-5-5", "high", Decimal("0.80"))
    for p in P.PROFILES.values():
        assert "{contract}" in p.brief_template or p.name == "deep-dive"


def test_build_brief_fills_payload_and_context():
    brief = P.build_brief(P.PROFILES["map-sector"], {"sector": "pets", "sector_name": "Pets"},
                          date(2026, 10, 19), journal_md="- yesterday: mapped cars", sector_digest="old digest")
    assert "2026-10-19" in brief and "`pets`" in brief and "Pets" in brief
    assert "old digest" in brief and "mapped cars" in brief
    assert "leads:" in brief and "150 words" in brief
    assert "{" not in brief.replace("{\"", "")  # no unfilled placeholders (JSON examples allowed)


def test_build_brief_missing_keys_become_none_marker():
    brief = P.build_brief(P.PROFILES["verify-gap"], {"gap_id": 7, "gap_title": "Pet sitting"}, date(2026, 10, 19))
    assert "gap:7" in brief and "Pet sitting" in brief and "(none)" in brief


def test_build_system_is_frozen_and_cached():
    class FakeSession:
        pass
    digests = {"country": "Kosovo has 1.6M people."}
    culture = [SimpleNamespace(key="culture:payments-and-trust", title="Payments and trust",
                               body_md="Cash dominates.")]
    system = P.build_system(FakeSession(), get_digest=lambda s, k: digests.get(k),
                            list_digests=lambda s, prefix: culture)
    assert [b["type"] for b in system] == ["text", "text"]
    assert system[-1]["cache_control"] == {"type": "ephemeral"} and "cache_control" not in system[0]
    assert "Kosovo has 1.6M people." in system[1]["text"] and "Cash dominates." in system[1]["text"]
    joined = system[0]["text"] + system[1]["text"]
    assert not re.search(r"\b20\d\d-\d\d-\d\d\b", joined)
    assert system == P.build_system(FakeSession(), get_digest=lambda s, k: digests.get(k),
                                    list_digests=lambda s, prefix: culture)


def test_journal_markdown_limits_size():
    entries = [SimpleNamespace(day=date(2026, 10, 18), did_md="a" * 5000, learned_md="b" * 5000,
                               tomorrow_md="c")]
    md = P.journal_markdown(entries, limit_chars=1000)
    assert len(md) <= 1000 and md.startswith("### 2026-10-18")


def test_unknown_profile_payload_type_rejected():
    with pytest.raises(TypeError):
        P.build_brief(P.PROFILES["culture"], ["not", "a", "dict"], date(2026, 10, 19))
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_profiles.py -v`
Expected: FAIL with `ImportError: cannot import name 'profiles'`

- [ ] **Step 3: Write `scout/worker/profiles.py`**

```python
"""Task profiles (what a worker does today) and the prompts that express them.

The system prompt is identical for every task of a run (tools → system prefix is cached);
everything that varies — date, sector, gap, journal — lives in the first user message.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from string import Formatter

from scout.db import repo

WORKER_RULES = """You are the research worker of Kosovo Gap Scout, a daily engine whose only goal is to find
business models that are proven in other countries (ideally the neighbours: Albania, North Macedonia,
Montenegro, Bosnia, Serbia, Croatia, Slovenia) but missing or badly served in Kosovo, so a solo founder
based in Prishtina (software engineer, 5–10 hours a week, ≤ €2,000 budget, consumer products, software only,
nothing in regulated finance, health care, gambling, physical inventory or fleets) can test and start one.

How you work:
- Albanian first. Search in Albanian ("a ka ... në Kosovë", "aplikacion për ...", "ku mund të ...",
  "sa kushton ... Prishtinë"), then English, then the neighbours' languages for proven models
  (Croatian/Serbian/Bosnian "aplikacija", Macedonian "апликација", Albanian for Albania).
- Knowledge base first. Call kb_search before searching the web; never re-research what is already known
  unless the facts are stale or contradictory.
- Evidence or silence. Every fact carries a source URL and an honest confidence. Do not infer that something
  is absent from Kosovo because you did not find it in one search — say "not found in N searches" and keep
  the presence level "unknown" unless you ran the full presence check (seven cities, both app stores, four
  web queries).
- Businesses, not people. Record companies, apps, pages and prices. Never record names, phone numbers or
  posts of private individuals; summarise complaints as patterns ("users complain about X") without quoting
  identifiable people.
- Kosovo specifics to keep in mind: euro currency; card penetration growing but cash dominant; PayPal does
  not pay out to Kosovo accounts; Stripe unavailable; large diaspora (Germany, Switzerland, Austria, US) that
  sends money and visits in summer and at New Year; young population (median age ≈ 30); Albanian-speaking
  majority with Serbian-speaking municipalities in the north; Instagram and TikTok are the main consumer
  channels; many services are sold through Instagram DMs and cash on delivery; the state portal e-Kosova
  digitalised many procedures; informal economy is significant; trust is built through personal networks.
- Persist with tools, then summarise. Knowledge that is not saved with kb_* tools is lost: the summary is
  for the journal only. Save facts as you go, not at the end.
- Budget. Every search costs money. Prefer kb_search, Places and app-store tools (free) for presence
  questions; use web_fetch only on pages that will yield numbers or names. If a tool answers "budget
  exhausted", stop immediately and write your summary.
"""

CONTRACT = ("Finish with a summary of at most 150 words: what you found, what changed in the knowledge base, "
            "then one line per lead starting with \"leads:\" (a lead is a proven model worth hunting or a gap "
            "worth verifying). Persist everything with kb_* tools BEFORE the summary.")

MAP_SECTOR_BRIEF = """Date: {today}. Task: MAP SECTOR `{sector}` ({sector_name}) in Kosovo.

Goal: a decision-grade picture of this sector in Kosovo today, saved as facts, businesses and a digest.
Do, in order:
1. kb_search for `{sector}` and read the existing digest below. Build on it; do not redo it.
2. Research Albanian-first: who serves this need in Kosovo (companies, apps, Instagram-only sellers, informal
   providers), typical prices, how they take payment, which cities they cover, what people complain about
   (forums, r/kosovo, press, review summaries), recent launches or closures. Use places_search for one or two
   city counts where it helps. Use askdata_* when population or household numbers matter.
3. Save 5–10 facts with kb_record_fact (always with source_url). Save every player with kb_record_business.
4. Note 0–3 leads: models you noticed in neighbouring countries that nobody offers here. Save them with
   kb_record_proven_model only when you have a URL as evidence; otherwise mention them in the summary.
5. Rewrite the digest with kb_write_digest key "sector:{sector}" (≤ 5,000 characters): demand picture,
   players, prices, payments, cities, complaints, your presence-level estimate with the evidence, open
   questions.

Existing digest:
{sector_digest}

Recent journal:
{journal_md}

{contract}"""

HUNT_MODELS_BRIEF = """Date: {today}. Task: HUNT PROVEN MODELS for sector `{sector}` ({sector_name}).

Goal: find consumer business models in this sector that demonstrably work in the neighbours (Albania, North
Macedonia, Montenegro, Bosnia, Serbia, Croatia, Slovenia) or the EU, and turn the best into gap candidates.
Do, in order:
1. kb_search for `{sector}`; read the digest below to know what Kosovo already has.
2. Search the neighbours in their languages and English: "<service> app Hrvatska", "<service> aplikacija
   Srbija", "<service> Shqipëri", "<service> Македонија", "<service> startup Balkans". Look for traction
   evidence: users, downloads, funding, prices, years active, app-store presence.
3. Save each model with kb_record_proven_model (markets with URLs; nearby markets count three times in
   scoring). Save traction facts with kb_record_fact (entity_type proven_model).
4. For each model that Kosovo lacks or serves badly, call kb_propose_gap with presence_level "unknown"
   (unless the knowledge base holds a presence check), a hypothesis of who in Kosovo pays and why, and the
   best why-not-yet reason.

Sector digest:
{sector_digest}

Known gaps in this sector:
{gaps_md}

Recent journal:
{journal_md}

{contract}"""

VERIFY_GAP_BRIEF = """Date: {today}. Task: VERIFY GAP #{gap_id} "{gap_title}" (sector `{sector}`).

Hypothesis so far: {hypothesis}
Presence level so far: {presence_level}

Run the presence-check protocol completely — this is the anti-hallucination rule of the whole system:
1. places_search for the service in each of Prishtinë, Prizren, Pejë, Gjakovë, Mitrovicë, Ferizaj, Gjilan,
   in Albanian and in English (14 calls). Count real, operating businesses per city.
2. app_store_search for the service keywords (store "both").
3. Web: three Albanian queries ("<service> në Kosovë", "<service> Prishtinë", "aplikacion <service>") and one
   English query. Look for digital products, not just listings.
4. Save every player found with kb_record_business (kind local or foreign).
5. Save exactly one presence-check fact: kb_record_fact with entity_type "presence_check", entity_key
   "gap:{gap_id}", claim "presence check: <verdict> — <one-line counts>", ttl_days 60, confidence 0.8 (0.5 if
   a source was degraded), value_json {{"verdict": "...", "places_by_city": {{...}}, "apps": [...],
   "web_hits": [...], "urls": [...]}}. Verdicts: absent (nothing in any channel), exists-but-poor (≤ 2 players,
   weak reviews or activity, or social-media-only), prishtina-only, offline-only (businesses exist but no
   digital product), decent (≥ 3 active players with digital products), unknown (sources degraded).
6. Save a payment_path fact (how a Kosovo customer could pay for this: card via local PSP, cash on delivery,
   bank transfer, in-app via Google/Apple billing) and the strongest why-not-yet facts.
7. Call kb_propose_gap with the same title "{gap_title}", sector `{sector}`, presence_level set to the
   verdict, and the updated hypothesis and why_not_yet — this updates the existing gap.
If the verdict is ambiguous, include one line "field-check: <a question the founder can answer in three
minutes by phone or by visiting>" in your summary.

Known facts about this gap:
{gaps_md}

Recent journal:
{journal_md}

{contract}"""

CULTURE_BRIEF = """Date: {today}. Task: CULTURE DIGEST `{theme}` ({theme_name}).

Goal: write the long-term memory on this theme that every future task will read, so the scout understands
how Kosovars actually live, pay, trust and buy.
Do, in order:
1. kb_search for `{theme}`; read the existing digest below.
2. Research: official statistics (askdata_*: population, household budget survey, ICT usage, labour market),
   Central Bank of Kosovo (payments, cards, remittances), reports (World Bank, UNDP Kosovo, Riinvest, GAP
   Institute, D4D, STIKK), serious press (Koha, Kallxo, Telegrafi, Prishtina Insight, Kosovo 2.0), and
   Albanian-language sources on everyday behaviour.
3. Save 6–10 facts with kb_record_fact (entity_type culture or stat; ttl_days 365 for culture, 180 for
   statistics; always with source_url).
4. Write the digest with kb_write_digest key "culture:{theme}" (≤ 5,000 characters) ending with a section
   "What this means for a consumer product in Kosovo" of concrete do/don't rules.

Existing digest:
{sector_digest}

Recent journal:
{journal_md}

{contract}"""

NEWS_SCAN_BRIEF = """Date: {today}. Task: NEWS SCAN — the last 48 hours in Kosovo's consumer economy.

Look for: product launches, startups, funding, closures, new regulation (payments, e-commerce, taxes,
licences), big complaints going viral, infrastructure changes (payments, delivery, transport), diaspora
news. Sources: Telegrafi, Koha, Kallxo, Gazeta Express, Insajderi, Prishtina Insight, Kosovo 2.0, STIKK,
Central Bank of Kosovo, Kosovo Chamber of Commerce; use at most four searches and four fetches.
Save each relevant item with kb_record_fact (entity_type news, ttl_days 30, with the sector slug if clear).
Flag anything that changes the picture for the gaps below.

Gaps being tracked:
{gaps_md}

Recent journal:
{journal_md}

{contract}"""

DEEP_DIVE_BRIEF = """Date: {today}. Task: DEEP DIVE on gap #{gap_id} "{gap_title}" (sector `{sector}`).

Hypothesis: {hypothesis}

Write the memo a careful operator would want before spending €150 on a demand test. Research first (kb_search,
then the web); save new facts with kb_record_fact as you go. Then answer with a memo of at most 900 words
with these headings:
1. The gap in one paragraph (what is proven where, what Kosovo has today, evidence with sources).
2. Market size: Kosovo (people, households, spend) and the Albanian-speaking expansion (Albania, North
   Macedonia, diaspora) — show the arithmetic.
3. Unit economics for a solo founder: price point, cost per customer, payment path in Kosovo, gross margin.
4. Go-to-market with no audience: channels, first 100 customers, what to copy from the proven model.
5. Why it does not exist yet, and whether that reason is fatal (payments, trust, informality, incumbents,
   regulation, market size).
6. A two-week demand test: one promise page in Albanian, Meta/TikTok ads of €75–150, 30 messages a day to
   public business pages, success benchmarks (cost per lead < €1.50 and ≥ 50 sign-ups, or ≥ 5 pre-orders, or
   ≥ 20 real conversations), kill rule (< 15 sign-ups after €75 and 7 days).
7. Verdict: proceed / park / kill, with confidence 0–1 and the single fact that would change your mind.
Known facts about this gap:
{gaps_md}

Recent journal:
{journal_md}"""


@dataclass(frozen=True)
class Profile:
    name: str
    model: str
    est_cost_eur: Decimal
    max_iterations: int
    max_searches: int
    max_fetches: int
    max_tokens: int
    effort: str
    brief_template: str


PROFILES: dict[str, Profile] = {
    "map-sector": Profile("map-sector", "claude-sonnet-5-5", Decimal("0.35"), 14, 12, 8, 4096, "medium",
                          MAP_SECTOR_BRIEF),
    "hunt-models": Profile("hunt-models", "claude-sonnet-5-5", Decimal("0.35"), 14, 12, 8, 4096, "medium",
                           HUNT_MODELS_BRIEF),
    "verify-gap": Profile("verify-gap", "claude-sonnet-5-5", Decimal("0.40"), 14, 10, 6, 4096, "medium",
                          VERIFY_GAP_BRIEF),
    "culture": Profile("culture", "claude-sonnet-5-5", Decimal("0.30"), 12, 10, 8, 4096, "medium",
                       CULTURE_BRIEF),
    "news-scan": Profile("news-scan", "claude-sonnet-5-5", Decimal("0.10"), 6, 4, 4, 2048, "medium",
                         NEWS_SCAN_BRIEF),
    "deep-dive": Profile("deep-dive", "claude-opus-5-5", Decimal("0.80"), 10, 8, 6, 8192, "high",
                         DEEP_DIVE_BRIEF),
}

COUNTRY_DIGEST_CHARS = 4000
CULTURE_DIGEST_CHARS = 1500
MEMORY_BLOCK_CHARS = 14000


def build_system(session, *, get_digest=repo.get_digest, list_digests=repo.list_digests) -> list[dict]:
    """Two text blocks: static rules, then the long-term memory. Built once per run, reused for every task."""
    country = get_digest(session, "country") or "No country digest yet — rely on the rules above."
    parts = ["## Country digest\n" + country[:COUNTRY_DIGEST_CHARS]]
    for d in sorted(list_digests(session, "culture:"), key=lambda d: d.key):
        parts.append(f"## {d.title}\n{d.body_md[:CULTURE_DIGEST_CHARS]}")
    memory = "\n\n".join(parts)[:MEMORY_BLOCK_CHARS]
    return [
        {"type": "text", "text": WORKER_RULES},
        {"type": "text", "text": "# Long-term memory\n\n" + memory, "cache_control": {"type": "ephemeral"}},
    ]


def journal_markdown(entries, limit_chars: int = 6000) -> str:
    chunks = []
    for e in entries:
        chunks.append(f"### {e.day.isoformat()}\n**Did:** {e.did_md}\n**Learned:** {e.learned_md}\n"
                      f"**Tomorrow:** {e.tomorrow_md}")
    return "\n\n".join(chunks)[:limit_chars]


class _Safe(dict):
    def __missing__(self, key: str) -> str:
        return "(none)"


def build_brief(profile: Profile, payload: dict, today: date, *, journal_md: str = "",
                sector_digest: str = "", gaps_md: str = "") -> str:
    if not isinstance(payload, dict):
        raise TypeError("payload must be a dict")
    values = _Safe({k: ("(none)" if v in (None, "") else v) for k, v in payload.items()})
    values.update(today=today.isoformat(), journal_md=journal_md or "(none)",
                  sector_digest=sector_digest or "(none)", gaps_md=gaps_md or "(none)", contract=CONTRACT)
    return Formatter().vformat(profile.brief_template, (), values)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_profiles.py -v`
Expected: 6 PASSED

- [ ] **Step 5: Commit**

```bash
uv run ruff check . && uv run ruff format .
git add -A && git commit -m "feat(worker): task profiles, frozen system prompt and brief builder"
```

---

### Task 14: Research worker (tool-runner loop with budget and pause_turn handling)

**Files:**
- Create: `scout/worker/research.py`
- Modify: `tests/fakes.py` (append `FakeRunner`, `fake_runner_factory`)
- Test: `tests/test_research.py`

**Interfaces:**
- Consumes: `LLM.record_message`, `message_text` (Task 7), `build_tools`, `ToolContext` (Task 12), `web_tools` (Task 12), `Profile` (Task 13), guard `can_afford`.
- Produces: `PER_ITERATION_EST_EUR: dict[str, Decimal]`; `TaskOutcome(summary_md: str, stop_reason: str, iterations: int, cost_eur: Decimal, restarts: int, tool_calls: int, truncated: bool, budget_stopped: bool)`; `ResearchWorker(client, llm, guard, system: list[dict], runner_factory=None)` with `MAX_RESTARTS = 3` and `.run(task_id: int | None, profile: Profile, brief: str, ctx: ToolContext) -> TaskOutcome`.

- [ ] **Step 1: Append the fake runner to `tests/fakes.py`**

```python


class FakeRunner:
    """Yields queued messages like the SDK runner; stops after a message without tool_use."""

    def __init__(self, messages, max_iterations=None) -> None:
        self._messages = list(messages)
        self._max = max_iterations
        self._count = 0
        self._last = None

    def __iter__(self):
        while self._messages and (self._max is None or self._count < self._max):
            self._last = self._messages.pop(0)
            self._count += 1
            yield self._last
            if not any(getattr(b, "type", "") == "tool_use" for b in self._last.content):
                return

    def generate_tool_call_response(self):
        if self._last is None:
            return None
        uses = [b for b in self._last.content if getattr(b, "type", "") == "tool_use"]
        if not uses:
            return None
        return {"role": "user", "content": [{"type": "tool_result", "tool_use_id": u.id, "content": "ok"}
                                            for u in uses]}


def fake_runner_factory(script: list[list], calls: list[dict]):
    """Each runner construction pops the next list of messages from `script` and logs its kwargs."""

    def factory(**kwargs):
        calls.append(kwargs)
        return FakeRunner(script.pop(0), kwargs.get("max_iterations"))

    return factory
```

- [ ] **Step 2: Write the failing tests**

`tests/test_research.py`:
```python
from decimal import Decimal

from scout.llm.gateway import LLM
from scout.worker.profiles import PROFILES
from scout.worker.research import PER_ITERATION_EST_EUR, ResearchWorker
from scout.worker.tools import ToolContext
from tests.fakes import (FakeClient, FakeGuard, FakeMessage, FakeUsage, fake_runner_factory, text_block,
                         tool_use_block)

SYSTEM = [{"type": "text", "text": "rules"}, {"type": "text", "text": "memory", "cache_control": {"type": "ephemeral"}}]


def _ctx(guard):
    return ToolContext(session=None, guard=guard, now=None, run_id=1, task_id=5, places=None, askdata=None)


def _worker(guard, script, calls):
    llm = LLM(FakeClient(), guard, Decimal("0.92"))
    return ResearchWorker(FakeClient(), llm, guard, SYSTEM, runner_factory=fake_runner_factory(script, calls))


def test_worker_runs_to_end_turn_and_records_each_message():
    guard, calls = FakeGuard(), []
    script = [[FakeMessage(content=[tool_use_block("kb_search", {"query": "pets"})], stop_reason="tool_use"),
               FakeMessage(content=[text_block("Found 3 players.\nleads: pet sitting")], stop_reason="end_turn")]]
    out = _worker(guard, script, calls).run(5, PROFILES["map-sector"], "brief", _ctx(guard))
    assert out.summary_md.endswith("leads: pet sitting") and out.stop_reason == "end_turn"
    assert out.iterations == 2 and out.restarts == 0 and not out.truncated and not out.budget_stopped
    assert len(guard.records) == 2 and all(r.task_id == 5 for r in guard.records)
    assert out.cost_eur == sum(r.cost_eur for r in guard.records)
    kw = calls[0]
    assert kw["model"] == "claude-sonnet-5-5" and kw["system"] is SYSTEM and kw["max_iterations"] == 14
    assert kw["output_config"] == {"effort": "medium"} and kw["max_tokens"] == 4096
    assert "thinking" not in kw and "tool_choice" not in kw
    names = [t.name for t in kw["tools"] if hasattr(t, "name")]
    assert names[0] == "kb_search" and len(names) == 11
    assert {"type": "web_search_20260209", "name": "web_search", "max_uses": 12} in kw["tools"]
    assert kw["messages"] == [{"role": "user", "content": "brief"}]


def test_worker_restarts_on_pause_turn():
    guard, calls = FakeGuard(), []
    paused = FakeMessage(content=[text_block("searching...")], stop_reason="pause_turn")
    done = FakeMessage(content=[text_block("done. leads: none")], stop_reason="end_turn")
    out = _worker(guard, [[paused], [done]], calls).run(5, PROFILES["news-scan"], "brief", _ctx(guard))
    assert out.restarts == 1 and out.stop_reason == "end_turn" and out.iterations == 2
    history = calls[1]["messages"]
    assert history[0] == {"role": "user", "content": "brief"}
    assert history[1]["role"] == "assistant" and history[1]["content"] is paused.content
    assert calls[1]["max_iterations"] == 5  # 6 minus the iteration already used


def test_worker_gives_up_after_max_restarts():
    guard, calls = FakeGuard(), []
    script = [[FakeMessage(content=[text_block("p")], stop_reason="pause_turn")] for _ in range(5)]
    out = _worker(guard, script, calls).run(5, PROFILES["news-scan"], "brief", _ctx(guard))
    assert out.restarts == ResearchWorker.MAX_RESTARTS and out.stop_reason == "pause_turn"
    assert len(calls) == ResearchWorker.MAX_RESTARTS + 1


def test_worker_stops_when_budget_tight():
    guard, calls = FakeGuard(cap=Decimal("0.05")), []
    big = FakeUsage(input_tokens=10_000, output_tokens=0)  # €0.0184 per message on Sonnet
    msgs = [FakeMessage(content=[tool_use_block("kb_search", {"query": "x"}, id=f"t{i}")],
                        stop_reason="tool_use", usage=big) for i in range(3)]
    msgs.append(FakeMessage(content=[text_block("summary")], stop_reason="end_turn", usage=big))
    out = _worker(guard, [msgs], calls).run(5, PROFILES["map-sector"], "brief", _ctx(guard))
    assert PER_ITERATION_EST_EUR["claude-sonnet-5-5"] == Decimal("0.03")
    assert out.iterations == 2 and out.budget_stopped is True
    assert "budget" in out.summary_md and len(guard.records) == 2


def test_worker_reports_max_tokens():
    guard, calls = FakeGuard(), []
    cut = FakeMessage(content=[text_block("long memo that was cut")], stop_reason="max_tokens")
    out = _worker(guard, [[cut]], calls).run(None, PROFILES["deep-dive"], "brief", _ctx(guard))
    assert out.truncated and out.stop_reason == "max_tokens" and out.summary_md.startswith("long memo")
    assert calls[0]["output_config"] == {"effort": "high"} and calls[0]["model"] == "claude-opus-5-5"
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `uv run pytest tests/test_research.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'scout.worker.research'`

- [ ] **Step 4: Write `scout/worker/research.py`**

```python
"""The research worker: one tool-runner conversation per task, priced per message, stopped by the budget."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal

from scout.llm.gateway import LLM, message_text
from scout.sources.web import web_tools
from scout.worker.profiles import Profile
from scout.worker.tools import ToolContext, build_tools

PER_ITERATION_EST_EUR: dict[str, Decimal] = {
    "claude-sonnet-5-5": Decimal("0.03"),
    "claude-opus-5-5": Decimal("0.08"),
    "claude-haiku-5-5": Decimal("0.005"),
}


@dataclass
class TaskOutcome:
    summary_md: str
    stop_reason: str
    iterations: int
    cost_eur: Decimal
    restarts: int
    tool_calls: int
    truncated: bool
    budget_stopped: bool


class ResearchWorker:
    MAX_RESTARTS = 3

    def __init__(self, client, llm: LLM, guard, system: list[dict],
                 runner_factory: Callable | None = None) -> None:
        self.client = client
        self.llm = llm
        self.guard = guard
        self.system = system
        self.runner_factory = runner_factory or (lambda **kw: client.beta.messages.tool_runner(**kw))

    def run(self, task_id: int | None, profile: Profile, brief: str, ctx: ToolContext) -> TaskOutcome:
        tools = build_tools(ctx) + web_tools(profile.max_searches, profile.max_fetches)
        messages: list[dict] = [{"role": "user", "content": brief}]
        step_est = PER_ITERATION_EST_EUR.get(profile.model, Decimal("0.03"))
        total = Decimal("0")
        iterations = restarts = 0
        last = None
        truncated = budget_stopped = False

        while True:
            remaining_iterations = profile.max_iterations - iterations
            if remaining_iterations <= 0:
                break
            runner = self.runner_factory(
                model=profile.model, max_tokens=profile.max_tokens, system=self.system, tools=tools,
                messages=messages, max_iterations=remaining_iterations,
                output_config={"effort": profile.effort},
            )
            stream = iter(runner)
            while True:
                if not self.guard.can_afford(step_est):
                    budget_stopped = True
                    break
                try:
                    message = next(stream)
                except StopIteration:
                    break
                iterations += 1
                last = message
                total += self.llm.record_message(profile.model, message, task_id=task_id)
                if message.stop_reason == "max_tokens":
                    truncated = True
                # Mirror the history: the runner keeps its own copy and does not expose it.
                messages.append({"role": "assistant", "content": message.content})
                tool_response = runner.generate_tool_call_response()  # cached; tools still run once
                if tool_response is not None:
                    messages.append(tool_response)
            if budget_stopped or last is None or last.stop_reason != "pause_turn":
                break
            if restarts >= self.MAX_RESTARTS:
                break
            restarts += 1  # paused mid-turn: history ends with the paused assistant turn, so resume

        summary = message_text(last) if last is not None else ""
        stop_reason = last.stop_reason if last is not None else "not_started"
        if budget_stopped:
            summary = (summary + "\n\n" if summary else "") + \
                "(stopped early: daily budget exhausted before the summary was written)"
        elif not summary:
            summary = f"(no summary text; stop_reason={stop_reason})"
        return TaskOutcome(summary_md=summary.strip(), stop_reason=stop_reason, iterations=iterations,
                           cost_eur=total, restarts=restarts, tool_calls=len(ctx.events),
                           truncated=truncated, budget_stopped=budget_stopped)
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `uv run pytest tests/test_research.py -v`
Expected: 5 PASSED

- [ ] **Step 6: Commit**

```bash
uv run ruff check . && uv run ruff format .
git add -A && git commit -m "feat(worker): research worker loop with pause_turn restarts and budget stop"
```

---

### Task 15: Extractor and extraction schemas

**Files:**
- Create: `scout/extract/__init__.py`, `scout/extract/schemas.py`, `scout/extract/extractor.py`
- Test: `tests/test_extractor.py`

**Interfaces:**
- Consumes: `LLM.parse` (Task 7).
- Produces: `AppClassification`, `AppClassificationBatch` (Pydantic, `extra="forbid"`, `Literal` enums only); `EXTRACTOR_SYSTEM: str`; `MAX_TEXT_CHARS = 300_000`; `Extractor(llm)` with `.extract(output_format: type[BaseModel], instructions: str, text: str, *, model: str = "claude-haiku-5-5", effort: str = "low", est_eur: Decimal = Decimal("0.01"), max_tokens: int = 4096, task_id: int | None = None) -> BaseModel`.

- [ ] **Step 1: Write the failing tests**

`tests/test_extractor.py`:
```python
from decimal import Decimal

from scout.extract.extractor import EXTRACTOR_SYSTEM, MAX_TEXT_CHARS, Extractor
from scout.extract.schemas import AppClassification, AppClassificationBatch
from scout.llm.gateway import LLM
from tests.fakes import FakeClient, FakeGuard, FakeMessage, text_block


def test_schema_is_structured_output_safe():
    schema = AppClassificationBatch.model_json_schema()
    assert schema["additionalProperties"] is False
    item = schema["$defs"]["AppClassification"]
    assert item["additionalProperties"] is False
    assert "enum" in item["properties"]["kosovo_relevance"]
    assert all(k not in str(schema) for k in ("minimum", "maximum", "minLength", "pattern"))


def test_extract_calls_haiku_low_effort_and_clips_text():
    batch = AppClassificationBatch(items=[AppClassification(
        app_key="com.x", category="mobility", consumer_need="bus times", kosovo_relevance="high",
        sector_slug="mobility-transit", is_global_brand=False, note="")])
    client = FakeClient([FakeMessage(content=[text_block("{}")], parsed_output=batch)])
    ex = Extractor(LLM(client, FakeGuard(), Decimal("0.92")))
    out = ex.extract(AppClassificationBatch, "Classify these apps.", "x" * (MAX_TEXT_CHARS + 10))
    assert out is batch
    kw = client.messages.calls[0]
    assert kw["model"] == "claude-haiku-5-5" and kw["output_config"] == {"effort": "low"}
    assert kw["system"] == EXTRACTOR_SYSTEM and kw["output_format"] is AppClassificationBatch
    assert len(kw["messages"][0]["content"]) < MAX_TEXT_CHARS + 200
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_extractor.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'scout.extract'`

- [ ] **Step 3: Write the schemas and the extractor**

`scout/extract/__init__.py`: empty file.

`scout/extract/schemas.py`:
```python
"""Pydantic schemas for structured extraction. Rules: extra='forbid', Literal enums, no numeric constraints."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

AppCategory = Literal[
    "mobility", "food-delivery", "marketplace", "fintech-payments", "health", "education", "home-services",
    "media-entertainment", "social", "utilities-government", "shopping", "travel", "jobs", "other",
]


class AppClassification(BaseModel):
    model_config = ConfigDict(extra="forbid")
    app_key: str
    category: AppCategory
    consumer_need: str
    kosovo_relevance: Literal["high", "medium", "low"]
    sector_slug: str
    is_global_brand: bool
    note: str


class AppClassificationBatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    items: list[AppClassification]
```

`scout/extract/extractor.py`:
```python
"""Haiku-powered structured extraction (synchronous in M1; Message Batches in M3)."""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel

from scout.llm.gateway import LLM

EXTRACTOR_SYSTEM = (
    "You extract structured data from text for a market-research system about Kosovo. Output only what the "
    "text supports. When unsure, use 'other', 'unknown' or 'low' rather than guessing. Never invent names, "
    "numbers or URLs. Keep free-text fields to one sentence."
)
MAX_TEXT_CHARS = 300_000  # ≈ 75k tokens, under the 100k-token guidance for Haiku 5.5


class Extractor:
    def __init__(self, llm: LLM) -> None:
        self.llm = llm

    def extract(self, output_format: type[BaseModel], instructions: str, text: str, *,
                model: str = "claude-haiku-5-5", effort: str = "low", est_eur: Decimal = Decimal("0.01"),
                max_tokens: int = 4096, task_id: int | None = None) -> BaseModel:
        user = f"{instructions.strip()}\n\n<text>\n{text[:MAX_TEXT_CHARS]}\n</text>"
        result = self.llm.parse(model=model, output_format=output_format, system=EXTRACTOR_SYSTEM, user=user,
                                max_tokens=max_tokens, effort=effort, est_eur=est_eur, task_id=task_id)
        return result.parsed
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_extractor.py -v`
Expected: 2 PASSED

- [ ] **Step 5: Commit**

```bash
uv run ruff check . && uv run ruff format .
git add -A && git commit -m "feat(extract): Haiku structured extractor and app classification schema"
```

---

### Task 16: Chart diff (Apple + Play, Kosovo vs seven neighbours)

**Files:**
- Create: `scout/worker/chart_diff.py`
- Test: `tests/test_chart_diff.py`

**Interfaces:**
- Consumes: `repo.save_chart_snapshot`, `repo.chart_snapshot`, `repo.latest_chart_date`, `repo.app_ever_in_chart`, `repo.upsert_fact`, `ChartEntryIn`, `FactIn` (Tasks 4–5); `apple.fetch_top_free`, `play.fetch_top_free`, `play.app_details` (Tasks 9–10); `Extractor`, `AppClassificationBatch` (Task 15).
- Produces: `CHART_COUNTRIES = ("xk", "al", "mk", "me", "ba", "rs", "hr", "si")`, `NEIGHBOURS`, `Lead(store, app_key, name, publisher, countries: list[str], best_rank: int)`, `ChartDiffReport(captured_on: date, snapshots_saved: int, leads: list[Lead], new_in_kosovo: list[str], errors: list[str])`, `run_chart_diff(session, today: date, *, apple_fetch=apple.fetch_top_free, play_fetch=play.fetch_top_free, min_neighbours: int = 2) -> ChartDiffReport`, `classify_and_record(session, extractor, report, *, now: datetime, run_id: int | None, max_leads: int = 10, play_details=play.app_details) -> int` (facts written).

- [ ] **Step 1: Write the failing tests**

`tests/test_chart_diff.py`:
```python
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from scout.db import repo
from scout.extract.extractor import Extractor
from scout.extract.schemas import AppClassification, AppClassificationBatch
from scout.llm.gateway import LLM
from scout.sources.types import ChartEntry
from scout.worker import chart_diff as CD
from tests.fakes import FakeClient, FakeGuard, FakeMessage, text_block

pytestmark = pytest.mark.db
TODAY = date(2026, 10, 19)
NOW = datetime(2026, 10, 19, 6, 0, tzinfo=UTC)


def _e(rank, key, name="n", publisher="p"):
    return ChartEntry(rank=rank, app_key=key, name=name, publisher=publisher, genres=(), url="u")


def _fetch(table):
    def fetch(country, limit=25, http=None):
        if country not in table:
            raise RuntimeError("down")
        return table[country]
    return fetch


APPLE = {"xk": [_e(1, "1", "Wolt")], "al": [_e(1, "1", "Wolt"), _e(2, "2", "Pawshake")],
         "mk": [_e(1, "2", "Pawshake"), _e(3, "3", "SkopjeBus")], "me": [_e(1, "3", "SkopjeBus")],
         "ba": [], "rs": [], "hr": [], "si": []}
PLAY = {"xk": [_e(1, "com.a", "A")], "al": [_e(1, "com.b", "B"), _e(2, "1", "Wolt")],
        "mk": [_e(1, "com.b", "B"), _e(2, "1", "Wolt")], "me": [], "ba": [], "rs": [], "hr": []}  # si missing


def test_chart_diff_never_mixes_stores(db_session):
    report = CD.run_chart_diff(db_session, TODAY, apple_fetch=_fetch(APPLE), play_fetch=_fetch(PLAY))
    leads = {(lead.store, lead.app_key) for lead in report.leads}
    # apple "1" is in Kosovo, so apple "2" and "3" are leads; play "1" is NOT in Kosovo's Play chart → lead
    assert leads == {("apple", "2"), ("apple", "3"), ("play", "com.b"), ("play", "1")}
    pawshake = next(lead for lead in report.leads if lead.app_key == "2" and lead.store == "apple")
    assert sorted(pawshake.countries) == ["al", "mk"] and pawshake.best_rank == 1
    assert report.errors == ["play/si: RuntimeError: down"]
    assert report.snapshots_saved == 1 + 2 + 2 + 1 + 1 + 2 + 2 + 2
    assert report.new_in_kosovo == []  # no earlier snapshot


def test_new_in_kosovo_and_ever_charted_suppression(db_session):
    CD.run_chart_diff(db_session, date(2026, 10, 12), apple_fetch=_fetch(APPLE), play_fetch=_fetch(PLAY))
    apple2 = dict(APPLE)
    apple2["xk"] = [_e(1, "1", "Wolt"), _e(2, "2", "Pawshake")]  # Pawshake arrives in Kosovo
    report = CD.run_chart_diff(db_session, TODAY, apple_fetch=_fetch(apple2), play_fetch=_fetch(PLAY))
    assert report.new_in_kosovo == ["Pawshake"]
    assert ("apple", "2") not in {(lead.store, lead.app_key) for lead in report.leads}


def test_classify_and_record_writes_sector_facts_and_skips_global_brands(db_session):
    repo.get_or_create_sector(db_session, "mobility-transit", "Mobility")
    report = CD.run_chart_diff(db_session, TODAY, apple_fetch=_fetch(APPLE), play_fetch=_fetch(PLAY))
    batch = AppClassificationBatch(items=[
        AppClassification(app_key="3", category="mobility", consumer_need="live bus times",
                          kosovo_relevance="high", sector_slug="mobility-transit", is_global_brand=False, note=""),
        AppClassification(app_key="2", category="marketplace", consumer_need="pet sitting",
                          kosovo_relevance="medium", sector_slug="pets", is_global_brand=False, note=""),
        AppClassification(app_key="com.b", category="social", consumer_need="chat", kosovo_relevance="low",
                          sector_slug="none", is_global_brand=True, note="")])
    client = FakeClient([FakeMessage(content=[text_block("{}")], parsed_output=batch)])
    extractor = Extractor(LLM(client, FakeGuard(), Decimal("0.92")))
    n = CD.classify_and_record(db_session, extractor, report, now=NOW, run_id=1,
                               play_details=lambda app_id, country="xk": (_ for _ in ()).throw(RuntimeError()))
    assert n == 2
    facts = repo.search_facts(db_session, "SkopjeBus", now=NOW)
    assert facts and facts[0].sector_id == repo.get_sector(db_session, "mobility-transit").id
    assert facts[0].value["countries"] == ["mk", "me"] and facts[0].entity_type == "stat"
    assert "SkopjeBus" in client.messages.calls[0]["messages"][0]["content"]


def test_no_leads_means_no_model_call(db_session):
    same = {c: [_e(1, "1", "Wolt")] for c in CD.CHART_COUNTRIES}
    report = CD.run_chart_diff(db_session, TODAY, apple_fetch=_fetch(same), play_fetch=_fetch(same))
    client = FakeClient([])
    assert CD.classify_and_record(db_session, Extractor(LLM(client, FakeGuard(), Decimal("0.92"))), report,
                                  now=NOW, run_id=1) == 0
    assert client.messages.calls == []
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `TEST_DATABASE_URL=<url> uv run pytest tests/test_chart_diff.py -v`
Expected: FAIL with `ImportError: cannot import name 'chart_diff'`

- [ ] **Step 3: Write `scout/worker/chart_diff.py`**

```python
"""Weekly app-chart diff: apps charting in ≥ 2 neighbours but never in Kosovo are cheap, strong leads."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime

from scout.db import repo
from scout.db.repo import ChartEntryIn, FactIn
from scout.extract.extractor import Extractor
from scout.extract.schemas import AppClassificationBatch
from scout.sources import apple, play

CHART_COUNTRIES = ("xk", "al", "mk", "me", "ba", "rs", "hr", "si")
NEIGHBOURS = CHART_COUNTRIES[1:]
CHART = "top-free"


@dataclass
class Lead:
    store: str
    app_key: str
    name: str
    publisher: str
    countries: list[str] = field(default_factory=list)
    best_rank: int = 999


@dataclass
class ChartDiffReport:
    captured_on: date
    snapshots_saved: int = 0
    leads: list[Lead] = field(default_factory=list)
    new_in_kosovo: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def run_chart_diff(session, today: date, *, apple_fetch=apple.fetch_top_free, play_fetch=play.fetch_top_free,
                   min_neighbours: int = 2) -> ChartDiffReport:
    report = ChartDiffReport(captured_on=today)
    for store, fetch in (("apple", apple_fetch), ("play", play_fetch)):
        charts: dict[str, list] = {}
        for country in CHART_COUNTRIES:
            try:
                charts[country] = list(fetch(country))
            except Exception as e:  # noqa: BLE001 — one dead storefront must not stop the others
                report.errors.append(f"{store}/{country}: {type(e).__name__}: {e}")
        for country, entries in charts.items():
            report.snapshots_saved += repo.save_chart_snapshot(
                session, store=store, country=country, chart=CHART,
                entries=[ChartEntryIn(e.rank, e.app_key, e.name) for e in entries], captured_on=today)
        if "xk" not in charts:
            continue  # cannot diff without the Kosovo chart
        xk_keys = {e.app_key for e in charts["xk"]}
        candidates: dict[str, Lead] = {}
        for country in NEIGHBOURS:
            for e in charts.get(country, []):
                if e.app_key in xk_keys:
                    continue
                lead = candidates.setdefault(e.app_key, Lead(store, e.app_key, e.name, e.publisher))
                lead.countries.append(country)
                lead.best_rank = min(lead.best_rank, e.rank)
        for lead in candidates.values():
            if len(lead.countries) >= min_neighbours and not repo.app_ever_in_chart(
                    session, store=store, country="xk", app_key=lead.app_key):
                report.leads.append(lead)
        previous = repo.latest_chart_date(session, store=store, country="xk", chart=CHART, before=today)
        if previous is not None:
            prev_keys = {r.app_key for r in repo.chart_snapshot(session, store=store, country="xk", chart=CHART,
                                                                 captured_on=previous)}
            report.new_in_kosovo += [e.name for e in charts["xk"] if e.app_key not in prev_keys]
    report.leads.sort(key=lambda lead: (-len(lead.countries), lead.best_rank))
    return report


CLASSIFY_INSTRUCTIONS = (
    "Each line is an app that ranks in the top-free chart of neighbouring countries but not in Kosovo. "
    "For each app give: category, the consumer need it serves (one sentence), kosovo_relevance (high if a "
    "Kosovo consumer plausibly has the same need and no local equivalent is known, low for global brands, "
    "games, carrier or bank apps tied to one country), the closest sector_slug from this list or 'none': "
    "home-services, health-booking, tutoring-education, mobility-transit, secondhand-marketplaces, "
    "rentals-housing, diaspora-services, weddings-events, food-grocery-delivery, beauty-wellness, "
    "fitness-sports, pets, car-services, parenting-kids, bureaucracy-helpers, local-travel, "
    "utilities-household-finance, jobs-gigs, agri-to-consumer, entertainment-media, legal-consumer, "
    "instagram-seller-tools, elderly-care, language-ai-consumer; and is_global_brand."
)


def classify_and_record(session, extractor: Extractor, report: ChartDiffReport, *, now: datetime,
                        run_id: int | None, max_leads: int = 10, play_details=play.app_details) -> int:
    leads = report.leads[:max_leads]
    if not leads:
        return 0
    for lead in leads:
        if lead.store == "play" and lead.name == lead.app_key:
            try:
                hit = play_details(lead.app_key, country="xk")
                lead.name, lead.publisher = hit.name or lead.name, hit.publisher or lead.publisher
            except Exception:  # noqa: BLE001 — a missing title is not worth failing the run
                pass
    text = "\n".join(f"{lead.store} | {lead.app_key} | {lead.name} | {lead.publisher} | "
                     f"countries={','.join(lead.countries)} | best_rank={lead.best_rank}" for lead in leads)
    batch = extractor.extract(AppClassificationBatch, CLASSIFY_INSTRUCTIONS, text)
    by_key = {lead.app_key: lead for lead in leads}
    written = 0
    for item in batch.items:
        lead = by_key.get(item.app_key)
        if lead is None or item.is_global_brand or item.kosovo_relevance == "low":
            continue
        sector_slug = item.sector_slug if repo.get_sector(session, item.sector_slug) else None
        repo.upsert_fact(session, FactIn(
            claim=(f"App '{lead.name}' ({lead.store}) charts top-free in {', '.join(lead.countries)} but not in "
                   f"Kosovo — {item.consumer_need}"),
            entity_type="stat", entity_key=f"app:{lead.store}:{lead.app_key}", confidence=0.6,
            source_url=None, sector_slug=sector_slug, ttl_days=30,
            value={"store": lead.store, "app_key": lead.app_key, "countries": lead.countries,
                   "best_rank": lead.best_rank, "category": item.category,
                   "relevance": item.kosovo_relevance, "sector_slug": item.sector_slug}),
            run_id=run_id, observed_at=now)
        written += 1
    return written
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `TEST_DATABASE_URL=<url> uv run pytest tests/test_chart_diff.py -v`
Expected: 4 PASSED

- [ ] **Step 5: Commit**

```bash
uv run ruff check . && uv run ruff format .
git add -A && git commit -m "feat(worker): weekly app-chart diff with Haiku lead classification"
```

---

### Task 17: Scoring rubric (the model proposes, Python decides)

**Files:**
- Create: `scout/strategy/__init__.py`, `scout/strategy/rubric.py`
- Test: `tests/test_rubric.py`

**Interfaces:**
- Produces: `PRESENCE_CAP: dict[str, int]`, `NO_CHECK_ABSENCE_CAP = 12`, `NO_CHECK_CONFIDENCE_CAP = 0.5`, `HARD_FILTERS: tuple[str, ...]`, `ScoreResult(total: int, components: dict[str, int], confidence: float, killed: bool, reasons: list[str])` (frozen), `score_gap(*, proof: int, absence: int, demand: int, founder_fit: int, risk_penalty: int, presence_level: str, has_presence_check: bool, hard_filter_failed: str | None, confidence: float) -> ScoreResult`, `cap_confidence(confidence: float, has_presence_check: bool) -> float`, `needs_field_check(total: int, confidence: float) -> bool`, `RUBRIC_TEXT: str` (sent to the Strategist).

- [ ] **Step 1: Write the failing tests**

`tests/test_rubric.py`:
```python
import pytest

from scout.strategy import rubric as R


def _score(**over):
    base = dict(proof=20, absence=25, demand=15, founder_fit=12, risk_penalty=3, presence_level="absent",
                has_presence_check=True, hard_filter_failed=None, confidence=0.8)
    base.update(over)
    return R.score_gap(**base)


def test_full_score_with_presence_check():
    r = _score()
    assert r.total == 20 + 25 + 15 + 12 + (15 - 3) == 84
    assert r.components == {"proof": 20, "absence": 25, "demand": 15, "founder_fit": 12, "risk": 12}
    assert r.confidence == 0.8 and not r.killed


def test_absence_capped_without_presence_check():
    r = _score(has_presence_check=False)
    assert r.components["absence"] == R.NO_CHECK_ABSENCE_CAP == 12
    assert r.confidence == R.NO_CHECK_CONFIDENCE_CAP == 0.5
    assert any("presence check" in reason for reason in r.reasons)


@pytest.mark.parametrize("level,cap", [("absent", 25), ("exists-but-poor", 18), ("prishtina-only", 12),
                                       ("offline-only", 10), ("decent", 0), ("unknown", 12), ("garbage", 12)])
def test_presence_level_caps_absence(level, cap):
    assert _score(presence_level=level).components["absence"] == cap


def test_hard_filter_kills():
    r = _score(hard_filter_failed="cardo-overlap")
    assert r.total == 0 and r.killed and r.reasons == ["hard filter: cardo-overlap"]
    with pytest.raises(ValueError):
        _score(hard_filter_failed="not-a-filter")


def test_components_are_clamped_and_risk_inverted():
    r = _score(proof=99, absence=-5, demand=50, founder_fit=-1, risk_penalty=40)
    assert r.components == {"proof": 25, "absence": 0, "demand": 20, "founder_fit": 0, "risk": 0}
    assert r.total == 45
    assert _score(confidence=1.7).confidence == 1.0


def test_needs_field_check_rule():
    assert R.needs_field_check(60, 0.59) and not R.needs_field_check(59, 0.1) and not R.needs_field_check(90, 0.6)
    assert R.cap_confidence(0.9, False) == 0.5 and R.cap_confidence(0.9, True) == 0.9
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_rubric.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'scout.strategy'`

- [ ] **Step 3: Write `scout/strategy/rubric.py`**

`scout/strategy/__init__.py`: empty file.

```python
"""Gap rubric (spec A3): 0–100, with caps that make hallucinated absence impossible to score high."""

from __future__ import annotations

from dataclasses import dataclass

PRESENCE_CAP: dict[str, int] = {
    "absent": 25, "exists-but-poor": 18, "prishtina-only": 12, "offline-only": 10, "decent": 0, "unknown": 12,
}
NO_CHECK_ABSENCE_CAP = 12
NO_CHECK_CONFIDENCE_CAP = 0.5
HARD_FILTERS = ("regulated-finance-health-gambling", "physical-inventory-or-fleet", "cardo-overlap",
                "test-cost-over-2000", "needs-full-time-before-revenue")

RUBRIC_TEXT = """Scoring rubric (0–100). You propose component scores; the system recomputes the total.
- proof (0–25): evidence the model works elsewhere. Count nearby markets (AL MK ME BA RS HR SI) three times,
  EU/US once; 25 means several nearby markets with traction evidence.
- absence (0–25): how missing it is in Kosovo. Cap by presence level: absent 25, exists-but-poor 18,
  prishtina-only 12, offline-only 10, decent 0, unknown 12. Without a presence check younger than 60 days
  the system caps absence at 12 and confidence at 0.5 regardless of what you propose.
- demand (0–20): signals Kosovars want it (complaints, searches, Instagram workarounds, diaspora pull,
  statistics on spend).
- founder_fit (0–15): software-only, buildable by one engineer in evenings, testable for ≤ €150 of ads,
  monetisable without a sales team, growable to Albanian speakers elsewhere.
- risk_penalty (0–15): the why-not-yet killer — payments, trust, informality, incumbents, regulation,
  logistics, market too small. The system awards 15 − penalty.
- hard filters (score 0, status killed): regulated finance/health/gambling; physical inventory or fleets;
  overlap with the founder's employer's asset-based-finance business; needs > €2,000 to test; needs the
  founder full-time before revenue. Name the filter in hard_filter_failed or use "none".
- confidence (0–1): how sure you are of the whole assessment, separate from the score."""


@dataclass(frozen=True)
class ScoreResult:
    total: int
    components: dict[str, int]
    confidence: float
    killed: bool
    reasons: list[str]


def _clamp(value: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, int(value)))


def cap_confidence(confidence: float, has_presence_check: bool) -> float:
    c = max(0.0, min(1.0, float(confidence)))
    return min(c, NO_CHECK_CONFIDENCE_CAP) if not has_presence_check else c


def needs_field_check(total: int, confidence: float) -> bool:
    return total >= 60 and confidence < 0.6


def score_gap(*, proof: int, absence: int, demand: int, founder_fit: int, risk_penalty: int,
              presence_level: str, has_presence_check: bool, hard_filter_failed: str | None,
              confidence: float) -> ScoreResult:
    if hard_filter_failed not in (None, "none", ""):
        if hard_filter_failed not in HARD_FILTERS:
            raise ValueError(f"unknown hard filter {hard_filter_failed!r}; expected one of {HARD_FILTERS}")
        return ScoreResult(total=0, components={"proof": 0, "absence": 0, "demand": 0, "founder_fit": 0,
                                                 "risk": 0},
                           confidence=cap_confidence(confidence, has_presence_check), killed=True,
                           reasons=[f"hard filter: {hard_filter_failed}"])
    reasons: list[str] = []
    absence_cap = PRESENCE_CAP.get(presence_level, PRESENCE_CAP["unknown"])
    if not has_presence_check:
        absence_cap = min(absence_cap, NO_CHECK_ABSENCE_CAP)
        reasons.append("no presence check ≤ 60 days: absence capped at 12, confidence at 0.5")
    components = {
        "proof": _clamp(proof, 0, 25),
        "absence": min(_clamp(absence, 0, 25), absence_cap),
        "demand": _clamp(demand, 0, 20),
        "founder_fit": _clamp(founder_fit, 0, 15),
        "risk": 15 - _clamp(risk_penalty, 0, 15),
    }
    return ScoreResult(total=sum(components.values()), components=components,
                       confidence=cap_confidence(confidence, has_presence_check), killed=False, reasons=reasons)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_rubric.py -v`
Expected: 12 PASSED

- [ ] **Step 5: Commit**

```bash
uv run ruff check . && uv run ruff format .
git add -A && git commit -m "feat(strategy): scoring rubric with presence-check caps and hard filters"
```

---

### Task 18: Strategist, Critic and apply

**Files:**
- Create: `scout/strategy/schemas.py`, `scout/strategy/strategist.py`
- Test: `tests/test_strategist.py`

**Interfaces:**
- Consumes: `LLM.parse` (Task 7), `repo.*` (Tasks 4–5), `score_gap`, `needs_field_check`, `RUBRIC_TEXT` (Task 17).
- Produces (`schemas.py`): `PresenceLevel`, `HardFilter`, `GapStatus`, `CriticDecision` Literals; Pydantic models `ComponentScores(proof, absence, demand, founder_fit, risk_penalty: int)`, `GapAssessment(gap_id: int, scores, presence_level, confidence: float, hard_filter_failed: HardFilter, reasoning: str, field_check_question: str, recommended_status: GapStatus)`, `NewGapIdea(title, sector_slug, hypothesis, why_not_yet, proven_model_slug: str)`, `StrategistOutput(assessments: list[GapAssessment], new_gaps: list[NewGapIdea], headline: str)`, `CriticVerdict(gap_id: int, strongest_objection: str, kosovo_killer: str, risk_penalty: int, confidence: float, decision: CriticDecision, field_check_question: str)`, `CriticOutput(verdicts: list[CriticVerdict])`, `DroppedTask(task_id: int, reason: str)`, `DirectorReview(keep_task_ids_in_order: list[int], dropped: list[DroppedTask], note: str)`.
- Produces (`strategist.py`): `STRATEGIST_SYSTEM`, `CRITIC_SYSTEM`, `MAX_FACTS_CHARS = 90_000`, `StrategyInputs(country_md, sector_digests: dict[str, str], facts: list[dict], gaps: list[dict])`, `GapChange(gap_id, title, old_status, new_status, old_score, new_score, confidence, why)`, `ApplyResult(changes: list[GapChange], field_checks_added: int, new_gaps: int)`, `Strategist(llm, session)` with `.collect_inputs(*, since: datetime, now: datetime, sector_slugs: list[str] | None = None) -> StrategyInputs`, `.assess(inputs, today) -> StrategistOutput`, `.critique(output, inputs, today, top_n: int = 3) -> CriticOutput`, `.apply(output, critic, *, now, run_id, max_open_field_checks: int = 5) -> ApplyResult`.

- [ ] **Step 1: Write the failing tests**

`tests/test_strategist.py`:
```python
import json
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest

from scout.db import repo
from scout.db.repo import FactIn
from scout.llm.gateway import LLM
from scout.strategy import schemas as S
from scout.strategy.strategist import MAX_FACTS_CHARS, Strategist
from tests.fakes import FakeClient, FakeGuard, FakeMessage, text_block

pytestmark = pytest.mark.db
NOW = datetime(2026, 10, 19, 6, 30, tzinfo=UTC)
TODAY = date(2026, 10, 19)


def _assessment(gap_id, **over):
    base = dict(gap_id=gap_id, scores=S.ComponentScores(proof=20, absence=25, demand=15, founder_fit=12,
                                                       risk_penalty=3),
                presence_level="absent", confidence=0.9, hard_filter_failed="none", reasoning="strong",
                field_check_question="", recommended_status="verified")
    base.update(over)
    return S.GapAssessment(**base)


@pytest.fixture
def seeded(db_session):
    repo.get_or_create_sector(db_session, "pets", "Pets")
    gap, _ = repo.propose_gap(db_session, title="Pet sitting marketplace", sector_slug="pets", hypothesis_md="h")
    repo.upsert_fact(db_session, FactIn(claim="Croatia has Pawshake with 10k sitters", entity_type="proven_model",
                                        entity_key="pet-sitting-marketplace", confidence=0.8, sector_slug="pets",
                                        source_url="https://x"), run_id=1, observed_at=NOW - timedelta(minutes=5))
    return gap


def _strategist(db_session, responses):
    return Strategist(LLM(FakeClient(responses), FakeGuard(), Decimal("0.92")), db_session)


def test_schemas_are_structured_output_safe():
    for model in (S.StrategistOutput, S.CriticOutput, S.DirectorReview):
        schema = json.dumps(model.model_json_schema())
        assert '"additionalProperties": false' in schema
        assert all(k not in schema for k in ("minimum", "maximum", "minLength", "pattern"))


def test_collect_inputs_sorted_and_bounded(db_session, seeded):
    st = _strategist(db_session, [])
    inputs = st.collect_inputs(since=NOW - timedelta(hours=1), now=NOW)
    assert inputs.facts[0]["claim"].startswith("Croatia") and inputs.gaps[0]["id"] == seeded.id
    assert inputs.gaps[0]["has_presence_check"] is False
    assert len(json.dumps(inputs.facts)) <= MAX_FACTS_CHARS


def test_assess_and_critique_call_opus_with_cached_system(db_session, seeded):
    out = S.StrategistOutput(assessments=[_assessment(seeded.id)], new_gaps=[], headline="h")
    crit = S.CriticOutput(verdicts=[S.CriticVerdict(gap_id=seeded.id, strongest_objection="o", kosovo_killer="k",
                                                    risk_penalty=8, confidence=0.6, decision="needs_field_check",
                                                    field_check_question="Call two vets in Prizren?")])
    client = FakeClient([FakeMessage(content=[text_block("{}")], parsed_output=out),
                         FakeMessage(content=[text_block("{}")], parsed_output=crit)])
    st = Strategist(LLM(client, FakeGuard(), Decimal("0.92")), db_session)
    inputs = st.collect_inputs(since=NOW - timedelta(hours=1), now=NOW)
    assert st.assess(inputs, TODAY) is out
    assert st.critique(out, inputs, TODAY) is crit
    a, c = client.messages.calls
    assert a["model"] == "claude-opus-5-5" and a["output_config"] == {"effort": "medium"}
    assert c["output_config"] == {"effort": "high"} and c["output_format"] is S.CriticOutput
    assert a["system"][-1]["cache_control"] == {"type": "ephemeral"}
    assert "2026-10-19" in a["messages"][0]["content"] and "2026" not in "".join(b["text"] for b in a["system"])
    assert a["messages"][0]["content"].index('"facts"') > 0


def test_apply_caps_absence_without_presence_check_and_merges_critic(db_session, seeded):
    st = _strategist(db_session, [])
    out = S.StrategistOutput(assessments=[_assessment(seeded.id)], new_gaps=[], headline="h")
    crit = S.CriticOutput(verdicts=[S.CriticVerdict(gap_id=seeded.id, strongest_objection="o", kosovo_killer="k",
                                                    risk_penalty=8, confidence=0.6, decision="needs_field_check",
                                                    field_check_question="Call two vets in Prizren?")])
    result = st.apply(out, crit, now=NOW, run_id=7)
    gap = repo.get_gap(db_session, seeded.id)
    assert gap.score_components["absence"] == 12 and gap.score_components["risk"] == 7
    assert gap.score_total == 20 + 12 + 15 + 12 + 7 and gap.confidence == 0.5
    assert gap.status == "verifying" and gap.last_assessed_run_id == 7
    assert result.field_checks_added == 1 and repo.open_field_checks(db_session)[0].gap_id == seeded.id
    assert result.changes[0].old_status == "candidate" and result.changes[0].new_score == gap.score_total


def test_apply_verifies_only_with_fresh_check_and_confidence(db_session, seeded):
    repo.upsert_fact(db_session, FactIn(claim="presence check: absent", entity_type="presence_check",
                                        entity_key=f"gap:{seeded.id}", confidence=0.8, sector_slug="pets",
                                        value={"verdict": "absent"}, ttl_days=60), run_id=1, observed_at=NOW)
    st = _strategist(db_session, [])
    out = S.StrategistOutput(assessments=[_assessment(seeded.id, confidence=0.8)], new_gaps=[], headline="h")
    crit = S.CriticOutput(verdicts=[S.CriticVerdict(gap_id=seeded.id, strongest_objection="o", kosovo_killer="k",
                                                    risk_penalty=3, confidence=0.8, decision="proceed",
                                                    field_check_question="")])
    st.apply(out, crit, now=NOW, run_id=8)
    gap = repo.get_gap(db_session, seeded.id)
    assert gap.status == "verified" and gap.score_components["absence"] == 25 and gap.confidence == 0.8


def test_critic_kill_parks_with_flag_and_hard_filter_kills(db_session, seeded):
    repo.get_or_create_sector(db_session, "utilities-household-finance", "Utilities")
    g2, _ = repo.propose_gap(db_session, title="Consumer loans app", sector_slug="utilities-household-finance")
    st = _strategist(db_session, [])
    out = S.StrategistOutput(assessments=[_assessment(seeded.id),
                                          _assessment(g2.id, hard_filter_failed="regulated-finance-health-gambling")],
                             new_gaps=[], headline="h")
    crit = S.CriticOutput(verdicts=[S.CriticVerdict(gap_id=seeded.id, strongest_objection="o", kosovo_killer="k",
                                                    risk_penalty=15, confidence=0.3, decision="kill",
                                                    field_check_question="")])
    st.apply(out, crit, now=NOW, run_id=9)
    assert repo.get_gap(db_session, seeded.id).status == "parked"
    assert repo.get_gap(db_session, seeded.id).critic_flag == "critic-says-kill"
    assert repo.get_gap(db_session, g2.id).status == "killed" and repo.get_gap(db_session, g2.id).score_total == 0


def test_apply_limits_open_field_checks_and_creates_new_gaps(db_session, seeded):
    for i in range(5):
        repo.add_field_check(db_session, gap_id=seeded.id, question=f"q{i}", why="w", due=TODAY)
    st = _strategist(db_session, [])
    out = S.StrategistOutput(
        assessments=[_assessment(seeded.id, confidence=0.4, recommended_status="verifying",
                                 field_check_question="one more?")],
        new_gaps=[S.NewGapIdea(title="Dog walking app", sector_slug="pets", hypothesis="h", why_not_yet="w",
                               proven_model_slug=""),
                  S.NewGapIdea(title="Ghost", sector_slug="no-such-sector", hypothesis="h", why_not_yet="w",
                               proven_model_slug="")],
        headline="h")
    result = st.apply(out, S.CriticOutput(verdicts=[]), now=NOW, run_id=10)
    assert result.field_checks_added == 0 and len(repo.open_field_checks(db_session)) == 5
    assert result.new_gaps == 1 and repo.get_gap_by_title(db_session, "pets", "Dog walking app") is not None
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `TEST_DATABASE_URL=<url> uv run pytest tests/test_strategist.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'scout.strategy.schemas'`

- [ ] **Step 3: Write `scout/strategy/schemas.py`**

```python
"""Structured-output schemas for the Opus judgement calls. extra='forbid'; Literal enums; no constraints."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

PresenceLevel = Literal["absent", "exists-but-poor", "prishtina-only", "offline-only", "decent", "unknown"]
HardFilter = Literal["none", "regulated-finance-health-gambling", "physical-inventory-or-fleet", "cardo-overlap",
                     "test-cost-over-2000", "needs-full-time-before-revenue"]
GapStatus = Literal["candidate", "verifying", "verified", "parked", "killed"]
CriticDecision = Literal["proceed", "needs_field_check", "park", "kill"]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ComponentScores(_Strict):
    proof: int
    absence: int
    demand: int
    founder_fit: int
    risk_penalty: int


class GapAssessment(_Strict):
    gap_id: int
    scores: ComponentScores
    presence_level: PresenceLevel
    confidence: float
    hard_filter_failed: HardFilter
    reasoning: str
    field_check_question: str
    recommended_status: GapStatus


class NewGapIdea(_Strict):
    title: str
    sector_slug: str
    hypothesis: str
    why_not_yet: str
    proven_model_slug: str


class StrategistOutput(_Strict):
    assessments: list[GapAssessment]
    new_gaps: list[NewGapIdea]
    headline: str


class CriticVerdict(_Strict):
    gap_id: int
    strongest_objection: str
    kosovo_killer: str
    risk_penalty: int
    confidence: float
    decision: CriticDecision
    field_check_question: str


class CriticOutput(_Strict):
    verdicts: list[CriticVerdict]


class DroppedTask(_Strict):
    task_id: int
    reason: str


class DirectorReview(_Strict):
    keep_task_ids_in_order: list[int]
    dropped: list[DroppedTask]
    note: str
```

- [ ] **Step 4: Write `scout/strategy/strategist.py`**

```python
"""Strategist (scores gaps) and Critic (attacks the top three); Python applies the rubric and writes state."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal

from scout.db import repo
from scout.db.models import GapAssessment as GapAssessmentRow
from scout.llm.gateway import LLM
from scout.strategy import schemas as S
from scout.strategy.rubric import RUBRIC_TEXT, needs_field_check, score_gap

MAX_FACTS_CHARS = 90_000  # ≈ 25k tokens
VERIFIED_CHECK_MAX_AGE_DAYS = 30
VERIFIED_MIN_CONFIDENCE = 0.7

STRATEGIST_SYSTEM = """You are the Strategist of Kosovo Gap Scout. Once a day you read what the research workers
learned and judge each tracked gap: a consumer business model proven elsewhere that may be missing in Kosovo,
to be started by a solo software engineer in Prishtina with 5–10 hours a week and ≤ €2,000.

Rules:
- Score only from the facts and digests given; cite them in `reasoning`. If the evidence is thin, lower
  `confidence` instead of guessing scores.
- Presence level must come from a presence_check fact; otherwise keep the gap's current level or "unknown".
- Recommend "verified" only when a presence check exists, proof has at least two sources with one nearby
  market, a payment path is recorded and your confidence is ≥ 0.7. Recommend "killed" only through a hard
  filter — otherwise "parked".
- A field check is a question the founder can answer in three minutes by phone or by walking into a shop in
  Prishtina, Prizren, Pejë, Gjakovë, Mitrovicë, Ferizaj or Gjilan. Propose one only when it would change the
  score or the confidence materially.
- Propose new gaps only when the facts show a proven model with no sign of a Kosovo equivalent; one line of
  hypothesis each, sector slug from the taxonomy in the input.
- Be concrete and short. Reasoning ≤ 80 words per gap.
"""

CRITIC_SYSTEM = """You are the Critic of Kosovo Gap Scout. You see the Strategist's top gaps and the same facts.
Your job is to find what would make a careful Kosovar operator say "this will not work here": the payment
path (cash culture, no PayPal payouts, card fees), trust (people buy from people they know), informality
(a WhatsApp group already does it for free), logistics, a hidden incumbent (a Telegram/Instagram seller,
a bank's app, Gjirafa, Wolt, a telecom), regulation, or a market too small for the model's economics.
For each gap give the strongest objection, the Kosovo-specific killer, your own risk_penalty (0–15) and
confidence (0–1), and a decision: proceed, needs_field_check (with the question), park or kill.
Decide "kill" only if the objection is close to certain; otherwise "park" or "needs_field_check".
"""


@dataclass
class StrategyInputs:
    country_md: str
    sector_digests: dict[str, str]
    facts: list[dict]
    gaps: list[dict]
    taxonomy: list[str] = field(default_factory=list)


@dataclass
class GapChange:
    gap_id: int
    title: str
    old_status: str
    new_status: str
    old_score: int
    new_score: int
    confidence: float
    why: str


@dataclass
class ApplyResult:
    changes: list[GapChange] = field(default_factory=list)
    field_checks_added: int = 0
    new_gaps: int = 0


def _system(text: str) -> list[dict]:
    return [{"type": "text", "text": text},
            {"type": "text", "text": RUBRIC_TEXT, "cache_control": {"type": "ephemeral"}}]


class Strategist:
    def __init__(self, llm: LLM, session) -> None:
        self.llm = llm
        self.session = session

    def collect_inputs(self, *, since: datetime, now: datetime,
                       sector_slugs: list[str] | None = None) -> StrategyInputs:
        s = self.session
        facts_rows = repo.fresh_facts_since(s, since, sector_slugs=sector_slugs, now=now)
        facts = sorted(({"claim": f.claim, "confidence": f.confidence, "type": f.entity_type, "key": f.entity_key,
                         "source": f.source_url or f.source_name, "observed": f.observed_at.date().isoformat()}
                        for f in facts_rows), key=lambda d: (-d["confidence"], d["claim"]))
        while len(json.dumps(facts, ensure_ascii=False)) > MAX_FACTS_CHARS and facts:
            facts.pop()
        gaps = []
        sectors = {sec.id: sec.slug for sec in repo.list_sectors(s)}
        for g in repo.list_gaps(s, statuses=["candidate", "verifying", "verified", "parked"],
                                sector_slugs=sector_slugs):
            gaps.append({"id": g.id, "title": g.title, "sector": sectors.get(g.sector_id), "status": g.status,
                         "score": g.score_total, "confidence": g.confidence, "presence_level": g.presence_level,
                         "has_presence_check": repo.has_presence_check(s, g, now=now),
                         "hypothesis": g.hypothesis_md[:600], "why_not_yet": g.why_not_yet_md[:400],
                         "components": g.score_components or {}})
        gaps.sort(key=lambda d: d["id"])
        wanted = {g["sector"] for g in gaps} | set(sector_slugs or [])
        digests = {slug: (repo.get_digest(s, f"sector:{slug}") or "")[:3000] for slug in sorted(wanted) if slug}
        return StrategyInputs(country_md=(repo.get_digest(s, "country") or "")[:3000], sector_digests=digests,
                              facts=facts, gaps=gaps, taxonomy=sorted(sectors.values()))

    def assess(self, inputs: StrategyInputs, today: date) -> S.StrategistOutput:
        payload = {"date": today.isoformat(), "country_digest": inputs.country_md,
                   "sector_digests": inputs.sector_digests, "facts": inputs.facts, "gaps": inputs.gaps,
                   "sector_taxonomy": inputs.taxonomy}
        res = self.llm.parse(model="claude-opus-5-5", output_format=S.StrategistOutput,
                             system=_system(STRATEGIST_SYSTEM),
                             user=json.dumps(payload, sort_keys=True, ensure_ascii=False),
                             max_tokens=8192, effort="medium", est_eur=Decimal("0.40"))
        return res.parsed

    def critique(self, output: S.StrategistOutput, inputs: StrategyInputs, today: date,
                 top_n: int = 3) -> S.CriticOutput:
        ranked = sorted(output.assessments, key=lambda a: -(a.scores.proof + a.scores.absence + a.scores.demand
                                                            + a.scores.founder_fit - a.scores.risk_penalty))
        top = ranked[:top_n]
        if not top:
            return S.CriticOutput(verdicts=[])
        ids = {a.gap_id for a in top}
        payload = {"date": today.isoformat(), "assessments": [a.model_dump() for a in top],
                   "gaps": [g for g in inputs.gaps if g["id"] in ids], "facts": inputs.facts,
                   "country_digest": inputs.country_md}
        res = self.llm.parse(model="claude-opus-5-5", output_format=S.CriticOutput, system=_system(CRITIC_SYSTEM),
                             user=json.dumps(payload, sort_keys=True, ensure_ascii=False),
                             max_tokens=4096, effort="high", est_eur=Decimal("0.30"))
        return res.parsed

    def apply(self, output: S.StrategistOutput, critic: S.CriticOutput, *, now: datetime, run_id: int | None,
              max_open_field_checks: int = 5) -> ApplyResult:
        s = self.session
        result = ApplyResult()
        verdicts = {v.gap_id: v for v in critic.verdicts}
        open_checks = len(repo.open_field_checks(s))
        for a in output.assessments:
            gap = repo.get_gap(s, a.gap_id)
            if gap is None or gap.status == "killed":
                continue
            v = verdicts.get(a.gap_id)
            risk_penalty = max(a.scores.risk_penalty, v.risk_penalty) if v else a.scores.risk_penalty
            confidence = min(a.confidence, v.confidence) if v else a.confidence
            has_check_60 = repo.has_presence_check(s, gap, now=now, max_age_days=60)
            has_check_30 = repo.has_presence_check(s, gap, now=now, max_age_days=VERIFIED_CHECK_MAX_AGE_DAYS)
            presence = a.presence_level if has_check_60 else (gap.presence_level or "unknown")
            score = score_gap(proof=a.scores.proof, absence=a.scores.absence, demand=a.scores.demand,
                              founder_fit=a.scores.founder_fit, risk_penalty=risk_penalty,
                              presence_level=presence, has_presence_check=has_check_60,
                              hard_filter_failed=None if a.hard_filter_failed == "none" else a.hard_filter_failed,
                              confidence=confidence)
            old_status, old_score = gap.status, gap.score_total
            question = (v.field_check_question if v and v.field_check_question else a.field_check_question).strip()
            new_status, flag = old_status, gap.critic_flag
            if score.killed:
                new_status = "killed"
            elif v and v.decision == "kill":
                new_status, flag = "parked", "critic-says-kill"
            elif v and v.decision == "park":
                new_status = "parked"
            elif a.recommended_status == "killed":
                new_status, flag = "parked", "strategist-says-kill"
            elif a.recommended_status == "parked":
                new_status = "parked"
            elif a.recommended_status == "verified" and has_check_30 and score.confidence >= VERIFIED_MIN_CONFIDENCE \
                    and not (v and v.decision == "needs_field_check"):
                new_status = "verified"
            elif score.total >= 60:
                new_status = "verifying"
            else:
                new_status = "candidate"
            wants_check = (v and v.decision == "needs_field_check") or needs_field_check(score.total, score.confidence)
            if wants_check and question and open_checks < max_open_field_checks:
                repo.add_field_check(s, gap_id=gap.id, question=question,
                                     why=f"score {score.total}, confidence {score.confidence:.2f}",
                                     due=(now + timedelta(days=7)).date())
                open_checks += 1
                result.field_checks_added += 1
            gap.presence_level = presence
            gap.score_total = score.total
            gap.score_components = score.components
            gap.confidence = score.confidence
            gap.status = new_status
            gap.critic_flag = flag
            gap.updated_at = now
            gap.last_assessed_run_id = run_id
            s.add(GapAssessmentRow(gap_id=gap.id, run_id=run_id, model="claude-opus-5-5",
                                   strategist=a.model_dump(), critic=v.model_dump() if v else None,
                                   score_total=score.total, confidence=score.confidence))
            s.commit()
            if new_status != old_status or score.total != old_score:
                result.changes.append(GapChange(gap.id, gap.title, old_status, new_status, old_score, score.total,
                                                score.confidence, (a.reasoning or "")[:200]))
        for idea in output.new_gaps:
            if repo.get_sector(s, idea.sector_slug) is None:
                continue
            _, created = repo.propose_gap(s, title=idea.title, sector_slug=idea.sector_slug,
                                          proven_model_slug=idea.proven_model_slug or None,
                                          hypothesis_md=idea.hypothesis, why_not_yet_md=idea.why_not_yet,
                                          run_id=run_id)
            result.new_gaps += int(created)
        return result
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `TEST_DATABASE_URL=<url> uv run pytest tests/test_strategist.py -v`
Expected: 8 PASSED

- [ ] **Step 6: Commit**

```bash
uv run ruff check . && uv run ruff format .
git add -A && git commit -m "feat(strategy): Opus strategist and critic with rubric-enforced apply"
```

---

### Task 19: Editor — the daily brief

**Files:**
- Create: `scout/editor/__init__.py`, `scout/editor/brief.py`
- Test: `tests/test_brief.py`

**Interfaces:**
- Consumes: `repo.fresh_facts_since`, `repo.open_field_checks`, `repo.tasks_for_run`, `repo.spent_on`, `repo.spent_between`, `repo.places_calls_in_month`, `repo.save_brief` (Tasks 4–5); `LLM.create_text` + `LLMError` (Task 7); `GapChange` (Task 18); `ChartDiffReport` (Task 16).
- Produces: `BriefInputs(run, today, changes, fresh_facts, field_checks, tasks, chart_errors, spent_today, spent_mtd, cap, places_calls)`, `collect_inputs(session, run, *, today, now, changes, chart_report=None) -> BriefInputs`, `is_quiet(inputs) -> bool`, `render_brief(inputs, narrative: str = "") -> str`, `write_brief(session, llm, run, *, today, now, changes, chart_report=None) -> str` (saves and returns Markdown).

- [ ] **Step 1: Write the failing tests**

`tests/test_brief.py`:
```python
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest

from scout.db import repo
from scout.db.repo import CostRecord, FactIn
from scout.editor import brief as B
from scout.llm.gateway import LLM
from scout.strategy.strategist import GapChange
from tests.fakes import FakeClient, FakeGuard, FakeMessage, text_block

pytestmark = pytest.mark.db
NOW = datetime(2026, 10, 19, 6, 40, tzinfo=UTC)
TODAY = date(2026, 10, 19)


@pytest.fixture
def run(db_session):
    r = repo.start_run(db_session, day=TODAY, phase="foundation", budget_cap_eur=Decimal("3"),
                       started_at=NOW - timedelta(minutes=40))
    t = repo.enqueue_task(db_session, profile="map-sector", payload={"sector": "pets"}, run_id=r.id)
    repo.claim_next_task(db_session, "w", now=NOW)
    repo.finish_task(db_session, t, result_md="ok", actual_cost_eur=Decimal("0.31"), now=NOW)
    repo.record_cost(db_session, CostRecord("llm", "anthropic", "claude-sonnet-5-5", {}, Decimal("0.31")),
                     day=TODAY, run_id=r.id)
    return r


def test_quiet_day_single_line_and_no_model_call(db_session, run):
    client = FakeClient([])
    md = B.write_brief(db_session, LLM(client, FakeGuard(), Decimal("0.92")), run, today=TODAY, now=NOW, changes=[])
    assert md == "Quiet day — 1 tasks, €0.31, nothing moved."
    assert client.messages.calls == [] and repo.latest_brief(db_session).markdown == md


def test_busy_day_has_all_sections_and_narrative(db_session, run):
    repo.get_or_create_sector(db_session, "pets", "Pets")
    gap, _ = repo.propose_gap(db_session, title="Pet sitting marketplace", sector_slug="pets")
    repo.upsert_fact(db_session, FactIn(claim="Prizren has 3 pet shops", entity_type="sector", entity_key="pets",
                                        confidence=0.7, sector_slug="pets", source_url="https://x"),
                     run_id=run.id, observed_at=NOW - timedelta(minutes=10))
    repo.add_field_check(db_session, gap_id=gap.id, question="Any sitters in Prizren?", why="low confidence",
                         due=TODAY + timedelta(days=7))
    changes = [GapChange(gap.id, "Pet sitting marketplace", "candidate", "verifying", 0, 64, 0.5, "strong proof")]
    client = FakeClient([FakeMessage(content=[text_block("Today the scout found a promising pet gap.")])])
    md = B.write_brief(db_session, LLM(client, FakeGuard(), Decimal("0.92")), run, today=TODAY, now=NOW,
                       changes=changes)
    for heading in ("## What changed", "## Field checks for you", "## What the scout did", "## What it learned",
                    "## Source health", "## Spend"):
        assert heading in md
    assert "Pet sitting marketplace" in md and "candidate → verifying" in md and "64" in md
    assert "Any sitters in Prizren?" in md and "Prizren has 3 pet shops" in md and "<https://x>" in md
    assert "€0.31" in md and "cap €3.00" in md
    assert md.splitlines()[0].startswith("# ") and "promising pet gap" in md
    kw = client.messages.calls[0]
    assert kw["model"] == "claude-sonnet-5-5" and kw["output_config"] == {"effort": "low"}


def test_narrative_failure_is_tolerated(db_session, run):
    repo.upsert_fact(db_session, FactIn(claim="Something important", entity_type="news", entity_key="k",
                                        confidence=0.9), run_id=run.id, observed_at=NOW)
    client = FakeClient([FakeMessage(content=[], stop_reason="refusal")])
    md = B.write_brief(db_session, LLM(client, FakeGuard(), Decimal("0.92")), run, today=TODAY, now=NOW, changes=[])
    assert "Something important" in md and "## What it learned" in md
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `TEST_DATABASE_URL=<url> uv run pytest tests/test_brief.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'scout.editor'`

- [ ] **Step 3: Write `scout/editor/brief.py`**

`scout/editor/__init__.py`: empty file.

```python
"""Deterministic Markdown brief with one optional Sonnet paragraph. Quiet days cost nothing."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal

from scout.budget.guard import BudgetExceeded
from scout.db import repo
from scout.llm.gateway import LLM, LLMError

NARRATIVE_SYSTEM = ("You write the two-sentence opening of a daily brief for a founder in Kosovo who is looking "
                    "for a business gap. Plain, specific, no hype, no bullet points. Mention the most important "
                    "change and what the founder should do today, if anything.")


@dataclass
class BriefInputs:
    run: object
    today: date
    changes: list
    fresh_facts: list
    field_checks: list
    tasks: list
    chart_errors: list[str]
    spent_today: Decimal
    spent_mtd: Decimal
    cap: Decimal
    places_calls: int
    gap_titles: dict[int, str] = field(default_factory=dict)


def collect_inputs(session, run, *, today: date, now: datetime, changes: list, chart_report=None) -> BriefInputs:
    facts = [f for f in repo.fresh_facts_since(session, run.started_at, now=now, min_confidence=0.6)
             if f.source_name != "seed"]
    checks = repo.open_field_checks(session)[:5]
    titles = {}
    for fc in checks:
        gap = repo.get_gap(session, fc.gap_id) if fc.gap_id else None
        titles[fc.id] = gap.title if gap else "(general)"
    return BriefInputs(run=run, today=today, changes=list(changes), fresh_facts=facts, field_checks=checks,
                       tasks=repo.tasks_for_run(session, run.id),
                       chart_errors=list(chart_report.errors) if chart_report else [],
                       spent_today=repo.spent_on(session, today),
                       spent_mtd=repo.spent_between(session, today.replace(day=1), today),
                       cap=Decimal(run.budget_cap_eur), places_calls=repo.places_calls_in_month(session, today),
                       gap_titles=titles)


def is_quiet(inputs: BriefInputs) -> bool:
    return not inputs.changes and not inputs.fresh_facts


def _money(x: Decimal) -> str:
    return f"€{Decimal(x).quantize(Decimal('0.01'))}"


def render_brief(inputs: BriefInputs, narrative: str = "") -> str:
    n_tasks = len(inputs.tasks)
    if is_quiet(inputs):
        return f"Quiet day — {n_tasks} tasks, {_money(inputs.spent_today)}, nothing moved."
    top = sorted(inputs.changes, key=lambda c: -c.new_score)
    headline = (f"# {inputs.today.isoformat()} — {top[0].title}: {top[0].new_status} ({top[0].new_score}/100)"
                if top else f"# {inputs.today.isoformat()} — {len(inputs.fresh_facts)} new facts, no gap moved")
    lines = [headline, ""]
    if narrative:
        lines += [narrative.strip(), ""]
    lines.append("## What changed")
    lines += [f"- **{c.title}** — {c.old_status} → {c.new_status}, score {c.old_score} → {c.new_score}, "
              f"confidence {c.confidence:.2f}. {c.why}" for c in top] or ["- nothing"]
    lines += ["", "## Field checks for you"]
    lines += [f"- [{fc.id}] {fc.question} — _{fc.why}_ (gap: {inputs.gap_titles.get(fc.id, '')}; due {fc.due})"
              for fc in inputs.field_checks] or ["- none open"]
    lines += ["", "## What the scout did"]
    for t in inputs.tasks:
        target = (t.payload or {}).get("sector") or (t.payload or {}).get("gap_title") or (t.payload or {}).get("theme") or ""
        lines.append(f"- {t.profile} {target} — {t.status}, {_money(t.actual_cost_eur)}"
                     + (f" — {t.error[:80]}" if t.error else ""))
    lines += ["", "## What it learned"]
    for f in inputs.fresh_facts[:5]:
        src = f" <{f.source_url}>" if f.source_url else f" ({f.source_name})"
        lines.append(f"- [{f.confidence:.2f}] {f.claim}{src}")
    failed = [t for t in inputs.tasks if t.status == "failed"]
    lines += ["", "## Source health",
              f"- tasks failed: {len(failed)}; chart errors: {len(inputs.chart_errors)}; "
              f"Places calls this month: {inputs.places_calls}/4500"]
    lines += [f"- {e}" for e in inputs.chart_errors[:5]]
    lines += ["", "## Spend",
              f"- today {_money(inputs.spent_today)} (cap {_money(inputs.cap)}); month to date {_money(inputs.spent_mtd)}"]
    return "\n".join(lines).strip()


def write_brief(session, llm: LLM, run, *, today: date, now: datetime, changes: list, chart_report=None) -> str:
    inputs = collect_inputs(session, run, today=today, now=now, changes=changes, chart_report=chart_report)
    narrative = ""
    if not is_quiet(inputs):
        summary = render_brief(inputs)[:6000]
        try:
            narrative = llm.create_text(model="claude-sonnet-5-5", system=NARRATIVE_SYSTEM, user=summary,
                                        max_tokens=300, effort="low", est_eur=Decimal("0.03")).text
        except (LLMError, BudgetExceeded):
            narrative = ""
    md = render_brief(inputs, narrative)
    repo.save_brief(session, run_id=run.id, day=today, markdown=md)
    return md
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `TEST_DATABASE_URL=<url> uv run pytest tests/test_brief.py -v`
Expected: 3 PASSED

- [ ] **Step 5: Commit**

```bash
uv run ruff check . && uv run ruff format .
git add -A && git commit -m "feat(editor): deterministic daily brief with skip rule and optional narrative"
```

---

### Task 20: Planner (pure) and state loader

**Files:**
- Create: `scout/director/__init__.py`, `scout/director/planner.py`
- Test: `tests/test_planner.py`

**Interfaces:**
- Consumes: `PROFILES` (Task 13), `repo.list_sectors`, `repo.list_digests`, `repo.list_gaps`, `repo.has_presence_check`, `repo.open_field_checks`, `repo.spent_on`, `repo.get_setting`, `repo.tasks_for_run` (Tasks 4–5), `seeds.CULTURE_THEMES` (Task 22 — import inside `load_state` only).
- Produces: `PHASES = ("foundation", "verification", "maintenance")`, `PHASE_RULES: dict[str, dict]`, `SectorInfo(slug, name_en, priority, status, last_mapped_at, last_hunted_at)`, `GapInfo(id, title, sector_slug, score_total, confidence, status, has_fresh_check)`, `PlannerState(today, sectors, culture_themes_missing, gaps, open_field_checks, spent_today, cap, flagged_gap_ids, deep_dive_done_this_month, done_today: set[tuple[str, str]])`, `PlannedTask(profile, payload, priority, est_cost_eur)`, `plan_tasks(state, phase) -> list[PlannedTask]`, `load_state(session, *, today, now, cap, run_ids_today: list[int]) -> PlannerState`.

- [ ] **Step 1: Write the failing tests**

`tests/test_planner.py`:
```python
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from scout.director import planner as P

MONDAY = date(2026, 10, 19)
SUNDAY = date(2026, 10, 25)
NOW = datetime(2026, 10, 19, 6, 0, tzinfo=UTC)


def _state(**over):
    base = dict(
        today=MONDAY,
        sectors=[P.SectorInfo("pets", "Pets", 2, "unmapped", None, None),
                 P.SectorInfo("home-services", "Home services", 1, "unmapped", None, None),
                 P.SectorInfo("tutoring-education", "Tutoring", 1, "mapped", NOW - timedelta(days=3), None),
                 P.SectorInfo("car-services", "Cars", 2, "mapped", NOW - timedelta(days=30),
                              NOW - timedelta(days=10))],  # map is stale (>14 d), hunt is not (<21 d)
        culture_themes_missing=["payments-and-trust"],
        gaps=[P.GapInfo(1, "Pet sitting", "pets", 70, 0.5, "candidate", False),
              P.GapInfo(2, "Dentist booking", "health-booking", 65, 0.5, "verifying", True),
              P.GapInfo(3, "Dead idea", "pets", 10, 0.2, "killed", False)],
        open_field_checks=0, spent_today=Decimal("0"), cap=Decimal("3.00"), flagged_gap_ids=[],
        deep_dive_done_this_month=False, done_today=set())
    base.update(over)
    return P.PlannerState(**base)


def _profiles(tasks):
    return [t.profile for t in tasks]


def test_foundation_monday_plan():
    tasks = P.plan_tasks(_state(), "foundation")
    assert _profiles(tasks) == ["verify-gap", "map-sector", "map-sector", "hunt-models", "chart-diff",
                                "news-scan", "culture"]
    assert [t.payload["sector"] for t in tasks if t.profile == "map-sector"] == ["home-services", "pets"]
    assert tasks[0].payload["gap_id"] == 1  # a gap without a fresh presence check is verified first
    assert tasks[3].payload["sector"] == "tutoring-education"  # mapped, never hunted
    assert tasks[-1].payload["theme"] == "payments-and-trust"
    assert sum(t.est_cost_eur for t in tasks) <= Decimal("3.00")


def test_nothing_when_cap_spent_and_dedupe_against_done_today():
    assert P.plan_tasks(_state(spent_today=Decimal("3.00")), "foundation") == []
    tasks = P.plan_tasks(_state(done_today={("map-sector", "home-services"), ("news-scan", "")}), "foundation")
    assert ("news-scan", "") not in {(t.profile, t.payload.get("sector", "")) for t in tasks}
    assert [t.payload["sector"] for t in tasks if t.profile == "map-sector"] == ["pets", "car-services"]


def test_budget_trims_lowest_priority_first():
    tasks = P.plan_tasks(_state(cap=Decimal("0.80")), "foundation")
    assert _profiles(tasks) == ["verify-gap", "map-sector", "chart-diff"]  # 0.40 + 0.35 + 0.05 = 0.80


def test_sunday_deep_dive_and_verification_phase():
    tasks = P.plan_tasks(_state(today=SUNDAY), "verification")
    assert _profiles(tasks) == ["verify-gap", "verify-gap", "news-scan", "deep-dive"]
    assert tasks[-1].payload["gap_id"] == 1 and tasks[-1].payload["gap_title"] == "Pet sitting"
    assert {t.payload["gap_id"] for t in tasks[:2]} == {1, 2}


def test_maintenance_only_flagged_gaps_and_first_sunday_deep_dive():
    assert _profiles(P.plan_tasks(_state(today=date(2026, 11, 2)), "maintenance")) == ["chart-diff", "news-scan"]
    tasks = P.plan_tasks(_state(today=date(2026, 11, 1), flagged_gap_ids=[2]), "maintenance")  # Sunday, 1st
    assert _profiles(tasks) == ["verify-gap", "news-scan", "deep-dive"] and tasks[0].priority == 90


def test_field_check_limit_blocks_verify_of_unchecked_gaps():
    tasks = P.plan_tasks(_state(open_field_checks=5), "foundation")
    verify = [t for t in tasks if t.profile == "verify-gap"]
    assert verify and verify[0].payload["gap_id"] == 2  # unchecked gap 1 waits for the founder's answers
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_planner.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'scout.director'`

- [ ] **Step 3: Write `scout/director/planner.py`**

`scout/director/__init__.py`: empty file.

```python
"""Deterministic daily planner (spec B9). Pure function over a snapshot of the knowledge base."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal

from scout.db import repo
from scout.worker.profiles import PROFILES

PHASES = ("foundation", "verification", "maintenance")
PHASE_RULES: dict[str, dict] = {
    "foundation": {"cap": Decimal("3.00"), "map-sector": 2, "hunt-models": 2, "verify-gap": 1, "culture": 1},
    "verification": {"cap": Decimal("1.50"), "map-sector": 0, "hunt-models": 0, "verify-gap": 2, "culture": 0},
    "maintenance": {"cap": Decimal("0.80"), "map-sector": 0, "hunt-models": 0, "verify-gap": 0, "culture": 0},
}
MAP_STALE_DAYS = 14
HUNT_STALE_DAYS = 21
CHART_DIFF_EST = Decimal("0.05")
MAX_OPEN_FIELD_CHECKS = 5
PRIORITY = {"verify-gap": 85, "map-sector": 80, "hunt-models": 75, "chart-diff": 70, "news-scan": 60,
            "culture": 55, "deep-dive": 40}


@dataclass
class SectorInfo:
    slug: str
    name_en: str
    priority: int
    status: str
    last_mapped_at: datetime | None
    last_hunted_at: datetime | None


@dataclass
class GapInfo:
    id: int
    title: str
    sector_slug: str
    score_total: int
    confidence: float
    status: str
    has_fresh_check: bool


@dataclass
class PlannerState:
    today: date
    sectors: list[SectorInfo]
    culture_themes_missing: list[str]
    gaps: list[GapInfo]
    open_field_checks: int
    spent_today: Decimal
    cap: Decimal
    flagged_gap_ids: list[int] = field(default_factory=list)
    deep_dive_done_this_month: bool = False
    done_today: set[tuple[str, str]] = field(default_factory=set)


@dataclass
class PlannedTask:
    profile: str
    payload: dict
    priority: int
    est_cost_eur: Decimal


def _key(profile: str, payload: dict) -> tuple[str, str]:
    return profile, str(payload.get("sector") or payload.get("gap_id") or payload.get("theme") or "")


def _gap_payload(g: GapInfo) -> dict:
    return {"gap_id": g.id, "gap_title": g.title, "sector": g.sector_slug}


def _verify_candidates(state: PlannerState) -> list[GapInfo]:
    live = [g for g in state.gaps if g.status in ("candidate", "verifying", "verified")]
    flagged = [g for g in live if g.id in state.flagged_gap_ids]
    needs = [g for g in live if g.id not in state.flagged_gap_ids and (not g.has_fresh_check or g.confidence < 0.6)]
    if state.open_field_checks >= MAX_OPEN_FIELD_CHECKS:
        # the founder has enough homework: prefer gaps whose check is already done
        needs.sort(key=lambda g: (not g.has_fresh_check, -g.score_total, -g.confidence))
    else:
        needs.sort(key=lambda g: (g.has_fresh_check, -g.score_total, g.confidence))
    return flagged + needs


def plan_tasks(state: PlannerState, phase: str) -> list[PlannedTask]:
    rules = PHASE_RULES[phase]
    if state.spent_today >= state.cap:
        return []
    weekday = state.today.weekday()  # Monday = 0, Sunday = 6
    wanted: list[PlannedTask] = []

    def add(profile: str, payload: dict, priority: int | None = None, est: Decimal | None = None) -> None:
        if _key(profile, payload) in state.done_today or any(_key(t.profile, t.payload) == _key(profile, payload)
                                                              for t in wanted):
            return
        est = est if est is not None else PROFILES[profile].est_cost_eur
        wanted.append(PlannedTask(profile, payload, priority if priority is not None else PRIORITY[profile], est))

    # verify-gap
    n_verify = rules["verify-gap"]
    for g in _verify_candidates(state):
        is_flagged = g.id in state.flagged_gap_ids
        if phase == "maintenance" and not is_flagged:
            continue
        if not is_flagged and n_verify <= 0:
            continue
        add("verify-gap", _gap_payload(g), 90 if is_flagged else None)
        if not is_flagged:
            n_verify -= 1
    # map-sector: unmapped by priority, then stale
    unmapped = sorted((s for s in state.sectors if s.status == "unmapped"), key=lambda s: (s.priority, s.slug))
    stale_cut = datetime.combine(state.today, datetime.min.time(), tzinfo=None) - timedelta(days=MAP_STALE_DAYS)
    stale = sorted((s for s in state.sectors if s.status != "unmapped" and s.last_mapped_at is not None
                    and s.last_mapped_at.replace(tzinfo=None) < stale_cut), key=lambda s: s.last_mapped_at)
    mapped_today: list[str] = []
    for s in (unmapped + stale)[: rules["map-sector"] + len(state.done_today)]:
        if sum(1 for t in wanted if t.profile == "map-sector") >= rules["map-sector"]:
            break
        before = len(wanted)
        add("map-sector", {"sector": s.slug, "sector_name": s.name_en})
        if len(wanted) > before:
            mapped_today.append(s.slug)
    # hunt-models: mapped sectors never hunted or hunted long ago, not mapped today
    hunt_cut = stale_cut + timedelta(days=MAP_STALE_DAYS - HUNT_STALE_DAYS)
    huntable = [s for s in state.sectors if s.status != "unmapped" and s.slug not in mapped_today
                and (s.last_hunted_at is None or s.last_hunted_at.replace(tzinfo=None) < hunt_cut)]
    huntable.sort(key=lambda s: (s.last_hunted_at is not None, s.priority, s.slug))
    for s in huntable:
        if sum(1 for t in wanted if t.profile == "hunt-models") >= rules["hunt-models"]:
            break
        add("hunt-models", {"sector": s.slug, "sector_name": s.name_en})
    # weekly and daily fixtures
    if weekday == 0:
        add("chart-diff", {}, est=CHART_DIFF_EST)
    add("news-scan", {})
    if rules["culture"] and state.culture_themes_missing:
        theme = sorted(state.culture_themes_missing)[0]
        add("culture", {"theme": theme, "theme_name": theme.replace("-", " ")})
    if weekday == 6 and (phase != "maintenance" or (state.today.day <= 7 and not state.deep_dive_done_this_month)):
        live = [g for g in state.gaps if g.status in ("candidate", "verifying", "verified") and g.score_total >= 50]
        live.sort(key=lambda g: (-g.score_total, -g.confidence))
        if live:
            add("deep-dive", _gap_payload(live[0]) | {"hypothesis": ""})
    # order by priority, then fit the budget greedily
    wanted.sort(key=lambda t: (-t.priority, t.profile))
    remaining = state.cap - state.spent_today
    planned: list[PlannedTask] = []
    for t in wanted:
        if t.est_cost_eur <= remaining:
            planned.append(t)
            remaining -= t.est_cost_eur
    return planned


def load_state(session, *, today: date, now: datetime, cap: Decimal, run_ids_today: list[int]) -> PlannerState:
    from scout.seeds import CULTURE_THEMES

    sectors = [SectorInfo(s.slug, s.name_en, s.priority, s.status, s.last_mapped_at, s.last_hunted_at)
               for s in repo.list_sectors(session)]
    have = {d.key for d in repo.list_digests(session, "culture:")}
    missing = [slug for slug, _name in CULTURE_THEMES if f"culture:{slug}" not in have]
    slug_by_id = {s.id: s.slug for s in repo.list_sectors(session)}
    gaps = [GapInfo(g.id, g.title, slug_by_id.get(g.sector_id, ""), g.score_total, g.confidence, g.status,
                    repo.has_presence_check(session, g, now=now, max_age_days=30))
            for g in repo.list_gaps(session)]
    done_today: set[tuple[str, str]] = set()
    for run_id in run_ids_today:
        for t in repo.tasks_for_run(session, run_id):
            done_today.add(_key(t.profile, t.payload or {}))
    first = today.replace(day=1)
    deep_done = any(t.profile == "deep-dive" and t.status == "done"
                    for rid in run_ids_today for t in repo.tasks_for_run(session, rid)) or bool(
        repo.get_setting(session, f"deep-dive-done:{first.isoformat()}"))
    return PlannerState(today=today, sectors=sectors, culture_themes_missing=missing, gaps=gaps,
                        open_field_checks=len(repo.open_field_checks(session)),
                        spent_today=repo.spent_on(session, today), cap=cap,
                        flagged_gap_ids=list(repo.get_setting(session, "flagged_gaps", []) or []),
                        deep_dive_done_this_month=deep_done, done_today=done_today)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_planner.py -v`
Expected: 6 PASSED. If `test_foundation_monday_plan` fails on ordering, the expected order is by `PRIORITY` descending then profile name; check `PRIORITY` before changing the test.

- [ ] **Step 5: Commit**

```bash
uv run ruff check . && uv run ruff format .
git add -A && git commit -m "feat(director): deterministic daily planner and state loader"
```

---

### Task 21: Director `run_once` — the daily run end to end

**Files:**
- Create: `scout/director/run.py`
- Modify: `scout/db/repo.py` (append `set_gap_test_plan`, `runs_on_day`)
- Test: `tests/test_run_once.py`

**Interfaces:**
- Consumes: everything above. `Settings` (Task 1); `BudgetGuard` (Task 6); `LLM` (Task 7); `AskDataClient`, `PlacesClient` (Tasks 8, 11); `ToolContext` (Task 12); `PROFILES`, `build_system`, `build_brief`, `journal_markdown` (Task 13); `ResearchWorker` (Task 14); `Extractor` (Task 15); `run_chart_diff`, `classify_and_record` (Task 16); `Strategist` (Task 18); `write_brief` (Task 19); `plan_tasks`, `load_state`, `PHASE_RULES` (Task 20); `DirectorReview` (Task 18).
- Produces: `repo.set_gap_test_plan(session, gap_id, md) -> None`, `repo.runs_on_day(session, day) -> list[Run]`; `RunSummary(run_id, day, phase, planned, done, failed, spent_eur, brief_md, stopped_reason)`; `run_once(settings, *, today=None, now=None, budget_override=None, phase_override=None, dry_run=False, client=None, session_factory=None, places=None, askdata=None, apple_fetch=apple.fetch_top_free, play_fetch=play.fetch_top_free, runner_factory=None, clock=None, worker_id="director") -> RunSummary`; `review_plan(llm, tasks, *, journal_md) -> tuple[list, list[str]]` (Opus drop/reorder).

- [ ] **Step 1: Append to `scout/db/repo.py`**

```python


def set_gap_test_plan(session: Session, gap_id: int, md: str) -> None:
    gap = session.get(Gap, gap_id)
    if gap is not None:
        gap.test_plan_md = md
        session.commit()


def runs_on_day(session: Session, day: date) -> list[Run]:
    return list(session.scalars(select(Run).where(Run.day == day).order_by(Run.id)))
```

- [ ] **Step 2: Write the failing tests**

`tests/test_run_once.py`:
```python
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from scout.db import repo
from scout.db.base import make_engine, make_session_factory
from scout.db.repo import FactIn
from scout.director import run as R
from scout.seeds import seed_all
from scout.sources.types import ChartEntry
from scout.strategy import schemas as S
from tests.fakes import FakeClient, FakeMessage, fake_runner_factory, text_block, tool_use_block

pytestmark = pytest.mark.db
MONDAY = date(2026, 10, 19)
NOW = datetime(2026, 10, 19, 4, 0, tzinfo=UTC)  # 06:00 in Kosovo


def _chart(country, limit=25, http=None):
    return [ChartEntry(1, "1", "Wolt", "Wolt", (), "u")]


def _conversation():
    return [FakeMessage(content=[tool_use_block("kb_search", {"query": "x"})], stop_reason="tool_use"),
            FakeMessage(content=[text_block("Did research.\nleads: none")], stop_reason="end_turn")]


@pytest.fixture
def world(db_session, db_engine, settings):
    seed_all(db_session)
    # keep the plan small: only two sectors unmapped
    for s in repo.list_sectors(db_session):
        if s.slug not in ("pets", "home-services"):
            repo.set_sector_status(db_session, s.slug, "mapped", now=NOW)
            s.last_hunted_at = NOW
    db_session.commit()
    gap, _ = repo.propose_gap(db_session, title="Pet sitting marketplace", sector_slug="pets", hypothesis_md="h")
    repo.upsert_fact(db_session, FactIn(claim="Pawshake works in Croatia", entity_type="proven_model",
                                        entity_key="pet-sitting", confidence=0.8, sector_slug="pets",
                                        source_url="https://x"), run_id=None, observed_at=NOW)
    settings.director_review = False
    return {"gap": gap, "factory": make_session_factory(db_engine)}


def _client(gap_id):
    strategist = S.StrategistOutput(assessments=[S.GapAssessment(
        gap_id=gap_id, scores=S.ComponentScores(proof=18, absence=25, demand=12, founder_fit=12, risk_penalty=4),
        presence_level="absent", confidence=0.8, hard_filter_failed="none", reasoning="r",
        field_check_question="Ask a vet in Prizren?", recommended_status="verifying")],
        new_gaps=[], headline="Pets look promising")
    critic = S.CriticOutput(verdicts=[S.CriticVerdict(gap_id=gap_id, strongest_objection="o", kosovo_killer="k",
                                                      risk_penalty=6, confidence=0.7, decision="needs_field_check",
                                                      field_check_question="Ask a vet in Prizren?")])
    return FakeClient([FakeMessage(content=[text_block("{}")], parsed_output=strategist),
                       FakeMessage(content=[text_block("{}")], parsed_output=critic),
                       FakeMessage(content=[text_block("Narrative.")])])


def test_full_day_with_fakes(world, settings):
    calls = []
    script = [_conversation() for _ in range(5)]  # verify, map, map, news, culture (chart-diff uses no runner)
    summary = R.run_once(settings, today=MONDAY, now=NOW, client=_client(world["gap"].id),
                         session_factory=world["factory"], apple_fetch=_chart, play_fetch=_chart,
                         runner_factory=fake_runner_factory(script, calls))
    assert summary.planned == 6 and summary.done == 6 and summary.failed == 0
    assert summary.phase == "foundation" and summary.stopped_reason == "queue empty"
    s = world["factory"]()
    run = repo.last_run(s)
    assert run.status == "done" and run.spent_eur == summary.spent_eur > 0
    assert repo.spent_on(s, MONDAY) == run.spent_eur
    assert [t.status for t in repo.tasks_for_run(s, run.id)] == ["done"] * 6
    gap = repo.get_gap(s, world["gap"].id)
    assert gap.score_total == 18 + 12 + 12 + 12 + (15 - 6) and gap.status == "verifying" and gap.confidence == 0.5
    assert len(repo.open_field_checks(s)) == 1
    assert "What changed" in summary.brief_md and repo.latest_brief(s).markdown == summary.brief_md
    assert repo.latest_journal(s)[0].did_md and "pets" in repo.latest_journal(s)[0].did_md
    metrics = s.query(repo.Scorecard).one().metrics
    assert metrics["days_run"] == 1 and metrics["gaps_by_status"]["verifying"] == 1
    assert all(kw["system"] is calls[0]["system"] for kw in calls)  # frozen prefix across the day
    s.close()


def test_second_run_same_day_plans_nothing_new_and_dry_run_writes_no_tasks(world, settings):
    calls = []
    R.run_once(settings, today=MONDAY, now=NOW, client=_client(world["gap"].id), session_factory=world["factory"],
               apple_fetch=_chart, play_fetch=_chart, runner_factory=fake_runner_factory([_conversation() for _ in range(5)], calls))
    again = R.run_once(settings, today=MONDAY, now=NOW, client=FakeClient([]), session_factory=world["factory"],
                       apple_fetch=_chart, play_fetch=_chart, runner_factory=fake_runner_factory([], calls),
                       dry_run=True)
    assert again.planned == 0 and again.stopped_reason == "dry run"
    s = world["factory"]()
    assert repo.last_run(s).status == "dry-run"
    s.close()


def test_budget_stop_marks_run_and_leaves_queue(world, settings):
    calls = []
    summary = R.run_once(settings, today=MONDAY, now=NOW, client=_client(world["gap"].id),
                         session_factory=world["factory"], apple_fetch=_chart, play_fetch=_chart,
                         runner_factory=fake_runner_factory([_conversation() for _ in range(5)], calls),
                         budget_override=Decimal("0.45"))
    assert summary.planned == 2 and summary.stopped_reason in ("queue empty", "budget")  # 0.40 + 0.05 fit
    s = world["factory"]()
    assert repo.last_run(s).budget_cap_eur == Decimal("0.45")
    s.close()


def test_review_plan_drops_and_reorders(world, settings):
    s = world["factory"]()
    run = repo.start_run(s, day=MONDAY, phase="foundation", budget_cap_eur=Decimal("3"), started_at=NOW)
    t1 = repo.enqueue_task(s, profile="map-sector", payload={"sector": "pets"}, priority=80, run_id=run.id)
    t2 = repo.enqueue_task(s, profile="map-sector", payload={"sector": "home-services"}, priority=80, run_id=run.id)
    t3 = repo.enqueue_task(s, profile="news-scan", payload={}, priority=60, run_id=run.id)
    review = S.DirectorReview(keep_task_ids_in_order=[t3.id, t1.id], dropped=[S.DroppedTask(task_id=t2.id, reason="dup")],
                              note="news first")
    from scout.budget.guard import BudgetGuard
    from scout.llm.gateway import LLM
    llm = LLM(FakeClient([FakeMessage(content=[text_block("{}")], parsed_output=review)]),
              BudgetGuard(s, day=MONDAY, daily_cap_eur=Decimal("3"), run_id=run.id), Decimal("0.92"))
    kept, notes = R.review_plan(llm, [t1, t2, t3], journal_md="")
    s.expire_all()
    assert [t.id for t in kept] == [t3.id, t1.id] and notes == ["dropped map-sector pets=home-services: dup", "news first"]
    assert repo.claim_next_task(s, "w", now=NOW).id == t3.id
    assert s.get(repo.Task, t2.id).status == "skipped"
    s.close()
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `TEST_DATABASE_URL=<url> uv run pytest tests/test_run_once.py -v`
Expected: FAIL with `ImportError: cannot import name 'run'` (and `seed_all` missing until Task 22 — write Task 22's `scout/seeds.py` first if running out of order; the plan's order is 21 then 22, so implement `scout/seeds.py` from Task 22 Step 3 now and finish its CLI in Task 22).

- [ ] **Step 4: Write `scout/director/run.py`**

```python
"""The Director: plan the day, run tasks one at a time, judge, write, remember. Exits when done."""

from __future__ import annotations

import json
import traceback
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import anthropic

from scout.budget.guard import BudgetExceeded, BudgetGuard
from scout.config import Settings
from scout.db import repo
from scout.db.base import make_engine, make_session_factory
from scout.director.planner import PHASE_RULES, load_state, plan_tasks
from scout.editor.brief import write_brief
from scout.extract.extractor import Extractor
from scout.llm.gateway import LLM, LLMError
from scout.sources import apple, play
from scout.sources.askdata import AskDataClient
from scout.sources.places import PlacesClient
from scout.strategy.schemas import DirectorReview
from scout.strategy.strategist import Strategist
from scout.worker.chart_diff import classify_and_record, run_chart_diff
from scout.worker.profiles import PROFILES, build_brief, build_system, journal_markdown
from scout.worker.research import ResearchWorker
from scout.worker.tools import ToolContext

REVIEW_EST = Decimal("0.10")
REVIEW_SYSTEM = ("You review the day's research plan for Kosovo Gap Scout. You may DROP tasks that duplicate "
                 "recent work (see the journal) or REORDER them so the most decision-relevant run first. You may "
                 "not add tasks. Keep every task unless you have a concrete reason.")


@dataclass
class RunSummary:
    run_id: int
    day: date
    phase: str
    planned: int
    done: int
    failed: int
    spent_eur: Decimal
    brief_md: str
    stopped_reason: str


def review_plan(llm: LLM, tasks: list, *, journal_md: str) -> tuple[list, list[str]]:
    """Opus may drop or reorder (never add). Returns (kept tasks in order, notes for the journal)."""
    payload = {"tasks": [{"id": t.id, "profile": t.profile, "payload": t.payload, "priority": t.priority,
                          "est_cost_eur": str(t.est_cost_eur)} for t in tasks], "journal": journal_md}
    res = llm.parse(model="claude-opus-5-5", output_format=DirectorReview, system=REVIEW_SYSTEM,
                    user=json.dumps(payload, sort_keys=True, ensure_ascii=False), max_tokens=1024,
                    effort="medium", est_eur=REVIEW_EST)
    review: DirectorReview = res.parsed
    by_id = {t.id: t for t in tasks}
    notes: list[str] = []
    dropped_ids = set()
    for d in review.dropped:
        t = by_id.get(d.task_id)
        if t is None:
            continue
        dropped_ids.add(t.id)
        t.status = "skipped"
        t.error = f"director: {d.reason}"[:4000]
        target = "=".join(str(v) for v in (t.payload or {}).values() if isinstance(v, str))
        notes.append(f"dropped {t.profile} {target}: {d.reason}")
    kept = [by_id[i] for i in review.keep_task_ids_in_order if i in by_id and i not in dropped_ids]
    kept += [t for t in tasks if t.id not in dropped_ids and t not in kept]  # never lose a task silently
    for rank, t in enumerate(kept):
        t.priority = 100 - rank
    llm.guard.session.commit()
    if review.note.strip():
        notes.append(review.note.strip())
    return kept, notes


def _local_today(now: datetime, tz: str) -> date:
    return now.astimezone(ZoneInfo(tz)).date()


def _gaps_md(session, sector_slug: str | None, gap_id: int | None, now: datetime) -> str:
    if gap_id is not None:
        gap = repo.get_gap(session, gap_id)
        if gap is None:
            return ""
        facts = repo.search_facts(session, gap.title, limit=12, now=now)
        head = (f"- #{gap.id} {gap.title}: status {gap.status}, score {gap.score_total}, confidence "
                f"{gap.confidence:.2f}, presence {gap.presence_level}\n  hypothesis: {gap.hypothesis_md[:500]}\n"
                f"  why not yet: {gap.why_not_yet_md[:300]}")
        return head + "\n" + "\n".join(f"- [{f.confidence:.2f}] {f.claim}" for f in facts)
    gaps = repo.list_gaps(session, statuses=["candidate", "verifying", "verified"],
                          sector_slugs=[sector_slug] if sector_slug else None)[:12]
    return "\n".join(f"- #{g.id} {g.title}: {g.status}, score {g.score_total}, presence {g.presence_level}"
                     for g in gaps)


def run_once(settings: Settings, *, today: date | None = None, now: datetime | None = None,
             budget_override: Decimal | None = None, phase_override: str | None = None, dry_run: bool = False,
             client=None, session_factory=None, places: PlacesClient | None = None,
             askdata: AskDataClient | None = None, apple_fetch=apple.fetch_top_free,
             play_fetch=play.fetch_top_free, runner_factory=None, clock=None, worker_id: str = "director") -> RunSummary:
    clock = clock or (lambda: datetime.now(UTC))
    now = now or clock()
    today = today or _local_today(now, settings.timezone)
    session_factory = session_factory or make_session_factory(make_engine(settings.database_url))
    client = client or anthropic.Anthropic(api_key=settings.anthropic_api_key)
    askdata = askdata or AskDataClient()
    if places is None and settings.google_places_api_key:
        places = PlacesClient(settings.google_places_api_key)
    session = session_factory()
    try:
        phase = phase_override or (repo.get_setting(session, "phase") or {}).get("value") or settings.phase
        if phase not in PHASE_RULES:
            raise ValueError(f"unknown phase {phase!r}")
        cap = Decimal(budget_override) if budget_override is not None else min(PHASE_RULES[phase]["cap"],
                                                                              Decimal(settings.daily_budget_eur))
        run = repo.start_run(session, day=today, phase=phase, budget_cap_eur=cap, started_at=now)
        guard = BudgetGuard(session, day=today, daily_cap_eur=cap, run_id=run.id)
        llm = LLM(client, guard, Decimal(settings.usd_to_eur))
        deadline = now + timedelta(minutes=settings.run_max_minutes)
        journal_md = journal_markdown(repo.latest_journal(session, limit=3))
        notes: list[str] = []

        # 1. plan
        earlier_runs = [r.id for r in repo.runs_on_day(session, today) if r.id != run.id]
        state = load_state(session, today=today, now=now, cap=cap, run_ids_today=earlier_runs)
        queued_before = repo.queued_tasks(session)
        for t in queued_before:  # tasks added by hand or by field-check answers join today's run
            t.run_id = run.id
        session.commit()
        new_tasks = []
        existing_keys = {(t.profile, str((t.payload or {}).get("sector") or (t.payload or {}).get("gap_id") or
                                        (t.payload or {}).get("theme") or "")) for t in queued_before}
        for p in plan_tasks(state, phase):
            key = (p.profile, str(p.payload.get("sector") or p.payload.get("gap_id") or p.payload.get("theme") or ""))
            if key in existing_keys:
                continue
            new_tasks.append(repo.enqueue_task(session, profile=p.profile, payload=p.payload, priority=p.priority,
                                               est_cost_eur=p.est_cost_eur, run_id=run.id))
        planned = queued_before + new_tasks
        if settings.director_review and len(planned) >= 3 and guard.can_afford(REVIEW_EST):
            try:
                planned, review_notes = review_plan(llm, planned, journal_md=journal_md)
                notes += review_notes
            except (LLMError, BudgetExceeded, anthropic.APIError) as e:
                notes.append(f"director review skipped: {type(e).__name__}")
        if dry_run:
            lines = [f"- {t.profile} {t.payload} (priority {t.priority}, est €{t.est_cost_eur})" for t in planned]
            repo.finish_run(session, run, spent_eur=Decimal("0"), tasks_done=0, tasks_failed=0,
                            summary_md="dry run\n" + "\n".join(lines), finished_at=clock(), status="dry-run")
            return RunSummary(run.id, today, phase, len(planned), 0, 0, Decimal("0"), "\n".join(lines), "dry run")

        # 2. execute
        system = build_system(session)
        worker = ResearchWorker(client, llm, guard, system, runner_factory=runner_factory)
        extractor = Extractor(llm)
        done = failed = 0
        chart_report = None
        stopped_reason = "queue empty"
        while True:
            if clock() >= deadline:
                stopped_reason = "time limit"
                break
            task = repo.claim_next_task(session, worker_id, now=clock())
            if task is None:
                break
            try:
                if task.profile == "chart-diff":
                    guard.check(Decimal("0.05"))
                    chart_report = run_chart_diff(session, today, apple_fetch=apple_fetch, play_fetch=play_fetch)
                    n = classify_and_record(session, extractor, chart_report, now=clock(), run_id=run.id)
                    summary_md = (f"snapshots {chart_report.snapshots_saved}; leads {len(chart_report.leads)}; "
                                  f"facts {n}; new in Kosovo: {', '.join(chart_report.new_in_kosovo) or 'none'}")
                    cost = sum((c.cost_eur for c in session.query(repo.Cost).filter_by(task_id=task.id)), Decimal("0"))
                    repo.finish_task(session, task, result_md=summary_md, actual_cost_eur=cost, now=clock())
                else:
                    profile = PROFILES[task.profile]
                    guard.check(profile.est_cost_eur)
                    payload = dict(task.payload or {})
                    sector = payload.get("sector")
                    digest = repo.get_digest(session, f"sector:{sector}") if sector else None
                    if task.profile == "culture":
                        digest = repo.get_digest(session, f"culture:{payload.get('theme')}")
                    if task.profile in ("verify-gap", "deep-dive") and payload.get("gap_id"):
                        gap = repo.get_gap(session, int(payload["gap_id"]))
                        if gap is not None:
                            payload.setdefault("hypothesis", gap.hypothesis_md)
                            payload.setdefault("presence_level", gap.presence_level)
                    brief = build_brief(profile, payload, today, journal_md=journal_md, sector_digest=digest or "",
                                        gaps_md=_gaps_md(session, sector, payload.get("gap_id"), clock()))
                    ctx = ToolContext(session=session, guard=guard, now=clock(), run_id=run.id, task_id=task.id,
                                      places=places, askdata=askdata)
                    outcome = worker.run(task.id, profile, brief, ctx)
                    repo.finish_task(session, task, result_md=outcome.summary_md, actual_cost_eur=outcome.cost_eur,
                                     now=clock())
                    if task.profile == "map-sector" and sector:
                        repo.set_sector_status(session, sector, "mapped", now=clock())
                    if task.profile == "hunt-models" and sector:
                        repo.set_sector_status(session, sector, "hunted", now=clock())
                    if task.profile == "deep-dive" and payload.get("gap_id"):
                        repo.set_gap_test_plan(session, int(payload["gap_id"]), outcome.summary_md)
                        repo.set_setting(session, f"deep-dive-done:{today.replace(day=1).isoformat()}", True)
                    if task.profile == "verify-gap":
                        for line in outcome.summary_md.splitlines():
                            if line.lower().startswith("field-check:") and len(repo.open_field_checks(session)) < 5:
                                repo.add_field_check(session, gap_id=int(payload["gap_id"]),
                                                     question=line.split(":", 1)[1].strip(), why="verify-gap was ambiguous",
                                                     due=today + timedelta(days=7))
                    if outcome.budget_stopped:
                        stopped_reason = "budget"
                        done += 1
                        break
                done += 1
            except BudgetExceeded as e:
                repo.fail_task(session, task, error=f"budget: {e}", now=clock(), requeue=False)
                failed += 1
                stopped_reason = "budget"
                break
            except Exception as e:  # noqa: BLE001 — one bad task must not end the day
                session.rollback()
                repo.fail_task(session, task, error=f"{type(e).__name__}: {e}\n{traceback.format_exc()[-1500:]}",
                               now=clock(), requeue=True)
                failed += 1

        # 3. judge
        changes = []
        strategist = Strategist(llm, session)
        fresh = repo.fresh_facts_since(session, run.started_at, now=clock())
        if fresh or new_tasks:
            try:
                inputs = strategist.collect_inputs(since=run.started_at - timedelta(hours=1), now=clock())
                if inputs.gaps or inputs.facts:
                    output = strategist.assess(inputs, today)
                    critic = strategist.critique(output, inputs, today)
                    applied = strategist.apply(output, critic, now=clock(), run_id=run.id)
                    changes = applied.changes
                    notes.append(f"strategist: {output.headline}; new gaps {applied.new_gaps}; "
                                 f"field checks {applied.field_checks_added}")
            except (LLMError, BudgetExceeded, anthropic.APIError) as e:
                notes.append(f"strategy skipped: {type(e).__name__}: {str(e)[:120]}")

        # 4. write and remember
        spent = guard.spent()
        brief_md = write_brief(session, llm, run, today=today, now=clock(), changes=changes, chart_report=chart_report)
        tasks = repo.tasks_for_run(session, run.id)
        did = "; ".join(f"{t.profile} {(t.payload or {}).get('sector') or (t.payload or {}).get('gap_title') or (t.payload or {}).get('theme') or ''} ({t.status})"
                        for t in tasks) or "nothing"
        learned = "\n".join(f"- {f.claim[:160]}" for f in fresh[:8]) or "- nothing new"
        unmapped = [s.slug for s in repo.list_sectors(session) if s.status == "unmapped"][:3]
        tomorrow = (f"next sectors: {', '.join(unmapped) or 'all mapped'}; open field checks: "
                    f"{len(repo.open_field_checks(session))}; " + "; ".join(notes))
        repo.write_journal(session, run_id=run.id, day=today, did_md=did, learned_md=learned, tomorrow_md=tomorrow)
        gaps = repo.list_gaps(session)
        by_status: dict[str, int] = {}
        for g in gaps:
            by_status[g.status] = by_status.get(g.status, 0) + 1
        top10 = [g.confidence for g in gaps[:10]]
        all_facts = session.query(repo.Fact).count()
        fresh_total = session.query(repo.Fact).filter(repo.Fact.expires_at > clock()).count()
        first = today.replace(day=1)
        metrics = {
            "sectors_mapped": sum(1 for s in repo.list_sectors(session) if s.status != "unmapped"),
            "proven_models": session.query(repo.ProvenModel).count(),
            "gaps_by_status": by_status,
            "avg_confidence_top10": round(sum(top10) / len(top10), 3) if top10 else 0,
            "facts_fresh_ratio": round(fresh_total / all_facts, 3) if all_facts else 0,
            "spend_mtd": str(repo.spent_between(session, first, today)),
            "searches_mtd": sum(int((c.units or {}).get("web_search_requests", 0))
                                for c in session.query(repo.Cost).filter(repo.Cost.day >= first)),
            "field_checks_open": len(repo.open_field_checks(session)),
            "field_checks_answered": session.query(repo.FieldCheck).filter_by(status="answered").count(),
            "days_run": session.query(repo.Run.day).filter(repo.Run.status == "done").distinct().count() + 1,
        }
        repo.save_scorecard(session, day=today, metrics=metrics)
        repo.finish_run(session, run, spent_eur=spent, tasks_done=done, tasks_failed=failed,
                        summary_md=brief_md[:4000], finished_at=clock(), status="done")
        return RunSummary(run.id, today, phase, len(planned), done, failed, spent, brief_md, stopped_reason)
    finally:
        session.close()
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `TEST_DATABASE_URL=<url> uv run pytest tests/test_run_once.py -v`
Expected: 4 PASSED. If `test_full_day_with_fakes` reports `planned == 7`, a culture digest seed is missing: `seed_all` must not write culture digests (only sectors, themes list, sources, country digest), so exactly one `culture` task is planned.

- [ ] **Step 6: Commit**

```bash
uv run ruff check . && uv run ruff format .
git add -A && git commit -m "feat(director): daily run_once with planning, execution, judgement and memory"
```

---

### Task 22: Seeds and CLI

**Files:**
- Create: `scout/seeds.py`, `scout/cli.py`
- Test: `tests/test_cli.py`

**Interfaces:**
- Produces (`seeds.py`): `SECTORS: list[tuple[str, str, str, int]]` (slug, name_en, name_sq, priority — 24 rows from spec Appendix A), `CULTURE_THEMES: list[tuple[str, str]]` (10 rows from Appendix B), `SOURCES: list[dict]`, `COUNTRY_DIGEST_SEED: str`, `seed_all(session) -> dict[str, int]`.
- Produces (`cli.py`): typer `app` with commands `init-db`, `seed`, `run`, `brief`, `status`, `add-task`, `field-check answer`, `chart-diff`, `flag-gap`, `set-phase`.

- [ ] **Step 1: Write the failing tests**

`tests/test_cli.py`:
```python
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from typer.testing import CliRunner

from scout import cli
from scout.db import repo
from scout.seeds import CULTURE_THEMES, SECTORS, seed_all

pytestmark = pytest.mark.db
runner = CliRunner()


@pytest.fixture(autouse=True)
def _wire(db_session, db_engine, settings, monkeypatch):
    from scout.db.base import make_session_factory

    monkeypatch.setattr(cli, "get_settings", lambda: settings)
    monkeypatch.setattr(cli, "session_factory", lambda s: make_session_factory(db_engine))
    yield


def test_seed_is_idempotent(db_session):
    first = seed_all(db_session)
    assert first["sectors"] == len(SECTORS) == 24 and first["themes"] == len(CULTURE_THEMES) == 10
    assert seed_all(db_session)["sectors"] == 0
    assert repo.get_digest(db_session, "country") and not repo.list_digests(db_session, "culture:")
    assert repo.get_sector(db_session, "home-services").priority == 1
    assert repo.get_setting(db_session, "culture_themes") == [slug for slug, _ in CULTURE_THEMES]


def test_cli_seed_add_task_and_status(db_session):
    assert runner.invoke(cli.app, ["seed"]).exit_code == 0
    out = runner.invoke(cli.app, ["add-task", "map-sector", "--sector", "pets"])
    assert out.exit_code == 0 and "queued task #" in out.stdout
    assert repo.queued_tasks(db_session)[0].payload == {"sector": "pets", "sector_name": "Pets"}
    assert runner.invoke(cli.app, ["add-task", "bogus"]).exit_code != 0
    status = runner.invoke(cli.app, ["status"])
    assert status.exit_code == 0 and "spent today" in status.stdout and "queued: 1" in status.stdout


def test_field_check_answer_records_fact_and_requeues_verify(db_session):
    seed_all(db_session)
    gap, _ = repo.propose_gap(db_session, title="Pet sitting", sector_slug="pets")
    fc = repo.add_field_check(db_session, gap_id=gap.id, question="Sitters in Prizren?", why="w",
                              due=datetime.now(UTC).date())
    out = runner.invoke(cli.app, ["field-check", "answer", str(fc.id), "No sitters, only two vets"])
    assert out.exit_code == 0
    fact = repo.search_facts(db_session, "sitters", now=datetime.now(UTC))[0]
    assert fact.confidence == 0.95 and fact.source_name == "founder" and fact.entity_key == f"gap:{gap.id}"
    task = repo.queued_tasks(db_session)[0]
    assert task.profile == "verify-gap" and task.priority == 90 and task.payload["gap_id"] == gap.id
    assert repo.open_field_checks(db_session) == []


def test_flag_gap_and_set_phase(db_session):
    seed_all(db_session)
    gap, _ = repo.propose_gap(db_session, title="Pet sitting", sector_slug="pets")
    assert runner.invoke(cli.app, ["flag-gap", str(gap.id)]).exit_code == 0
    assert repo.get_setting(db_session, "flagged_gaps") == [gap.id]
    assert runner.invoke(cli.app, ["set-phase", "verification"]).exit_code == 0
    assert repo.get_setting(db_session, "phase") == {"value": "verification"}
    assert runner.invoke(cli.app, ["set-phase", "nonsense"]).exit_code != 0


def test_run_dry_run_passes_flags(monkeypatch):
    seen = {}

    def fake_run_once(settings, **kw):
        seen.update(kw)
        from scout.director.run import RunSummary
        return RunSummary(1, kw["today"] or datetime.now(UTC).date(), "foundation", 0, 0, 0, Decimal("0"), "", "dry run")
    monkeypatch.setattr(cli, "run_once", fake_run_once)
    out = runner.invoke(cli.app, ["run", "--budget", "0.50", "--phase", "verification", "--dry-run"])
    assert out.exit_code == 0 and seen["budget_override"] == Decimal("0.50")
    assert seen["phase_override"] == "verification" and seen["dry_run"] is True
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `TEST_DATABASE_URL=<url> uv run pytest tests/test_cli.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'scout.seeds'`

- [ ] **Step 3: Write `scout/seeds.py`**

```python
"""Starting knowledge: the sector taxonomy, culture themes, source registry and a cautious country digest."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from scout.db import repo
from scout.db.models import Source

# (slug, name_en, name_sq, priority) — spec Appendix A
SECTORS: list[tuple[str, str, str, int]] = [
    ("home-services", "Home services (cleaning, repairs, handymen)", "Shërbime për shtëpi", 1),
    ("health-booking", "Health and dental booking", "Rezervime shëndetësore", 1),
    ("tutoring-education", "Tutoring, Matura prep, courses", "Mësim privat dhe kurse", 1),
    ("mobility-transit", "Transit, parking, intercity transport", "Transport dhe parkim", 1),
    ("secondhand-marketplaces", "Second-hand marketplaces (fashion, kids, electronics)", "Tregje të dorës së dytë", 1),
    ("rentals-housing", "Long-term rentals and housing services", "Qira dhe banim", 1),
    ("diaspora-services", "Diaspora-to-family services", "Shërbime për diasporën", 1),
    ("weddings-events", "Weddings and events marketplace", "Dasma dhe evente", 1),
    ("food-grocery-delivery", "Food, grocery and meal-plan delivery", "Ushqim dhe dërgesa", 2),
    ("beauty-wellness", "Beauty and wellness booking", "Bukuri dhe mirëqenie", 2),
    ("fitness-sports", "Fitness, sports and courts", "Fitnes dhe sport", 2),
    ("pets", "Pets (vets, sitting, supplies)", "Kafshë shtëpiake", 2),
    ("car-services", "Car services (repairs, inspection, parts)", "Shërbime për vetura", 2),
    ("parenting-kids", "Parenting, childcare and kids' activities", "Prindër dhe fëmijë", 2),
    ("bureaucracy-helpers", "Bureaucracy and e-Kosova helpers", "Ndihmë për burokraci", 2),
    ("local-travel", "Local travel, weekends, mountains", "Udhëtime lokale", 2),
    ("utilities-household-finance", "Utilities, bills and household money tools", "Fatura dhe financa familjare", 3),
    ("jobs-gigs", "Jobs, gigs and freelancing", "Punë dhe angazhime", 3),
    ("agri-to-consumer", "Farm-to-consumer food", "Nga fshati te konsumatori", 3),
    ("entertainment-media", "Entertainment, tickets, media", "Argëtim dhe media", 3),
    ("legal-consumer", "Consumer legal and notary help", "Ndihmë juridike", 3),
    ("instagram-seller-tools", "Tools for Instagram sellers", "Vegla për shitës në Instagram", 3),
    ("elderly-care", "Elderly care and remote family care", "Kujdes për të moshuarit", 3),
    ("language-ai-consumer", "Albanian-language AI consumer tools", "Vegla AI në shqip", 3),
]

# (slug, name) — spec Appendix B
CULTURE_THEMES: list[tuple[str, str]] = [
    ("payments-and-trust", "Payments and trust"),
    ("diaspora-and-remittances", "Diaspora and remittances"),
    ("family-and-housing", "Family and housing"),
    ("youth-and-work", "Youth and work"),
    ("language-and-media", "Language and media"),
    ("cities-and-mobility", "Cities and mobility"),
    ("calendar-and-seasons", "Calendar and seasons"),
    ("shopping-habits", "Shopping habits"),
    ("bureaucracy-and-state", "Bureaucracy and the state"),
    ("health-and-education", "Health and education"),
]

SOURCES: list[dict] = [
    {"tier": "A", "name": "askdata", "kind": "stats", "base_url": "https://askdata.rks-gov.net/api/v1/en/ASKdata/",
     "ttl_hours": 24 * 180, "cost_per_call_eur": Decimal("0")},
    {"tier": "A", "name": "google-places", "kind": "places", "base_url": "https://places.googleapis.com/v1/places:searchText",
     "ttl_hours": 24 * 30, "cost_per_call_eur": Decimal("0"), "config": {"monthly_quota": 4500}},
    {"tier": "A", "name": "apple-rss", "kind": "app-chart", "base_url": "https://rss.marketingtools.apple.com/api/v2/",
     "ttl_hours": 24 * 7, "cost_per_call_eur": Decimal("0")},
    {"tier": "A", "name": "google-play", "kind": "app-chart", "base_url": "https://play.google.com/store/apps/",
     "ttl_hours": 24 * 7, "cost_per_call_eur": Decimal("0")},
    {"tier": "A", "name": "itunes-search", "kind": "app-search", "base_url": "https://itunes.apple.com/search",
     "ttl_hours": 24 * 30, "cost_per_call_eur": Decimal("0")},
    {"tier": "A", "name": "claude-web-search", "kind": "web", "base_url": None, "ttl_hours": 24 * 30,
     "cost_per_call_eur": Decimal("0.0092")},
    {"tier": "B", "name": "apify-instagram", "kind": "social", "base_url": "https://api.apify.com/", "ttl_hours": 24 * 14,
     "cost_per_call_eur": Decimal("0.002"), "enabled": False},
    {"tier": "B", "name": "meta-ad-library", "kind": "ads", "base_url": "https://www.facebook.com/ads/library/",
     "ttl_hours": 24 * 7, "cost_per_call_eur": Decimal("0.002"), "enabled": False},
    {"tier": "C", "name": "merrjep", "kind": "classifieds", "base_url": "https://www.merrjep.com/", "ttl_hours": 24 * 7,
     "cost_per_call_eur": Decimal("0"), "enabled": False},
    {"tier": "C", "name": "kosovajob", "kind": "jobs", "base_url": "https://kosovajob.com/", "ttl_hours": 24 * 7,
     "cost_per_call_eur": Decimal("0"), "enabled": False},
    {"tier": "D", "name": "founder", "kind": "field", "base_url": None, "ttl_hours": 24 * 365,
     "cost_per_call_eur": Decimal("0")},
]

COUNTRY_DIGEST_SEED = """# Kosovo — starting picture (seed; every number below must be verified and sourced by the scout)

- People: ≈ 1.6 million residents (2024 census, provisional), one of Europe's youngest populations (median age ≈ 30).
  Albanian-speaking majority; Serbian-speaking communities mainly in the north and in enclaves; official languages
  Albanian and Serbian.
- Cities: Prishtinë (capital, ≈ 200k+ in the municipality), Prizren, Pejë, Gjakovë, Mitrovicë, Ferizaj, Gjilan.
  Most consumer apps launch in Prishtina only.
- Money: euro is the currency; cash still dominant in daily shopping, card use growing fast; PayPal cannot
  pay out to Kosovo accounts; Stripe is unavailable; local card acquiring exists through banks and PSPs;
  cash on delivery is normal for e-commerce.
- Diaspora: several hundred thousand Kosovars abroad (Germany, Switzerland, Austria, Scandinavia, US);
  remittances are a major share of GDP; summer (July–August) and New Year bring the diaspora home and drive
  spending on weddings, cars, housing and restaurants.
- Digital life: high household internet and smartphone penetration; Android dominant; Instagram, TikTok,
  Facebook and WhatsApp/Viber are the main channels; many small businesses sell through Instagram DMs;
  e-Kosova portal digitalised many state services.
- Economy: small, service-heavy, large informal sector; wages low by EU standards; unemployment high
  among youth; strong entrepreneurial culture (cafés, car services, construction, ICT outsourcing).
- Known consumer players to treat as incumbents: Wolt (food delivery), Gjirafa (GjirafaMall, Gjirafa50,
  video), Merrjep and other classifieds, KosovaJob, Telegrafi/Koha (media), banks' apps, telecom apps.
"""


def seed_all(session) -> dict[str, int]:
    counts = {"sectors": 0, "themes": 0, "sources": 0, "digests": 0}
    for slug, name_en, name_sq, priority in SECTORS:
        if repo.get_sector(session, slug) is None:
            repo.get_or_create_sector(session, slug, name_en, name_sq, priority=priority)
            counts["sectors"] += 1
    themes = [slug for slug, _ in CULTURE_THEMES]
    if repo.get_setting(session, "culture_themes") != themes:
        repo.set_setting(session, "culture_themes", themes)
        counts["themes"] = len(themes)
    for row in SOURCES:
        if session.query(Source).filter_by(name=row["name"]).first() is None:
            session.add(Source(**row))
            counts["sources"] += 1
    session.commit()
    if repo.get_digest(session, "country") is None:
        repo.set_digest(session, "country", "Kosovo — starting picture", COUNTRY_DIGEST_SEED, now=datetime.now(UTC))
        counts["digests"] += 1
    return counts
```

- [ ] **Step 4: Write `scout/cli.py`**

```python
"""Command-line entry points: `scout <command>`."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import typer
from rich.console import Console
from rich.table import Table

from scout.config import Settings, get_settings
from scout.db import repo
from scout.db.base import make_engine, make_session_factory
from scout.db.repo import FactIn
from scout.director.planner import PHASES
from scout.director.run import run_once
from scout.seeds import seed_all
from scout.worker.profiles import PROFILES

app = typer.Typer(help="Kosovo Gap Scout", no_args_is_help=True)
field_check_app = typer.Typer(help="Founder field checks")
app.add_typer(field_check_app, name="field-check")
console = Console()


def session_factory(settings: Settings):
    return make_session_factory(make_engine(settings.database_url))


@app.command("init-db")
def init_db() -> None:
    """Apply database migrations (alembic upgrade head)."""
    from alembic import command
    from alembic.config import Config

    command.upgrade(Config("alembic.ini"), "head")
    console.print("database at head")


@app.command()
def seed() -> None:
    """Insert sectors, culture themes, sources and the starting country digest."""
    with session_factory(get_settings())() as s:
        console.print(seed_all(s))


@app.command()
def run(budget: float | None = typer.Option(None, help="Override today's cap in EUR"),
        phase: str | None = typer.Option(None, help="foundation | verification | maintenance"),
        dry_run: bool = typer.Option(False, "--dry-run", help="Plan only; run nothing")) -> None:
    """Run today's cycle: plan → research → judge → brief."""
    settings = get_settings()
    summary = run_once(settings, today=None, budget_override=Decimal(str(budget)) if budget is not None else None,
                       phase_override=phase, dry_run=dry_run)
    console.print(f"run #{summary.run_id} {summary.day} phase={summary.phase} planned={summary.planned} "
                  f"done={summary.done} failed={summary.failed} spent=€{summary.spent_eur} ({summary.stopped_reason})")
    console.print(summary.brief_md)


@app.command()
def brief() -> None:
    """Print the latest brief."""
    with session_factory(get_settings())() as s:
        b = repo.latest_brief(s)
        console.print(b.markdown if b else "no brief yet")


@app.command()
def status() -> None:
    """Show spend, queue, top gaps and open field checks."""
    with session_factory(get_settings())() as s:
        today = datetime.now(UTC).date()
        last = repo.last_run(s)
        console.print(f"last run: {last.day if last else '-'} status={last.status if last else '-'}; "
                      f"spent today €{repo.spent_on(s, today)}; month €{repo.spent_between(s, today.replace(day=1), today)}; "
                      f"queued: {len(repo.queued_tasks(s))}")
        table = Table("id", "gap", "status", "score", "conf", "presence")
        for g in repo.list_gaps(s, statuses=["candidate", "verifying", "verified", "parked"])[:10]:
            table.add_row(str(g.id), g.title, g.status, str(g.score_total), f"{g.confidence:.2f}", g.presence_level)
        console.print(table)
        for fc in repo.open_field_checks(s):
            console.print(f"field check #{fc.id}: {fc.question}")


@app.command("add-task")
def add_task(profile: str, sector: str | None = typer.Option(None), gap_id: int | None = typer.Option(None),
             theme: str | None = typer.Option(None), priority: int = typer.Option(70)) -> None:
    """Queue a task for the next run."""
    if profile not in PROFILES and profile != "chart-diff":
        raise typer.BadParameter(f"profile must be one of {', '.join([*PROFILES, 'chart-diff'])}")
    with session_factory(get_settings())() as s:
        payload: dict = {}
        if sector:
            sec = repo.get_sector(s, sector)
            if sec is None:
                raise typer.BadParameter(f"unknown sector {sector}")
            payload = {"sector": sec.slug, "sector_name": sec.name_en}
        if gap_id is not None:
            gap = repo.get_gap(s, gap_id)
            if gap is None:
                raise typer.BadParameter(f"unknown gap {gap_id}")
            sec = next((x for x in repo.list_sectors(s) if x.id == gap.sector_id), None)
            payload = {"gap_id": gap.id, "gap_title": gap.title, "sector": sec.slug if sec else ""}
        if theme:
            payload = {"theme": theme, "theme_name": theme.replace("-", " ")}
        est = PROFILES[profile].est_cost_eur if profile in PROFILES else Decimal("0.05")
        t = repo.enqueue_task(s, profile=profile, payload=payload, priority=priority, est_cost_eur=est)
        console.print(f"queued task #{t.id} {profile} {payload}")


@field_check_app.command("answer")
def field_check_answer(check_id: int, answer: str) -> None:
    """Record the founder's answer as a high-confidence fact and re-queue verification of the gap."""
    with session_factory(get_settings())() as s:
        fc = s.get(repo.FieldCheck, check_id)
        if fc is None or fc.status != "open":
            raise typer.BadParameter(f"no open field check #{check_id}")
        now = datetime.now(UTC)
        gap = repo.get_gap(s, fc.gap_id) if fc.gap_id else None
        sec = next((x for x in repo.list_sectors(s) if gap and x.id == gap.sector_id), None)
        repo.upsert_fact(s, FactIn(claim=f"Founder field check — Q: {fc.question} A: {answer}", entity_type="gap",
                                   entity_key=f"gap:{fc.gap_id}" if fc.gap_id else "general", confidence=0.95,
                                   sector_slug=sec.slug if sec else None, ttl_days=180, source_name="founder"),
                         run_id=None, observed_at=now)
        repo.answer_field_check(s, fc, answer=answer, answered_at=now)
        if gap is not None:
            repo.enqueue_task(s, profile="verify-gap", priority=90, est_cost_eur=PROFILES["verify-gap"].est_cost_eur,
                              payload={"gap_id": gap.id, "gap_title": gap.title, "sector": sec.slug if sec else ""})
        console.print(f"answered #{check_id}; verify-gap queued" if gap else f"answered #{check_id}")


@app.command("chart-diff")
def chart_diff_cmd() -> None:
    """Run the app-chart diff now and print the leads (no model call)."""
    from scout.worker.chart_diff import run_chart_diff

    with session_factory(get_settings())() as s:
        report = run_chart_diff(s, datetime.now(UTC).date())
        for lead in report.leads:
            console.print(f"{lead.store} {lead.app_key} {lead.name} — {','.join(lead.countries)} (best rank {lead.best_rank})")
        console.print(f"snapshots {report.snapshots_saved}; errors {report.errors}")


@app.command("flag-gap")
def flag_gap(gap_id: int, unflag: bool = typer.Option(False, "--unflag")) -> None:
    """Mark a gap as founder-flagged: it is verified first and in maintenance phase."""
    with session_factory(get_settings())() as s:
        if repo.get_gap(s, gap_id) is None:
            raise typer.BadParameter(f"unknown gap {gap_id}")
        flagged = list(repo.get_setting(s, "flagged_gaps", []) or [])
        flagged = [g for g in flagged if g != gap_id] if unflag else sorted(set(flagged) | {gap_id})
        repo.set_setting(s, "flagged_gaps", flagged)
        console.print(f"flagged gaps: {flagged}")


@app.command("set-phase")
def set_phase(phase: str) -> None:
    """Switch phase: foundation | verification | maintenance."""
    if phase not in PHASES:
        raise typer.BadParameter(f"phase must be one of {', '.join(PHASES)}")
    with session_factory(get_settings())() as s:
        repo.set_setting(s, "phase", {"value": phase})
        console.print(f"phase = {phase}")
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `TEST_DATABASE_URL=<url> uv run pytest tests/test_cli.py tests/test_run_once.py -v`
Expected: 9 PASSED

- [ ] **Step 6: Run the whole suite, lint, commit**

```bash
TEST_DATABASE_URL=<url> uv run pytest -q
uv run ruff check . && uv run ruff format .
git add -A && git commit -m "feat(cli): seeds and command-line entry points"
```

---

### Task 23: Deployment to Render + Neon and the first live runs

**Files:**
- Create: `render.yaml`, `tests/test_live.py`
- Modify: `README.md` (deployment section)

**Interfaces:** none new — this task wires the service and proves the live assumptions (spec B19) with network-marked tests.

- [ ] **Step 1: Write `render.yaml`**

```yaml
services:
  - type: cron
    name: kosovo-gap-scout
    runtime: python
    plan: starter
    schedule: "0 6 * * *"          # 06:00 UTC = 08:00 Kosovo in winter; brief ready before work
    buildCommand: pip install uv && uv sync --frozen --no-dev
    startCommand: uv run scout run
    envVars:
      - key: PYTHON_VERSION
        value: "3.12"
      - key: ANTHROPIC_API_KEY
        sync: false
      - key: DATABASE_URL
        sync: false
      - key: GOOGLE_PLACES_API_KEY
        sync: false
      - key: APIFY_TOKEN
        sync: false
      - key: SCOUT_PHASE
        value: foundation
      - key: SCOUT_DAILY_BUDGET_EUR
        value: "3.00"
      - key: SCOUT_RUN_MAX_MINUTES
        value: "50"
      - key: SCOUT_TIMEZONE
        value: Europe/Belgrade
      - key: SCOUT_DIRECTOR_REVIEW
        value: "true"
```

- [ ] **Step 2: Write the live tests (run by hand, never in CI)**

`tests/test_live.py`:
```python
"""Live checks against real services. Run by hand: uv run pytest tests/test_live.py -m network -v"""

import os
from decimal import Decimal

import pytest

pytestmark = pytest.mark.network


@pytest.fixture
def client():
    import anthropic

    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        pytest.skip("ANTHROPIC_API_KEY not set")
    return anthropic.Anthropic(api_key=key)


def test_prompt_cache_hits_on_second_call(client):
    from scout.budget.pricing import usage_units

    filler = "Kosovo Gap Scout rules. " * 400  # ≈ 2k tokens, above the minimum cacheable prefix
    system = [{"type": "text", "text": filler, "cache_control": {"type": "ephemeral"}}]
    kwargs = dict(model="claude-haiku-5-5", max_tokens=20, system=system,
                  messages=[{"role": "user", "content": "Reply with the single word: ok"}],
                  output_config={"effort": "low"})
    first = client.messages.create(**kwargs)
    second = client.messages.create(**kwargs)
    assert usage_units(first.usage)["cache_write_tokens"] > 0 or usage_units(first.usage)["cache_read_tokens"] > 0
    assert usage_units(second.usage)["cache_read_tokens"] > 0


def test_places_region_code_xk(client):
    from scout.sources.places import PlacesClient

    key = os.environ.get("GOOGLE_PLACES_API_KEY")
    if not key:
        pytest.skip("GOOGLE_PLACES_API_KEY not set")
    res = PlacesClient(key).text_search("dentist Prizren")
    assert res.count > 0 and any("Prizren" in p.address for p in res.places)


def test_tool_runner_accepts_system_and_effort(client):
    """Spec B19 #3: tool_runner takes system=, max_iterations=, output_config= on anthropic 1.x."""
    from anthropic import beta_tool

    @beta_tool
    def ping(word: str) -> str:
        """Echo a word.

        Args:
            word: The word to echo.
        """
        return word

    runner = client.beta.messages.tool_runner(
        model="claude-haiku-5-5", max_tokens=200, system="Use the ping tool once with the word hello, then stop.",
        tools=[ping], messages=[{"role": "user", "content": "go"}], max_iterations=3,
        output_config={"effort": "low"})
    last = runner.until_done()
    assert last.stop_reason in ("end_turn", "tool_use")
    assert Decimal(last.usage.input_tokens) > 0
```

- [ ] **Step 3: Provision Neon and Render (manual checklist — tick each)**

1. Neon: create project `kosovo-gap-scout` (region EU), database `scout`; copy the pooled connection string into `.env` as `DATABASE_URL`; create branch `test` and copy its string as `TEST_DATABASE_URL`.
2. Locally: `uv run scout init-db && uv run scout seed`, then `uv run pytest tests/test_live.py -m network -v` with the real keys — all three pass (the Places test proves `regionCode: "XK"`; if it fails with a 400, the fallback in `PlacesClient.text_search` handles it: record the outcome in `README.md`).
3. Google Cloud: enable "Places API (New)", create an API key restricted to that API; set `GOOGLE_PLACES_API_KEY`.
4. Anthropic Console: create a dedicated key `kosovo-gap-scout` under the personal account; set a **monthly spend limit of $40** in the console; set `ANTHROPIC_API_KEY`.
5. GitHub: create a private repo, `git remote add origin … && git push -u origin main`.
6. Render: "New → Blueprint" from the repo; fill the `sync: false` env vars; deploy. Trigger the cron once by hand ("Trigger run"); watch logs for `run #1`.
7. First three live runs with a reduced cap: in Render set `SCOUT_DAILY_BUDGET_EUR=1.00` for days 1–3, confirm `scout status` spend matches the Anthropic console within 10 %, then raise to `3.00`.
8. Add to the calendar: Sunday 10:00 "scout: answer field checks + read the deep-dive"; first of the month "scout: compare console bill with the Costs scorecard".

- [ ] **Step 4: Update `README.md` with the deployment section**

Append:
```markdown
## Deployment (Render cron + Neon)
- Blueprint: `render.yaml` (cron `0 6 * * *`, `uv run scout run`).
- Secrets live only in Render env vars and `.env` (never committed).
- First-run ritual: `scout init-db`, `scout seed`, `scout run --budget 1.00`, read `scout brief`.
- Daily: read the brief (10 min). Sunday: `scout field-check answer <id> "<text>"` for each open check.
- Phase changes: `scout set-phase verification` (2026-11-16), `scout set-phase maintenance` (2026-12-14).
- Source notes: record here any live deviation found by `tests/test_live.py` (Places region code, Play chart HTML).
```

- [ ] **Step 5: Commit and tag the milestone**

```bash
uv run ruff check . && uv run ruff format .
git add -A && git commit -m "chore: render blueprint, live checks and deployment notes"
git tag m1-engine
```

---

## After Milestone 1 — what the next plans cover

Each later milestone gets its own plan document (same format) written at the start of that milestone; the scope is fixed here so the M1 code leaves the right seams.

**M2 — Dashboard + social eyes (build Sat 2026-10-24 and 2026-10-31; live 2026-11-01).** Second Render service (web): FastAPI + Jinja2 + HTMX, single-user cookie auth from `DASHBOARD_TOKEN`; pages Today, Gaps (Verify / Park / Kill / Choose as finalist), Field checks (answer form → `FactIn(... source_name="founder", confidence=0.95)` → `enqueue_task("verify-gap", priority=90)`), Pipeline (retry, add task), Knowledge (digest edit → journal), Journal, Costs, Ask (Sonnet 5.5 over `kb_search` read-only, ≤ €0.20), Settings. Tier B via `apify-client`: `apify/instagram-scraper` (hashtag + place, public posts, business profiles only), Facebook Pages scraper, Meta Ad Library (country XK) into the `ads` table; a `social-scan` profile (Sonnet, est €0.25) gets `instagram_search` and `ad_library_search` tools added to `TOOL_NAMES`; the presence-check brief gains step 4 (social); `BusinessProfile` and `AdSignal` extraction schemas; Apify spend recorded as `CostRecord(kind="apify", ...)` from actor run stats.

**M3 — Batches + source health (Sat 2026-11-07; live 2026-11-15).** `Extractor.submit_batch(items)` / `collect_batch(batch_id)` with `client.messages.batches.create(requests=[Request(custom_id=..., params=MessageCreateParamsNonStreaming(...))])`, `batches.retrieve(id).processing_status == "ended"`, `batches.results(id)`; Director two-stage (`scout run --stage submit` at 06:00, `--stage collect` at 06:45 as a second cron); `sources.last_ok_at/failure_count` updated by every source call, with a brief "Source health" line per degraded source; `scout costs --reconcile` comparing the ledger with the console CSV export.

**M4 — Tier C crawlers (Phase 2; live by 2026-12-13).** `crawlee[playwright]>=1.7` crawlers for Merrjep, Gjirafa50, KosovaJob, news sites and ARBK (JS app), honouring robots.txt and 1 request/2 s; `ListingStats` extraction schema; a `market-scan` profile that reads listing counts and price bands into facts (`entity_type="stat"`); ARBK registration-count facts per sector as a demand signal.

## Self-review notes (done while writing)

- Spec coverage: B1–B10, B12–B17 (M1 rows) and A3's rubric are implemented by Tasks 1–23; B11 and Tier B/C sources are deferred to M2–M4 as the spec says. `kb_write_digest` was added to the B5 tool list (needed by B5's map-sector/culture purposes and B13).
- Placeholder scan: no TBD/TODO/"similar to Task"; every code step has its code.
- Type consistency: `FactIn`, `CostRecord`, `ChartEntryIn`, `ToolContext`, `Profile`, `TaskOutcome`, `ScoreResult`, `StrategistOutput`, `CriticOutput`, `DirectorReview`, `GapChange`, `PlannedTask`, `PlannerState`, `RunSummary` are used with the same names and fields across tasks; repo functions are called with the keyword signatures declared in Tasks 4–5.
- Review Focus coverage: 1 → Task 17 `test_absence_capped_without_presence_check` (+ Task 18 apply test); 2 → Task 14 `test_worker_stops_when_budget_tight`; 3 → Task 4 `test_upsert_fact_refreshes_same_claim`, `test_propose_gap_dedupes_by_title`; 4 → Task 6 `test_spent_uses_explicit_day`; 5 → Task 14 `test_worker_restarts_on_pause_turn`, `test_worker_reports_max_tokens`; 6 → Task 1 `test_normalize_db_url_keeps_query`; 7 → Task 16 `test_chart_diff_never_mixes_stores`.
