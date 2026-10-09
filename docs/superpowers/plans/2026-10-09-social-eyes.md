# Social Eyes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the scout see Kosovo's Instagram shops, Meta ads and Kosovo websites at €0 extra a month, and feed what it finds into the presence check and the demand score.

**Architecture:** Three new tools in the existing research worker:
- `instagram_search` and `ad_library_search` call Apify actors through a small REST client.
- `kosovo_site_crawl` renders allowlisted Kosovo pages with Crawl4AI.

A social guard enforces all paid-call limits in code: the score gate, one call per tool per task, the monthly credit cap and the cache. Results are reduced to privacy-safe summaries before anything is stored. A weekly `ads-sweep` task reads the Ad Library for all of Kosovo.

**Tech Stack:** Python 3.12, httpx (Apify REST API), Crawl4AI (optional extra `crawl`), SQLAlchemy 2 + Alembic, FastAPI/Jinja2, pytest.

**Spec:** `docs/superpowers/specs/2026-10-09-social-eyes-design.md`

## Global Constraints

- €0 extra a month: Apify free credit only; stop at `SCOUT_APIFY_MONTHLY_USD` (default 4.50) per calendar month of the run's Kosovo day.
- Apify cost is free credit: record it as `kind="apify"` with the USD amount in `units["usd"]` and `cost_eur = 0`, so it never uses the daily Claude budget (same pattern as the free Places quota).
- Paid social calls: only in `verify-gap` for a gap with `score_total >= 60` or flagged by the founder; or in `ads-sweep` (Ad Library only).
- Per task: 1 `instagram_search` + 1 `ad_library_search`. Cache hits are free and do not count.
- Results per call: ≤ 30 Instagram accounts, ≤ 50 ads, ≤ 300 ads in the sweep. Actor timeout: 120 s.
- Cache: 30 days for Instagram, 14 days for ads.
- Crawl: allowlisted domains only, ≤ 20 pages per task, ≥ 2 s between pages, robots.txt obeyed.
- Privacy: keep public business accounts only; reduce comments to counts; never store commenter names or comment text.
- No `APIFY_TOKEN` → the paid tools are not offered and `ads-sweep` is not planned. No Crawl4AI installed → the crawl tool is not offered.
- Code style: ruff, line length 100. No narrative comments. Do not commit; the founder commits. Work on the current branch (no worktrees).
- Tests: write the tests listed in each task (the approved spec asks for them). Run only that task's test files, never the full suite. DB tests need `TEST_DATABASE_URL=postgresql://scout:scout@localhost:55432/scout_test`. Never run `-m network`.

## Review Focus

1. **Odd Apify item shapes.** Missing keys, `None` values or non-list fields must not crash the normalisers; they return fewer records instead. Tested in Task 3.
2. **Oversized results.** If Apify returns more items than asked, only `max_items` are kept and stored. Tested in Task 5.
3. **Render failures.** If Crawl4AI raises any error, the page is skipped and counted as a source failure, never a task error. Tested in Task 5.
4. **Old facts without a `value`.** A `social` fact with `value=None` must not break the gap page. Tested in Task 7.
5. **Very long or empty queries.** A 500-character query works (the cache key is trimmed); an empty query is refused outside the sweep. Tested in Task 5.

---

### Task 1: Data layer

**Files:**
- Modify: `scout/db/models.py` (add `Ad`, `SocialCache`)
- Create: `alembic/versions/3f6b2c1d9a7e_social_eyes.py`
- Modify: `scout/db/repo.py` (imports, new functions at the end of the costs section)
- Modify: `scout/config.py` (add `apify_monthly_usd`)
- Modify: `scout/seeds.py` (add the `kosovo-sites` source row)
- Modify: `scout/worker/tools.py:21-41` (`FACT_ENTITY_TYPES`, `PRESENCE_LEVELS`)
- Modify: `scout/strategy/schemas.py:9-11`, `scout/strategy/rubric.py:8-15,29-30`, `scout/web/ui.py:67-83`
- Test: `tests/test_repo_social.py` (create), `tests/test_alembic_env.py` (add one test)

**Interfaces:**
- Produces:
  - `repo.apify_usd_in_month(session, day: date) -> Decimal`
  - `repo.get_social_cache(session, source: str, query_key: str, *, now: datetime, max_age_days: int) -> SocialCache | None`
  - `repo.put_social_cache(session, source: str, query_key: str, items: dict, *, cost_usd: Decimal, now: datetime) -> SocialCache`
  - `repo.upsert_ads(session, ads: list[dict], *, gap_id: int | None, sector_slug: str | None, now: datetime) -> int`
  - `repo.ads_for_gap(session, gap_id: int, limit: int = 20) -> list[Ad]`
  - `repo.social_facts_for_gap(session, gap_id: int, *, now: datetime) -> list[Fact]`
  - `repo.mark_source(session, name: str, *, ok: bool, now: datetime) -> None`
  - `Settings.apify_monthly_usd: Decimal`
  - Presence level `"instagram-only"`; fact types `"social"` and `"ad_signal"`.
  - The ad dict that `upsert_ads` takes has these keys: `ad_archive_id, page_name, page_url, ad_text, platforms, first_seen, last_seen, is_active, is_foreign, link_url`. `first_seen` and `last_seen` are ISO date strings or `None`. Task 3's `social.ads_summary` produces this shape.

- [ ] **Step 1: Add the models**

In `scout/db/models.py`, append:

```python
class Ad(Base):
    __tablename__ = "ads"
    id: Mapped[int] = mapped_column(primary_key=True)
    ad_archive_id: Mapped[str] = mapped_column(String(40), unique=True)
    page_name: Mapped[str] = mapped_column(String(200), default="")
    page_url: Mapped[str | None] = mapped_column(Text)
    ad_text: Mapped[str] = mapped_column(Text, default="")
    platforms: Mapped[list] = mapped_column(JSONType, default=list)
    first_seen: Mapped[date | None] = mapped_column(Date)
    last_seen: Mapped[date | None] = mapped_column(Date)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_foreign: Mapped[bool | None] = mapped_column(Boolean)
    sector_slug: Mapped[str | None] = mapped_column(String(80))
    gap_id: Mapped[int | None] = mapped_column(ForeignKey("gaps.id"))
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    raw: Mapped[dict | None] = mapped_column(JSONType)


class SocialCache(Base):
    __tablename__ = "social_cache"
    __table_args__ = (UniqueConstraint("source", "query_key", name="ux_social_cache_query"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String(20))
    query_key: Mapped[str] = mapped_column(String(320))
    items: Mapped[dict] = mapped_column(JSONType, default=dict)
    cost_usd: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0"))
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
```

- [ ] **Step 2: Add the migration**

Create `alembic/versions/3f6b2c1d9a7e_social_eyes.py`:

```python
"""social eyes: ads and social_cache

Revision ID: 3f6b2c1d9a7e
Revises: e5b79c74a1a4
Create Date: 2026-10-09 18:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "3f6b2c1d9a7e"
down_revision: Union[str, Sequence[str], None] = "e5b79c74a1a4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

JSON = sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql")


def upgrade() -> None:
    op.create_table(
        "ads",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("ad_archive_id", sa.String(length=40), nullable=False),
        sa.Column("page_name", sa.String(length=200), nullable=False),
        sa.Column("page_url", sa.Text(), nullable=True),
        sa.Column("ad_text", sa.Text(), nullable=False),
        sa.Column("platforms", JSON, nullable=False),
        sa.Column("first_seen", sa.Date(), nullable=True),
        sa.Column("last_seen", sa.Date(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("is_foreign", sa.Boolean(), nullable=True),
        sa.Column("sector_slug", sa.String(length=80), nullable=True),
        sa.Column("gap_id", sa.Integer(), nullable=True),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("raw", JSON, nullable=True),
        sa.ForeignKeyConstraint(["gap_id"], ["gaps.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("ad_archive_id"),
    )
    op.create_table(
        "social_cache",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(length=20), nullable=False),
        sa.Column("query_key", sa.String(length=320), nullable=False),
        sa.Column("items", JSON, nullable=False),
        sa.Column("cost_usd", sa.Numeric(precision=12, scale=6), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source", "query_key", name="ux_social_cache_query"),
    )


def downgrade() -> None:
    op.drop_table("social_cache")
    op.drop_table("ads")
```

- [ ] **Step 3: Add the repo functions**

In `scout/db/repo.py`, add `Ad`, `SocialCache` and `Source` to the `from scout.db.models import (...)` list, keeping it alphabetical. Then add these functions right after `places_calls_in_month`:

```python
def apify_usd_in_month(session: Session, day: date) -> Decimal:
    start = day.replace(day=1)
    rows = session.scalars(
        select(Cost).where(Cost.kind == "apify", Cost.day >= start, Cost.day <= day)
    )
    return sum((Decimal(str((c.units or {}).get("usd", "0"))) for c in rows), Decimal("0"))


def get_social_cache(
    session: Session, source: str, query_key: str, *, now: datetime, max_age_days: int
) -> SocialCache | None:
    row = session.scalars(
        select(SocialCache).where(SocialCache.source == source, SocialCache.query_key == query_key)
    ).first()
    if row is None or row.fetched_at <= now - timedelta(days=max_age_days):
        return None
    return row


def put_social_cache(
    session: Session,
    source: str,
    query_key: str,
    items: dict,
    *,
    cost_usd: Decimal,
    now: datetime,
) -> SocialCache:
    row = session.scalars(
        select(SocialCache).where(SocialCache.source == source, SocialCache.query_key == query_key)
    ).first()
    if row is None:
        row = SocialCache(source=source, query_key=query_key)
        session.add(row)
    row.items, row.cost_usd, row.fetched_at = items, cost_usd, now
    session.commit()
    return row


def _iso_date(value: str | None) -> date | None:
    return date.fromisoformat(value) if value else None


def upsert_ads(
    session: Session,
    ads: list[dict],
    *,
    gap_id: int | None,
    sector_slug: str | None,
    now: datetime,
) -> int:
    for a in ads:
        row = session.scalars(select(Ad).where(Ad.ad_archive_id == a["ad_archive_id"])).first()
        if row is None:
            row = Ad(ad_archive_id=a["ad_archive_id"])
            session.add(row)
        last_seen = _iso_date(a.get("last_seen"))
        row.page_name = (a.get("page_name") or "")[:200]
        row.page_url = a.get("page_url")
        row.ad_text = a.get("ad_text") or ""
        row.platforms = list(a.get("platforms") or [])
        row.first_seen = _iso_date(a.get("first_seen")) or row.first_seen
        row.last_seen = max(d for d in (row.last_seen, last_seen) if d) if (
            row.last_seen or last_seen
        ) else None
        row.is_active = bool(a.get("is_active"))
        row.is_foreign = a.get("is_foreign")
        row.gap_id = gap_id or row.gap_id
        row.sector_slug = sector_slug or row.sector_slug
        row.fetched_at = now
        row.raw = {"link_url": a.get("link_url")}
    session.commit()
    return len(ads)


def ads_for_gap(session: Session, gap_id: int, limit: int = 20) -> list[Ad]:
    return list(
        session.scalars(
            select(Ad)
            .where(Ad.gap_id == gap_id)
            .order_by(Ad.is_active.desc(), Ad.first_seen.asc().nulls_last(), Ad.id)
            .limit(limit)
        )
    )


def social_facts_for_gap(session: Session, gap_id: int, *, now: datetime) -> list[Fact]:
    return list(
        session.scalars(
            select(Fact)
            .where(
                Fact.entity_type.in_(("social", "ad_signal")),
                Fact.entity_key == f"gap:{gap_id}",
                Fact.expires_at > now,
            )
            .order_by(Fact.observed_at.desc(), Fact.id.desc())
        )
    )


def mark_source(session: Session, name: str, *, ok: bool, now: datetime) -> None:
    src = session.scalars(select(Source).where(Source.name == name)).first()
    if src is None:
        return
    if ok:
        src.last_ok_at = now
        src.enabled = True
    else:
        src.failure_count = (src.failure_count or 0) + 1
    session.commit()
```

- [ ] **Step 4: Settings, seed row, vocabularies**

`scout/config.py`: add the field after `usd_to_eur`:

```python
    apify_monthly_usd: Decimal = Decimal("4.50")
```

`scout/seeds.py`: add this row to `SOURCES`, right after the `kosovajob` row:

```python
    {
        "tier": "C",
        "name": "kosovo-sites",
        "kind": "web",
        "base_url": None,
        "ttl_hours": 24 * 7,
        "cost_per_call_eur": Decimal("0"),
        "enabled": False,
    },
```

`scout/worker/tools.py`:
- Add `"social"` and `"ad_signal"` at the end of `FACT_ENTITY_TYPES`.
- Add `"instagram-only"` to `PRESENCE_LEVELS`, before `"unknown"`.

`scout/strategy/schemas.py`: update the literal:

```python
PresenceLevel = Literal[
    "absent",
    "exists-but-poor",
    "prishtina-only",
    "offline-only",
    "instagram-only",
    "decent",
    "unknown",
]
```

`scout/strategy/rubric.py`:
- Add `"instagram-only": 18,` to `PRESENCE_CAP`, after `"offline-only"`.
- In `RUBRIC_TEXT`, change `prishtina-only 12, offline-only 10, decent 0, unknown 12` to `prishtina-only 12, offline-only 10, instagram-only 18, decent 0, unknown 12`.

`scout/web/ui.py`:
- Add `"instagram-only": "Only on Instagram (informal)",` to `PRESENCE`, before `"unknown"`.
- Add `"ads-sweep": "Weekly ads sweep",` to `PROFILE_NAMES`.

- [ ] **Step 5: Write the tests**

Create `tests/test_repo_social.py`:

```python
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest

from scout.db import repo
from scout.db.models import Source
from scout.db.repo import CostRecord, FactIn

pytestmark = pytest.mark.db
NOW = datetime(2026, 10, 19, 6, 0, tzinfo=UTC)


def _ad(archive_id="111", **over):
    base = {
        "ad_archive_id": archive_id,
        "page_name": "Torta Shop",
        "page_url": "https://facebook.com/tortashop",
        "ad_text": "Porosit torten",
        "platforms": ["facebook"],
        "first_seen": "2026-09-01",
        "last_seen": "2026-10-10",
        "is_active": True,
        "is_foreign": False,
        "link_url": "https://tortashop.rks",
    }
    return base | over


def test_apify_usd_counts_only_apify_rows_of_the_month(db_session):
    for day, kind, usd in (
        (date(2026, 9, 30), "apify", "1.00"),
        (date(2026, 10, 1), "apify", "0.25"),
        (date(2026, 10, 18), "apify", "0.50"),
        (date(2026, 10, 18), "places", "9.00"),
    ):
        repo.record_cost(
            db_session,
            CostRecord(kind, "x", None, {"usd": usd}, Decimal("0")),
            day=day,
            run_id=None,
        )
    assert repo.apify_usd_in_month(db_session, date(2026, 10, 19)) == Decimal("0.75")


def test_social_cache_round_trip_and_expiry(db_session):
    repo.put_social_cache(
        db_session, "instagram", "torta|30", {"shops": []}, cost_usd=Decimal("0.05"), now=NOW
    )
    hit = repo.get_social_cache(
        db_session, "instagram", "torta|30", now=NOW + timedelta(days=29), max_age_days=30
    )
    assert hit is not None and hit.items == {"shops": []}
    assert (
        repo.get_social_cache(
            db_session, "instagram", "torta|30", now=NOW + timedelta(days=31), max_age_days=30
        )
        is None
    )
    repo.put_social_cache(
        db_session, "instagram", "torta|30", {"shops": [1]}, cost_usd=Decimal("0"), now=NOW
    )
    assert repo.get_social_cache(
        db_session, "instagram", "torta|30", now=NOW, max_age_days=30
    ).items == {"shops": [1]}


def test_upsert_ads_updates_by_archive_id(db_session):
    repo.get_or_create_sector(db_session, "food", "Food")
    gap, _ = repo.propose_gap(
        db_session,
        title="Cake delivery",
        sector_slug="food",
        proven_model_slug=None,
        hypothesis_md="",
        presence_level="unknown",
        why_not_yet_md="",
        run_id=None,
    )
    repo.upsert_ads(db_session, [_ad()], gap_id=gap.id, sector_slug="food", now=NOW)
    repo.upsert_ads(
        db_session, [_ad(last_seen="2026-10-19", is_active=False)], gap_id=None, sector_slug=None,
        now=NOW,
    )
    ads = repo.ads_for_gap(db_session, gap.id)
    assert len(ads) == 1
    assert ads[0].last_seen == date(2026, 10, 19) and ads[0].is_active is False
    assert ads[0].gap_id == gap.id and ads[0].sector_slug == "food"
    assert ads[0].raw == {"link_url": "https://tortashop.rks"}


def test_social_facts_for_gap_only_fresh_social_types(db_session):
    for etype, key in (("social", "gap:7"), ("ad_signal", "gap:7"), ("gap", "gap:7"), ("social", "gap:8")):
        repo.upsert_fact(
            db_session,
            FactIn(claim=f"{etype} {key}", entity_type=etype, entity_key=key, confidence=0.7),
            run_id=None,
            observed_at=NOW,
        )
    facts = repo.social_facts_for_gap(db_session, 7, now=NOW)
    assert sorted(f.entity_type for f in facts) == ["ad_signal", "social"]


def test_mark_source(db_session):
    db_session.add(Source(tier="B", name="apify-instagram", kind="social", enabled=False))
    db_session.commit()
    repo.mark_source(db_session, "apify-instagram", ok=False, now=NOW)
    repo.mark_source(db_session, "apify-instagram", ok=True, now=NOW)
    repo.mark_source(db_session, "no-such-source", ok=True, now=NOW)
    src = db_session.query(Source).filter_by(name="apify-instagram").one()
    assert src.failure_count == 1 and src.enabled is True and src.last_ok_at == NOW
```

Add to `tests/test_alembic_env.py`:

```python
def test_social_tables_are_in_the_migrations(percent_url, capsys):
    command.upgrade(Config(str(ROOT / "alembic.ini")), "head", sql=True)
    out = capsys.readouterr().out
    assert "CREATE TABLE ads" in out and "CREATE TABLE social_cache" in out
```

- [ ] **Step 6: Run the tests and lint**

Run: `TEST_DATABASE_URL=postgresql://scout:scout@localhost:55432/scout_test uv run pytest -q tests/test_repo_social.py tests/test_alembic_env.py tests/test_seeds.py tests/test_rubric.py tests/test_web_ui.py`
Expected: all pass.

Run: `uv run ruff format scout/db scout/config.py scout/seeds.py scout/worker/tools.py scout/strategy scout/web/ui.py tests/test_repo_social.py tests/test_alembic_env.py && uv run ruff check scout tests`
Expected: no errors. (`ruff format` may rewrap the long tuple in the test; that is fine.)

---

### Task 2: Apify client

**Files:**
- Create: `scout/sources/apify.py`
- Test: `tests/test_apify.py`

**Interfaces:**
- Produces:
  - `INSTAGRAM_ACTOR = "apify~instagram-scraper"` and `ADS_ACTOR = "apify~facebook-ads-scraper"`
  - `ActorResult(items: list[dict], cost_usd: Decimal, run_id: str)`
  - `ApifyError(message, cost_usd: Decimal = 0)`, which has a `.cost_usd` attribute
  - `ApifyClient(token, http=None, timeout_s=120).run(actor: str, actor_input: dict, *, max_items: int) -> ActorResult`
  - `ad_library_url(query: str, country: str = "XK") -> str`

- [ ] **Step 1: Write the client**

Create `scout/sources/apify.py`:

```python
"""Apify REST client: start an actor run, wait up to a timeout, return its dataset items and real cost."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from urllib.parse import urlencode

import httpx

API = "https://api.apify.com/v2"
INSTAGRAM_ACTOR = "apify~instagram-scraper"
ADS_ACTOR = "apify~facebook-ads-scraper"
WAIT_STEP_S = 60  # the API holds a waitForFinish request for at most 60 s
FINISHED = {"SUCCEEDED", "FAILED", "ABORTED", "TIMED-OUT"}


class ApifyError(RuntimeError):
    def __init__(self, message: str, cost_usd: Decimal = Decimal("0")) -> None:
        super().__init__(message)
        self.cost_usd = cost_usd


@dataclass
class ActorResult:
    items: list[dict]
    cost_usd: Decimal
    run_id: str


def ad_library_url(query: str, country: str = "XK") -> str:
    params = {"active_status": "active", "ad_type": "all", "country": country, "media_type": "all"}
    if query.strip():
        params |= {"q": query.strip(), "search_type": "keyword_unordered"}
    return "https://www.facebook.com/ads/library/?" + urlencode(params)


def _cost(run: dict) -> Decimal:
    return Decimal(str(run.get("usageTotalUsd") or 0))


def _error_text(r: httpx.Response) -> str:
    try:
        return str(r.json()["error"]["message"])[:200]
    except (ValueError, KeyError, TypeError):
        return r.text[:200]


class ApifyClient:
    def __init__(self, token: str, http: httpx.Client | None = None, timeout_s: int = 120) -> None:
        self.http = http or httpx.Client(timeout=WAIT_STEP_S + 15)
        self.headers = {"Authorization": f"Bearer {token}"}
        self.timeout_s = timeout_s

    def _request(self, method: str, path: str, **kwargs):
        r = self.http.request(method, f"{API}{path}", headers=self.headers, **kwargs)
        if r.status_code >= 400:
            raise ApifyError(f"apify {r.status_code}: {_error_text(r)}")
        return r.json()

    def run(self, actor: str, actor_input: dict, *, max_items: int) -> ActorResult:
        params = {"timeout": self.timeout_s, "maxItems": max_items, "waitForFinish": WAIT_STEP_S}
        run = self._request("POST", f"/acts/{actor}/runs", params=params, json=actor_input)["data"]
        waited = WAIT_STEP_S
        while run["status"] not in FINISHED and waited < self.timeout_s:
            run = self._request(
                "GET", f"/actor-runs/{run['id']}", params={"waitForFinish": WAIT_STEP_S}
            )["data"]
            waited += WAIT_STEP_S
        if run["status"] not in FINISHED:
            self._request("POST", f"/actor-runs/{run['id']}/abort")
            run = self._request("GET", f"/actor-runs/{run['id']}")["data"]
            raise ApifyError(f"timed out after {self.timeout_s} s", _cost(run))
        if run["status"] != "SUCCEEDED":
            raise ApifyError(f"run {run['status'].lower()}", _cost(run))
        items = self._request(
            "GET",
            f"/datasets/{run['defaultDatasetId']}/items",
            params={"clean": "true", "limit": max_items},
        )
        return ActorResult(items=list(items)[:max_items], cost_usd=_cost(run), run_id=run["id"])
```

- [ ] **Step 2: Write the tests**

Create `tests/test_apify.py`:

```python
from decimal import Decimal

import httpx
import pytest

from scout.sources.apify import INSTAGRAM_ACTOR, ApifyClient, ApifyError, ad_library_url

RUN = "/v2/acts/apify~instagram-scraper/runs"
RUN_GET = "/v2/actor-runs/r1"


def _run(status, cost=0.031):
    return {"data": {"id": "r1", "status": status, "defaultDatasetId": "d1", "usageTotalUsd": cost}}


def _client(routes):
    calls = []

    def handler(request):
        calls.append(request)
        resp = routes.get((request.method, request.url.path))
        if resp is None:
            return httpx.Response(404, json={"error": {"message": "not found"}})
        return resp() if callable(resp) else resp

    http = httpx.Client(transport=httpx.MockTransport(handler))
    return ApifyClient("tok", http=http), calls


def test_run_returns_items_and_real_cost():
    client, calls = _client(
        {
            ("POST", RUN): httpx.Response(201, json=_run("SUCCEEDED")),
            ("GET", "/v2/datasets/d1/items"): httpx.Response(200, json=[{"username": "a"}]),
        }
    )
    res = client.run(INSTAGRAM_ACTOR, {"search": "torta"}, max_items=30)
    assert res.items == [{"username": "a"}] and res.cost_usd == Decimal("0.031")
    params = calls[0].url.params
    assert (params["maxItems"], params["timeout"], params["waitForFinish"]) == ("30", "120", "60")
    assert calls[0].headers["Authorization"] == "Bearer tok"
    assert calls[1].url.params["limit"] == "30"


def test_run_keeps_at_most_max_items():
    client, _ = _client(
        {
            ("POST", RUN): httpx.Response(201, json=_run("SUCCEEDED")),
            ("GET", "/v2/datasets/d1/items"): httpx.Response(200, json=[{"i": n} for n in range(9)]),
        }
    )
    assert len(client.run(INSTAGRAM_ACTOR, {}, max_items=5).items) == 5


def test_run_polls_until_finished():
    client, _ = _client(
        {
            ("POST", RUN): httpx.Response(201, json=_run("RUNNING")),
            ("GET", RUN_GET): httpx.Response(200, json=_run("SUCCEEDED", 0.04)),
            ("GET", "/v2/datasets/d1/items"): httpx.Response(200, json=[]),
        }
    )
    assert client.run(INSTAGRAM_ACTOR, {}, max_items=30).cost_usd == Decimal("0.04")


def test_timeout_aborts_and_keeps_the_cost():
    client, calls = _client(
        {
            ("POST", RUN): httpx.Response(201, json=_run("RUNNING")),
            ("GET", RUN_GET): httpx.Response(200, json=_run("RUNNING", 0.02)),
            ("POST", "/v2/actor-runs/r1/abort"): httpx.Response(200, json=_run("ABORTING")),
        }
    )
    with pytest.raises(ApifyError, match="timed out") as e:
        client.run(INSTAGRAM_ACTOR, {}, max_items=30)
    assert e.value.cost_usd == Decimal("0.02")
    assert any(c.url.path.endswith("/abort") for c in calls)


def test_failed_run_raises_with_its_cost():
    client, _ = _client({("POST", RUN): httpx.Response(201, json=_run("FAILED", 0.01))})
    with pytest.raises(ApifyError, match="run failed") as e:
        client.run(INSTAGRAM_ACTOR, {}, max_items=30)
    assert e.value.cost_usd == Decimal("0.01")


def test_http_error_carries_the_api_message():
    body = {"error": {"message": "Monthly usage hard limit exceeded"}}
    client, _ = _client({("POST", RUN): httpx.Response(402, json=body)})
    with pytest.raises(ApifyError, match="hard limit") as e:
        client.run(INSTAGRAM_ACTOR, {}, max_items=30)
    assert e.value.cost_usd == Decimal("0")


def test_ad_library_url():
    assert "country=XK" in ad_library_url("") and "q=" not in ad_library_url("")
    url = ad_library_url("torta ditelindje")
    assert "q=torta+ditelindje" in url and "search_type=keyword_unordered" in url
```

- [ ] **Step 3: Run the tests and lint**

Run: `uv run pytest -q tests/test_apify.py`
Expected: 7 passed.

Run: `uv run ruff format scout/sources/apify.py tests/test_apify.py && uv run ruff check scout/sources/apify.py tests/test_apify.py`

---

### Task 3: Social normalisers

**Files:**
- Create: `scout/sources/social.py`
- Create: `tests/social_samples.py` (sample payloads, reused in Task 5)
- Test: `tests/test_social.py`

**Interfaces:**
- Produces:
  - `question_counts(texts) -> {"price": int, "delivery": int, "where": int}`
  - `instagram_summary(items: list[dict]) -> {"shops": [shop], "questions": counts}`. Each shop has the keys `username, name, followers, category, last_post, url`, with `last_post` as an ISO date or `None`. At most 30 shops.
  - `ads_summary(items: list[dict], *, today: date) -> {"ads": [ad], "count": int, "foreign": int, "long_running": int}`. Each ad dict has the keys Task 1's `upsert_ads` takes, plus `long_running: bool`.
  - `is_foreign(text: str, link_url: str | None) -> bool | None`

The Apify field names below come from the two actors' documented output. The live test in Task 8 confirms them; if a live sample differs, fix `_first(...)` key lists here.

- [ ] **Step 1: Write the normalisers**

Create `scout/sources/social.py`:

```python
"""Turn raw Apify items into privacy-safe scout records: public business accounts only, comments reduced
to counts, ads with a local/foreign guess."""

from __future__ import annotations

import re
from collections.abc import Iterable
from datetime import UTC, date, datetime
from urllib.parse import urlparse

MAX_SHOPS = 30
LONG_RUNNING_DAYS = 30
QUESTION_PATTERNS = {
    "price": re.compile(
        r"sa\s*kushton|sa\s*[eë]sht[eë]|[cç]mimi|qmimi|\bprice\b|how much|\bcost", re.I
    ),
    "delivery": re.compile(
        r"d[eë]rg|posta|transport|delivery|\bship|a\s*vjen\s*n[eë]", re.I
    ),
    "where": re.compile(
        r"ku\s*gjendeni|ku\s*jeni|ku\s*mund|lokacion|adres|where (can|do|are)", re.I
    ),
}
KOSOVO_LOCAL = re.compile(
    r"\+383|\b04[3-9][\s-]?\d{3}|prishtin|prizren|\bpej[eë]\b|gjakov|mitrovic|ferizaj|gjilan", re.I
)
FOREIGN_HINTS = re.compile(r"\+355|\+389|\+381|\+382|\+387|\+49|\+41|\+43|\+90|\btiran", re.I)
FOREIGN_TLDS = (".al", ".mk", ".rs", ".me", ".ba", ".hr", ".si", ".de", ".ch", ".at", ".tr")


def _first(d: dict, *keys):
    for k in keys:
        v = d.get(k)
        if v not in (None, ""):
            return v
    return None


def _dict(v) -> dict:
    return v if isinstance(v, dict) else {}


def _list(v) -> list:
    return v if isinstance(v, list) else []


def _date(v) -> date | None:
    if isinstance(v, int | float) and v > 0:
        return datetime.fromtimestamp(v, tz=UTC).date()
    if isinstance(v, str) and len(v) >= 10:
        try:
            return date.fromisoformat(v[:10])
        except ValueError:
            return None
    return None


def question_counts(texts: Iterable[str]) -> dict[str, int]:
    counts = dict.fromkeys(QUESTION_PATTERNS, 0)
    for text in texts:
        for kind, pattern in QUESTION_PATTERNS.items():
            if isinstance(text, str) and pattern.search(text):
                counts[kind] += 1
    return counts


def instagram_summary(items: list[dict]) -> dict:
    shops: list[dict] = []
    texts: list[str] = []
    for it in _list(items):
        it = _dict(it)
        username = it.get("username")
        is_business = it.get("isBusinessAccount") or it.get("businessCategoryName")
        if not username or it.get("private") or not is_business:
            continue
        posts = [_dict(p) for p in _list(it.get("latestPosts"))]
        dates = [d for d in (_date(p.get("timestamp")) for p in posts) if d]
        for p in posts:
            texts += [_dict(c).get("text") or "" for c in _list(p.get("latestComments"))]
        shops.append(
            {
                "username": str(username),
                "name": str(it.get("fullName") or ""),
                "followers": int(it.get("followersCount") or 0),
                "category": it.get("businessCategoryName"),
                "last_post": max(dates).isoformat() if dates else None,
                "url": it.get("url") or f"https://www.instagram.com/{username}/",
            }
        )
        if len(shops) >= MAX_SHOPS:
            break
    return {"shops": shops, "questions": question_counts(texts)}


def is_foreign(text: str, link_url: str | None) -> bool | None:
    host = (urlparse(link_url or "").hostname or "").lower()
    if host.endswith(FOREIGN_TLDS) or FOREIGN_HINTS.search(text or ""):
        return True
    if host.endswith(".rks") or KOSOVO_LOCAL.search(text or ""):
        return False
    return None


def ads_summary(items: list[dict], *, today: date) -> dict:
    ads: list[dict] = []
    for it in _list(items):
        it = _dict(it)
        archive_id = _first(it, "adArchiveID", "adArchiveId", "ad_archive_id")
        if archive_id is None:
            continue
        snap = _dict(it.get("snapshot"))
        text = str(_first(_dict(snap.get("body")), "text") or "")
        link = _first(snap, "linkUrl", "link_url")
        active = bool(_first(it, "isActive", "is_active"))
        first = _date(_first(it, "startDate", "start_date", "startDateFormatted"))
        end = _date(_first(it, "endDate", "end_date", "endDateFormatted"))
        last = today if active else end
        platforms = _first(it, "publisherPlatform", "publisher_platform") or []
        ads.append(
            {
                "ad_archive_id": str(archive_id),
                "page_name": str(_first(it, "pageName", "page_name") or ""),
                "page_url": _first(snap, "pageProfileUri", "page_profile_uri"),
                "ad_text": text[:2000],
                "platforms": [str(p).lower() for p in _list(platforms)],
                "first_seen": first.isoformat() if first else None,
                "last_seen": last.isoformat() if last else None,
                "is_active": active,
                "is_foreign": is_foreign(text, link),
                "link_url": link,
                "long_running": bool(
                    active and first and (today - first).days >= LONG_RUNNING_DAYS
                ),
            }
        )
    return {
        "ads": ads,
        "count": len(ads),
        "foreign": sum(1 for a in ads if a["is_foreign"]),
        "long_running": sum(1 for a in ads if a["long_running"]),
    }
```

- [ ] **Step 2: Write the sample payloads**

Create `tests/social_samples.py`:

```python
"""Sample Apify payloads in the documented output shape of the two actors."""

PROFILES = [
    {
        "username": "tortat.e.mira",
        "fullName": "Tortat e Mira",
        "isBusinessAccount": True,
        "businessCategoryName": "Bakery",
        "followersCount": 5400,
        "private": False,
        "url": "https://www.instagram.com/tortat.e.mira/",
        "latestPosts": [
            {
                "timestamp": "2026-10-01T10:00:00.000Z",
                "latestComments": [
                    {"text": "Sa kushton kjo torte?", "ownerUsername": "private.person1"},
                    {"text": "A dergoni ne Prizren?", "ownerUsername": "private.person2"},
                    {"text": "Ku gjendeni?", "ownerUsername": "private.person3"},
                    {"text": "Shume e bukur", "ownerUsername": "private.person4"},
                ],
            },
            {"timestamp": "2026-09-20T10:00:00.000Z", "latestComments": []},
        ],
    },
    {
        "username": "ana.private",
        "fullName": "Ana",
        "isBusinessAccount": False,
        "followersCount": 300,
        "latestPosts": [
            {
                "timestamp": "2026-10-02T10:00:00.000Z",
                "latestComments": [{"text": "sa kushton?", "ownerUsername": "x"}],
            }
        ],
    },
    {"username": "secret.shop", "isBusinessAccount": True, "private": True, "followersCount": 10},
]

ADS = [
    {
        "adArchiveID": "111",
        "pageName": "Torta Shop",
        "isActive": True,
        "startDate": 1756684800,
        "publisherPlatform": ["FACEBOOK", "INSTAGRAM"],
        "snapshot": {
            "body": {"text": "Porosit torten tende! Tel +383 44 123 456, Prishtinë"},
            "pageProfileUri": "https://facebook.com/tortashop",
            "linkUrl": "https://tortashop.rks",
        },
    },
    {
        "adArchiveID": "222",
        "pageName": "Shopi AL",
        "isActive": True,
        "startDateFormatted": "2026-10-01T00:00:00",
        "publisherPlatform": ["INSTAGRAM"],
        "snapshot": {
            "body": {"text": "Dërgesa në Kosovë për 2 ditë"},
            "linkUrl": "https://shopi.al/products",
        },
    },
    {
        "ad_archive_id": "333",
        "page_name": "Mystery",
        "is_active": False,
        "start_date": 1759276800,
        "end_date": 1759708800,
        "snapshot": {"body": {"text": "Best deals"}},
    },
    {"pageName": "no id"},
]
```

- [ ] **Step 3: Write the tests**

Create `tests/test_social.py`:

```python
import json
from datetime import date

from scout.sources import social as S
from tests.social_samples import ADS, PROFILES

TODAY = date(2026, 10, 19)


def test_instagram_summary_keeps_only_public_business_accounts():
    out = S.instagram_summary(PROFILES)
    assert out["shops"] == [
        {
            "username": "tortat.e.mira",
            "name": "Tortat e Mira",
            "followers": 5400,
            "category": "Bakery",
            "last_post": "2026-10-01",
            "url": "https://www.instagram.com/tortat.e.mira/",
        }
    ]


def test_instagram_summary_reduces_comments_to_counts():
    out = S.instagram_summary(PROFILES)
    assert out["questions"] == {"price": 1, "delivery": 1, "where": 1}
    dumped = json.dumps(out, ensure_ascii=False)
    for secret in ("private.person", "Sa kushton", "ana.private", "secret.shop"):
        assert secret not in dumped


def test_instagram_summary_caps_shops():
    many = [{"username": f"s{n}", "isBusinessAccount": True} for n in range(40)]
    assert len(S.instagram_summary(many)["shops"]) == 30


def test_normalisers_survive_odd_shapes():
    odd = [None, "x", {"username": None}, {"username": "a", "isBusinessAccount": True,
           "latestPosts": "nope"}, {"adArchiveID": "9", "snapshot": None, "publisherPlatform": "FB"}]
    assert [s["username"] for s in S.instagram_summary(odd)["shops"]] == ["a"]
    assert S.ads_summary(odd, today=TODAY)["count"] == 1
    assert S.instagram_summary(None) == {"shops": [], "questions": S.question_counts([])}


def test_ads_summary_dates_platforms_and_origin():
    out = S.ads_summary(ADS, today=TODAY)
    by_id = {a["ad_archive_id"]: a for a in out["ads"]}
    assert set(by_id) == {"111", "222", "333"}
    local, foreign, unknown = by_id["111"], by_id["222"], by_id["333"]
    assert local["is_foreign"] is False and local["platforms"] == ["facebook", "instagram"]
    assert (local["first_seen"], local["last_seen"]) == ("2025-09-01", "2026-10-19")
    assert local["long_running"] is True and local["page_url"] == "https://facebook.com/tortashop"
    assert foreign["is_foreign"] is True and foreign["long_running"] is False
    assert unknown["is_foreign"] is None and unknown["is_active"] is False
    assert (unknown["first_seen"], unknown["last_seen"]) == ("2025-10-01", "2025-10-06")
    assert (out["count"], out["foreign"], out["long_running"]) == (3, 1, 1)


def test_question_counts_albanian_and_english():
    texts = ["Çmimi?", "how much is it", "a dërgoni në Gjilan", "where can I buy", "nice"]
    assert S.question_counts(texts) == {"price": 2, "delivery": 1, "where": 1}
```

- [ ] **Step 4: Run the tests and lint**

Run: `uv run pytest -q tests/test_social.py`
Expected: 6 passed. If `tests.social_samples` cannot be imported, check `tests/__init__.py`. If it is missing, import with `from social_samples import ADS, PROFILES` instead, because pytest puts `tests/` on `sys.path` (rootdir-relative import). Use the same import form in Task 5.

Run: `uv run ruff format scout/sources/social.py tests/social_samples.py tests/test_social.py && uv run ruff check scout/sources/social.py tests/social_samples.py tests/test_social.py`

---

### Task 4: Crawl client

**Files:**
- Create: `scout/sources/crawl.py`
- Modify: `pyproject.toml` (add the optional extra `crawl`), `uv.lock`
- Test: `tests/test_crawl.py`

**Interfaces:**
- Produces:
  - `ALLOWED_DOMAINS: tuple[str, ...]`
  - `allowed_domain(url) -> str | None`
  - `source_for(domain) -> str`, which maps `merrjep.com` to `"merrjep"`, `kosovajob.com` to `"kosovajob"` and any other domain to `"kosovo-sites"`
  - `CrawlRefused(RuntimeError)`
  - `CrawlClient(render=None, http=None, sleep=time.sleep, clock=time.monotonic).fetch(url) -> str`, which returns Markdown
  - `crawl_available() -> bool`

- [ ] **Step 1: Add the optional dependency**

In `pyproject.toml` under `[project.optional-dependencies]`, add:

```toml
crawl = ["crawl4ai>=0.6"]
```

Run: `uv lock`
Expected: `uv.lock` updated, exit 0.

- [ ] **Step 2: Write the client**

Create `scout/sources/crawl.py`:

```python
"""Polite fetches of allowlisted Kosovo sites, rendered to Markdown by Crawl4AI (optional extra `crawl`)."""

from __future__ import annotations

import importlib.util
import time
from collections.abc import Callable
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import httpx

ALLOWED_DOMAINS = (
    "merrjep.com",
    "gjirafa50.com",
    "kosovajob.com",
    "telegrafi.com",
    "koha.net",
    "kallxo.com",
    "prishtinainsight.com",
    "arbk.rks-gov.net",
)
SOURCE_BY_DOMAIN = {"merrjep.com": "merrjep", "kosovajob.com": "kosovajob"}
DEFAULT_SOURCE = "kosovo-sites"
MIN_INTERVAL_S = 2.0
USER_AGENT = "KosovoGapScout/1.0 (+https://github.com/EltonMehmeti/kosovo-gap-scout)"


class CrawlRefused(RuntimeError):
    pass


def crawl_available() -> bool:
    return importlib.util.find_spec("crawl4ai") is not None


def allowed_domain(url: str) -> str | None:
    parsed = urlparse(url.strip())
    if parsed.scheme not in ("http", "https"):
        return None
    host = (parsed.hostname or "").lower()
    for domain in ALLOWED_DOMAINS:
        if host == domain or host.endswith("." + domain):
            return domain
    return None


def source_for(domain: str) -> str:
    return SOURCE_BY_DOMAIN.get(domain, DEFAULT_SOURCE)


def _render_with_crawl4ai(url: str) -> str:
    import asyncio

    from crawl4ai import AsyncWebCrawler, BrowserConfig, CacheMode, CrawlerRunConfig

    async def go() -> str:
        async with AsyncWebCrawler(
            config=BrowserConfig(headless=True, user_agent=USER_AGENT)
        ) as crawler:
            res = await crawler.arun(url, config=CrawlerRunConfig(cache_mode=CacheMode.BYPASS))
        if not res.success:
            raise RuntimeError(res.error_message or f"status {res.status_code}")
        return str(res.markdown or "")

    return asyncio.run(go())


class CrawlClient:
    def __init__(
        self,
        render: Callable[[str], str] | None = None,
        http: httpx.Client | None = None,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.render = render or _render_with_crawl4ai
        self.http = http or httpx.Client(
            timeout=15, headers={"User-Agent": USER_AGENT}, follow_redirects=True
        )
        self.sleep, self.clock = sleep, clock
        self._robots: dict[str, RobotFileParser] = {}
        self._last: float | None = None

    def _robots_for(self, url: str) -> RobotFileParser:
        p = urlparse(url)
        base = f"{p.scheme}://{p.netloc}"
        if base not in self._robots:
            rp = RobotFileParser()
            try:
                r = self.http.get(base + "/robots.txt")
                if r.status_code in (401, 403):
                    rp.disallow_all = True
                elif r.status_code >= 400:
                    rp.allow_all = True
                else:
                    rp.parse(r.text.splitlines())
            except httpx.HTTPError:
                rp.disallow_all = True
            self._robots[base] = rp
        return self._robots[base]

    def fetch(self, url: str) -> str:
        url = url.strip()
        if allowed_domain(url) is None:
            raise CrawlRefused("domain not on the allowlist")
        if not self._robots_for(url).can_fetch(USER_AGENT, url):
            raise CrawlRefused("robots.txt disallows this page")
        if self._last is not None:
            wait = MIN_INTERVAL_S - (self.clock() - self._last)
            if wait > 0:
                self.sleep(wait)
        self._last = self.clock()
        return self.render(url)
```

- [ ] **Step 3: Write the tests**

Create `tests/test_crawl.py`:

```python
import httpx
import pytest

from scout.sources.crawl import CrawlClient, CrawlRefused, allowed_domain, source_for


class Clock:
    def __init__(self):
        self.t = 100.0
        self.sleeps = []

    def __call__(self):
        return self.t

    def sleep(self, s):
        self.sleeps.append(s)
        self.t += s


def _client(robots="User-agent: *\nDisallow: /admin\n", status=200, rendered=None, clock=None):
    hits = {"robots": 0}

    def handler(request):
        if request.url.path == "/robots.txt":
            hits["robots"] += 1
            if status == "down":
                raise httpx.ConnectError("down")
            return httpx.Response(status, text=robots)
        return httpx.Response(404)

    rendered = rendered if rendered is not None else []
    clock = clock or Clock()
    client = CrawlClient(
        render=lambda url: rendered.append(url) or f"# page {url}",
        http=httpx.Client(transport=httpx.MockTransport(handler)),
        sleep=clock.sleep,
        clock=clock,
    )
    return client, rendered, hits


def test_allowed_domain():
    assert allowed_domain("https://www.merrjep.com/shpalljet") == "merrjep.com"
    assert allowed_domain("https://m.merrjep.com/x") == "merrjep.com"
    assert allowed_domain("https://arbk.rks-gov.net/page") == "arbk.rks-gov.net"
    for bad in ("https://evilmerrjep.com", "https://merrjep.com.evil.io", "ftp://merrjep.com", "x"):
        assert allowed_domain(bad) is None
    assert source_for("merrjep.com") == "merrjep" and source_for("koha.net") == "kosovo-sites"


def test_refuses_domains_off_the_allowlist():
    client, rendered, _ = _client()
    with pytest.raises(CrawlRefused, match="allowlist"):
        client.fetch("https://www.instagram.com/x")
    assert rendered == []


def test_obeys_robots_and_fetches_it_once_per_host():
    client, rendered, hits = _client()
    with pytest.raises(CrawlRefused, match="robots"):
        client.fetch("https://www.merrjep.com/admin/x")
    assert client.fetch("https://www.merrjep.com/shpalljet").startswith("# page")
    assert rendered == ["https://www.merrjep.com/shpalljet"] and hits["robots"] == 1


def test_unreachable_robots_means_no_crawl_and_404_means_allowed():
    client, _, _ = _client(status="down")
    with pytest.raises(CrawlRefused):
        client.fetch("https://koha.net/a")
    client, rendered, _ = _client(status=404)
    client.fetch("https://koha.net/a")
    assert rendered == ["https://koha.net/a"]


def test_pages_are_two_seconds_apart():
    clock = Clock()
    client, _, _ = _client(clock=clock)
    for n in range(3):
        client.fetch(f"https://koha.net/{n}")
    assert clock.sleeps == [2.0, 2.0]
    clock.t += 5
    client.fetch("https://koha.net/later")
    assert clock.sleeps == [2.0, 2.0]
```

- [ ] **Step 4: Run the tests and lint**

Run: `uv run pytest -q tests/test_crawl.py`
Expected: 5 passed. These tests do not need Crawl4AI installed.

Run: `uv run ruff format scout/sources/crawl.py tests/test_crawl.py && uv run ruff check scout/sources/crawl.py tests/test_crawl.py`

---

### Task 5: Social guard and the three tools

**Files:**
- Create: `scout/worker/social_guard.py`
- Modify: `scout/worker/tools.py` (imports, `ToolContext`, `_presence_check`, three `*_impl` functions, `build_tools`)
- Test: `tests/test_social_tools.py`

**Interfaces:**
- Consumes: Task 1 repo functions; Task 2 `ApifyClient`, `ApifyError`, `ActorResult`, `INSTAGRAM_ACTOR`, `ADS_ACTOR`, `ad_library_url`; Task 3 `social.instagram_summary`, `social.ads_summary`; Task 4 `CrawlClient`, `CrawlRefused`, `allowed_domain`, `source_for`, `ALLOWED_DOMAINS`.
- Produces:
  - `social_guard.qualifies(ctx) -> bool`
  - `social_guard.resume_text(day: date) -> str`
  - `social_guard.credit_used_up(session, day, cap_usd) -> bool`
  - `social_guard.ADS_SWEEP_PROFILE = "ads-sweep"`
  - New `ToolContext` fields: `apify`, `crawler`, `apify_monthly_usd`, `social_calls`, `social_ok`, `crawl_pages`
  - New tool-name constants: `SOCIAL_TOOL_NAMES = ("instagram_search", "ad_library_search")` and `CRAWL_TOOL_NAMES = ("kosovo_site_crawl",)`. `TOOL_NAMES` itself is unchanged.

- [ ] **Step 1: Write the guard**

Create `scout/worker/social_guard.py`:

```python
"""Code-enforced limits on paid social calls (spec §4): the score gate, one call per tool per task, the
monthly Apify credit cap, and a cache that serves repeat queries free."""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, timedelta
from decimal import Decimal

import httpx

from scout.db import repo
from scout.db.repo import CostRecord
from scout.sources.apify import ActorResult, ApifyError

SCORE_GATE = 60
ADS_SWEEP_PROFILE = "ads-sweep"
CACHE_DAYS = {"instagram": 30, "ads": 14}
TOOL_FOR = {"instagram": "instagram_search", "ads": "ad_library_search"}
SOURCE_NAME = {"instagram": "apify-instagram", "ads": "meta-ad-library"}
QUERY_KEY_CHARS = 300


def query_key(query: str, max_items: int) -> str:
    return f"{' '.join(query.lower().split())[:QUERY_KEY_CHARS]}|{max_items}"


def qualifies(ctx) -> bool:
    gap_id = (ctx.payload or {}).get("gap_id")
    if ctx.profile != "verify-gap" or gap_id is None:
        return False
    gap = repo.get_gap(ctx.session, int(gap_id))
    flagged = int(gap_id) in (repo.get_setting(ctx.session, "flagged_gaps", []) or [])
    return gap is not None and (gap.score_total >= SCORE_GATE or flagged)


def resume_text(day: date) -> str:
    next_month = (day.replace(day=28) + timedelta(days=4)).replace(day=1)
    return f"Social credit used up for {day:%B} — paid social checks resume {next_month:%b} 1."


def credit_used_up(session, day: date, cap_usd: Decimal) -> bool:
    return repo.apify_usd_in_month(session, day) >= Decimal(cap_usd)


def _gate(ctx, source: str) -> str | None:
    if ctx.profile == ADS_SWEEP_PROFILE:
        if source == "ads":
            return None
        return "error: the weekly ads sweep may only call ad_library_search"
    if qualifies(ctx):
        return None
    return (
        "paid social checks run only while checking a gap that scores 60 or more (or that the "
        "founder flagged) — use web_search with site:instagram.com instead"
    )


def _record(ctx, source: str, cost_usd: Decimal, items: int) -> None:
    ctx.guard.record(
        CostRecord(
            "apify",
            "apify",
            source,
            {"usd": str(cost_usd), "items": items, "calls": 1},
            Decimal("0"),
            task_id=ctx.task_id,
        )
    )


def paid_call(
    ctx,
    source: str,
    query: str,
    *,
    max_items: int,
    run: Callable[[int], ActorResult],
    normalise: Callable[[list[dict]], dict],
) -> dict | str:
    """The normalised result, or the text to show the model when the call may not or did not run."""
    if refusal := _gate(ctx, source):
        return refusal
    key = query_key(query, max_items)
    cached = repo.get_social_cache(
        ctx.session, source, key, now=ctx.now, max_age_days=CACHE_DAYS[source]
    )
    if cached is not None:
        ctx.social_ok += 1
        return cached.items
    if ctx.social_calls.get(source, 0) >= 1:
        return f"error: one {TOOL_FOR[source]} per task — work with the result you already have"
    if credit_used_up(ctx.session, ctx.guard.day, ctx.apify_monthly_usd):
        return f"social source unavailable: {resume_text(ctx.guard.day)}"
    ctx.social_calls[source] = ctx.social_calls.get(source, 0) + 1
    try:
        result = run(max_items)
    except ApifyError as e:
        _record(ctx, source, e.cost_usd, 0)
        repo.mark_source(ctx.session, SOURCE_NAME[source], ok=False, now=ctx.now)
        return f"social source unavailable: {e}"
    except httpx.HTTPError as e:
        _record(ctx, source, Decimal("0"), 0)
        repo.mark_source(ctx.session, SOURCE_NAME[source], ok=False, now=ctx.now)
        return f"social source unavailable: {type(e).__name__}"
    items = result.items[:max_items]
    _record(ctx, source, result.cost_usd, len(items))
    repo.mark_source(ctx.session, SOURCE_NAME[source], ok=True, now=ctx.now)
    summary = normalise(items)
    repo.put_social_cache(ctx.session, source, key, summary, cost_usd=result.cost_usd, now=ctx.now)
    ctx.social_ok += 1
    return summary
```

- [ ] **Step 2: Extend `ToolContext` and the presence check**

In `scout/worker/tools.py`:

Change the imports block to:

```python
from scout.db import repo
from scout.db.repo import CostRecord, FactIn
from scout.sources import apple, play, social
from scout.sources.apify import ADS_ACTOR, INSTAGRAM_ACTOR, ApifyClient, ad_library_url
from scout.sources.askdata import AskDataClient
from scout.sources.crawl import ALLOWED_DOMAINS, CrawlClient, CrawlRefused, allowed_domain, source_for
from scout.sources.places import PlacesClient
from scout.worker import social_guard
```

Add the constants after `TOOL_NAMES`:

```python
SOCIAL_TOOL_NAMES = ("instagram_search", "ad_library_search")
CRAWL_TOOL_NAMES = ("kosovo_site_crawl",)
MAX_INSTAGRAM_ACCOUNTS = 30
MAX_ADS = 50
SWEEP_MAX_ADS = 300
SWEEP_RESULT_LIMIT = 4000
MAX_CRAWL_PAGES = 20
```

Add the fields at the end of `ToolContext`, after `search_note`:

```python
    apify: ApifyClient | None = None
    crawler: CrawlClient | None = None
    apify_monthly_usd: Decimal = Decimal("4.50")
    social_calls: dict[str, int] = field(default_factory=dict)
    social_ok: int = 0
    crawl_pages: int = 0
```

In `_presence_check`, add this right before `value["verdict"] = verdict`:

```python
    if ctx.apify is not None and social_guard.qualifies(ctx) and ctx.social_ok == 0:
        value["social"] = "partial"
        confidence = min(confidence, DEGRADED_CHECK_MAX_CONFIDENCE)
```

- [ ] **Step 3: Add the three `*_impl` functions**

In `scout/worker/tools.py`, add these after `askdata_fetch_impl`, under a new `# ---------- social and Kosovo sites ----------` header that matches the existing section headers:

```python
def instagram_search_impl(ctx: ToolContext, query: str) -> str:
    if ctx.apify is None:
        return "instagram_search unavailable (no APIFY_TOKEN configured) — use web_search instead"
    query = query.strip()
    if not query:
        return "error: query is empty"
    actor_input = {
        "search": query,
        "searchType": "user",
        "searchLimit": MAX_INSTAGRAM_ACCOUNTS,
        "resultsType": "details",
        "resultsLimit": MAX_INSTAGRAM_ACCOUNTS,
    }
    out = social_guard.paid_call(
        ctx,
        "instagram",
        query,
        max_items=MAX_INSTAGRAM_ACCOUNTS,
        run=lambda n: ctx.apify.run(INSTAGRAM_ACTOR, actor_input, max_items=n),
        normalise=social.instagram_summary,
    )
    if isinstance(out, str):
        return out
    shops, q = out["shops"], out["questions"]
    gap_id = ctx.payload.get("gap_id")
    if gap_id is not None:
        repo.upsert_fact(
            ctx.session,
            FactIn(
                claim=f"Instagram search {query!r}: {len(shops)} business accounts in results",
                entity_type="social",
                entity_key=f"gap:{gap_id}",
                confidence=0.7,
                sector_slug=_or_none(ctx.payload.get("sector") or ""),
                value={"query": query, **out},
                ttl_days=30,
                source_name="apify-instagram",
            ),
            run_id=ctx.run_id,
            observed_at=ctx.now,
        )
        ctx.touched_gap_ids.add(int(gap_id))
    lines = [f"{len(shops)} Instagram business accounts for {query!r}"]
    lines += [
        f"- @{s['username']} {s['name']} | {s['followers']} followers | {s['category'] or '-'} | "
        f"last post {s['last_post'] or '-'}"
        for s in shops
    ]
    lines.append(
        f"comment questions: price {q['price']}, delivery {q['delivery']}, where to buy {q['where']}"
    )
    return _clip("\n".join(lines), SOURCE_RESULT_LIMIT)


def ad_library_search_impl(ctx: ToolContext, query: str = "") -> str:
    if ctx.apify is None:
        return "ad_library_search unavailable (no APIFY_TOKEN configured) — use web_search instead"
    sweep = ctx.profile == social_guard.ADS_SWEEP_PROFILE
    query = query.strip()
    if not query and not sweep:
        return "error: query is empty"
    limit = SWEEP_MAX_ADS if sweep else MAX_ADS
    actor_input = {
        "startUrls": [{"url": ad_library_url(query)}],
        "resultsLimit": limit,
        "isDetailsPerAd": False,
    }
    out = social_guard.paid_call(
        ctx,
        "ads",
        query,
        max_items=limit,
        run=lambda n: ctx.apify.run(ADS_ACTOR, actor_input, max_items=n),
        normalise=lambda items: social.ads_summary(items, today=ctx.guard.day),
    )
    if isinstance(out, str):
        return out
    ads = out["ads"]
    gap_id = ctx.payload.get("gap_id")
    sector = _or_none(ctx.payload.get("sector") or "")
    repo.upsert_ads(
        ctx.session,
        ads,
        gap_id=int(gap_id) if gap_id is not None else None,
        sector_slug=sector,
        now=ctx.now,
    )
    head = (
        f"{out['count']} Meta ads shown in Kosovo for {query or 'all advertisers'!r}: "
        f"{out['foreign']} foreign sellers, {out['long_running']} running 30+ days"
    )
    if gap_id is not None and not sweep:
        repo.upsert_fact(
            ctx.session,
            FactIn(
                claim=head,
                entity_type="ad_signal",
                entity_key=f"gap:{gap_id}",
                confidence=0.7,
                sector_slug=sector,
                value={k: out[k] for k in ("count", "foreign", "long_running")} | {"query": query},
                ttl_days=14,
                source_name="meta-ad-library",
            ),
            run_id=ctx.run_id,
            observed_at=ctx.now,
        )
        ctx.touched_gap_ids.add(int(gap_id))

    def origin(a: dict) -> str:
        return {True: "foreign", False: "local"}.get(a["is_foreign"], "?")

    lines = [head]
    lines += [
        f"- {a['page_name']} | {origin(a)} | since {a['first_seen'] or '?'} | {a['ad_text'][:100]}"
        for a in ads
    ]
    return _clip("\n".join(lines), SWEEP_RESULT_LIMIT if sweep else SOURCE_RESULT_LIMIT)


def kosovo_site_crawl_impl(ctx: ToolContext, url: str) -> str:
    if ctx.crawler is None:
        return "kosovo_site_crawl unavailable (Crawl4AI is not installed) — use web_fetch instead"
    domain = allowed_domain(url)
    if domain is None:
        return f"error: only these sites can be crawled: {', '.join(ALLOWED_DOMAINS)}"
    if ctx.crawl_pages >= MAX_CRAWL_PAGES:
        return f"crawl limit reached for this task ({MAX_CRAWL_PAGES} pages) — use what you have"
    ctx.crawl_pages += 1
    source = source_for(domain)
    try:
        text = ctx.crawler.fetch(url)
    except CrawlRefused as e:
        repo.mark_source(ctx.session, source, ok=False, now=ctx.now)
        return f"page skipped: {e}"
    except Exception as e:  # noqa: BLE001 — a dead site must not kill the task
        repo.mark_source(ctx.session, source, ok=False, now=ctx.now)
        return f"page skipped: {type(e).__name__}"
    repo.mark_source(ctx.session, source, ok=True, now=ctx.now)
    return _clip(text.strip() or "(empty page)", SOURCE_RESULT_LIMIT)
```

- [ ] **Step 4: Register the tools**

In `build_tools`, before the `return [...]`, add:

```python
    @beta_tool
    def instagram_search(query: str) -> str:
        """Find Instagram business accounts in Kosovo by keyword (paid; one call per task; only while
        checking a gap that scores 60+). Returns public business accounts with followers and last post
        date, plus counts of comments asking about price, delivery or where to buy.

        Args:
            query: The word local sellers use, found first with web_search site:instagram.com, e.g.
                "torta prishtine" or "lule ferizaj".
        """
        return _run(ctx, "instagram_search", instagram_search_impl, query=query)

    @beta_tool
    def ad_library_search(query: str = "") -> str:
        """Search the public Meta Ad Library for ads shown in Kosovo (paid; one call per task). Shows who
        pays to sell this, whether the seller is local or foreign, and how long each ad has run.

        Args:
            query: Words a seller would put in the ad, in Albanian, e.g. "dërgesa falas torta". Leave
                empty only in the weekly ads sweep.
        """
        return _run(ctx, "ad_library_search", ad_library_search_impl, query=query)

    @beta_tool
    def kosovo_site_crawl(url: str) -> str:
        """Read one page of an allowlisted Kosovo site as Markdown (free; up to 20 pages per task):
        merrjep.com, gjirafa50.com, kosovajob.com, telegrafi.com, koha.net, kallxo.com,
        prishtinainsight.com, arbk.rks-gov.net. Use it for listings, prices and job ads.

        Args:
            url: Full https URL on one of those sites, e.g. a Merrjep search results page.
        """
        return _run(ctx, "kosovo_site_crawl", kosovo_site_crawl_impl, url=url)
```

Then replace the final `return [...]` with:

```python
    tools = [
        kb_search,
        kb_record_fact,
        kb_record_business,
        kb_record_proven_model,
        kb_propose_gap,
        kb_write_digest,
        places_search,
        app_store_search,
        askdata_list,
        askdata_table,
        askdata_fetch,
    ]
    if ctx.apify is not None:
        tools += [instagram_search, ad_library_search]
    if ctx.crawler is not None:
        tools.append(kosovo_site_crawl)
    return tools
```

The paid tools stay in the tool list for every task of a run, so the cached prefix stays the same; `social_guard` refuses them per task.

- [ ] **Step 5: Write the tests**

Create `tests/test_social_tools.py`:

```python
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from scout.budget.guard import BudgetGuard
from scout.db import repo
from scout.db.models import Ad, Cost, Fact, Source
from scout.seeds import seed_all
from scout.sources.apify import ActorResult, ApifyError
from scout.sources.askdata import AskDataClient
from scout.sources.crawl import CrawlRefused
from scout.worker import tools as T
from tests.social_samples import ADS, PROFILES

pytestmark = pytest.mark.db
NOW = datetime(2026, 10, 19, 6, 0, tzinfo=UTC)
DAY = date(2026, 10, 19)


class FakeApify:
    def __init__(self, items=None, cost="0.05", error=None):
        self.items, self.cost, self.error = items or [], cost, error
        self.calls = []

    def run(self, actor, actor_input, *, max_items):
        self.calls.append((actor, actor_input, max_items))
        if self.error:
            raise self.error
        return ActorResult(items=list(self.items), cost_usd=Decimal(self.cost), run_id="r1")


class FakeCrawler:
    def __init__(self, error=None):
        self.error, self.urls = error, []

    def fetch(self, url):
        self.urls.append(url)
        if self.error:
            raise self.error
        return "# listings\n- torta 25€"


@pytest.fixture
def gap(db_session):
    seed_all(db_session)
    g, _ = repo.propose_gap(
        db_session,
        title="Cake delivery",
        sector_slug="pets",
        proven_model_slug=None,
        hypothesis_md="",
        presence_level="unknown",
        why_not_yet_md="",
        run_id=None,
    )
    g.score_total = 72
    db_session.commit()
    return g


def _ctx(session, *, gap=None, profile="verify-gap", apify=None, crawler=None, day=DAY):
    run = repo.start_run(
        session, day=day, phase="foundation", budget_cap_eur=Decimal("3"), started_at=NOW
    )
    payload = {"gap_id": gap.id, "sector": "pets"} if gap is not None else {}
    return T.ToolContext(
        session=session,
        guard=BudgetGuard(session, day=day, daily_cap_eur=Decimal("3"), run_id=run.id),
        now=NOW,
        run_id=run.id,
        task_id=None,
        places=None,
        askdata=AskDataClient(),
        profile=profile,
        payload=payload,
        apify=apify,
        crawler=crawler,
    )


def _apify_costs(session):
    return session.query(Cost).filter_by(kind="apify").all()


def test_instagram_search_records_shops_fact_and_free_credit_cost(db_session, gap):
    fake = FakeApify(PROFILES)
    ctx = _ctx(db_session, gap=gap, apify=fake)
    out = T.instagram_search_impl(ctx, query="torta prishtine")
    assert "@tortat.e.mira" in out and "price 1" in out and "ana.private" not in out
    assert fake.calls[0][2] == 30 and fake.calls[0][1]["searchType"] == "user"
    fact = db_session.query(Fact).filter_by(entity_type="social", entity_key=f"gap:{gap.id}").one()
    assert fact.value["shops"][0]["username"] == "tortat.e.mira"
    (cost,) = _apify_costs(db_session)
    assert cost.units["usd"] == "0.05" and cost.cost_eur == 0
    src = db_session.query(Source).filter_by(name="apify-instagram").one()
    assert src.enabled is True and src.last_ok_at is not None
    assert ctx.social_ok == 1


def test_score_below_60_is_refused_without_a_call(db_session, gap):
    gap.score_total = 40
    db_session.commit()
    fake = FakeApify(PROFILES)
    out = T.instagram_search_impl(_ctx(db_session, gap=gap, apify=fake), query="torta")
    assert out.startswith("paid social checks run only") and fake.calls == []


def test_flagged_gap_below_60_is_allowed(db_session, gap):
    gap.score_total = 40
    repo.set_setting(db_session, "flagged_gaps", [gap.id])
    db_session.commit()
    fake = FakeApify(PROFILES)
    T.instagram_search_impl(_ctx(db_session, gap=gap, apify=fake), query="torta")
    assert len(fake.calls) == 1


def test_other_profiles_are_refused(db_session, gap):
    fake = FakeApify(ADS)
    ctx = _ctx(db_session, gap=gap, profile="map-sector", apify=fake)
    assert T.ad_library_search_impl(ctx, query="torta").startswith("paid social checks")
    assert fake.calls == []


def test_second_paid_call_in_a_task_is_refused(db_session, gap):
    fake = FakeApify(PROFILES)
    ctx = _ctx(db_session, gap=gap, apify=fake)
    T.instagram_search_impl(ctx, query="torta")
    assert T.instagram_search_impl(ctx, query="kek").startswith("error: one instagram_search")
    assert len(fake.calls) == 1


def test_cache_hit_is_free_and_does_not_count(db_session, gap):
    fake = FakeApify(PROFILES)
    T.instagram_search_impl(_ctx(db_session, gap=gap, apify=fake), query="Torta  Prishtine")
    ctx2 = _ctx(db_session, gap=gap, apify=fake)
    assert "@tortat.e.mira" in T.instagram_search_impl(ctx2, query="torta prishtine")
    assert len(fake.calls) == 1 and len(_apify_costs(db_session)) == 1
    T.instagram_search_impl(ctx2, query="kek")
    assert len(fake.calls) == 2


def test_long_query_works_and_empty_query_is_refused(db_session, gap):
    fake = FakeApify(PROFILES)
    ctx = _ctx(db_session, gap=gap, apify=fake)
    assert T.instagram_search_impl(ctx, query="   ").startswith("error: query is empty")
    assert "@tortat.e.mira" in T.instagram_search_impl(ctx, query="torta " * 100)


def test_monthly_cap_blocks_and_resets_next_month(db_session, gap):
    repo.record_cost(
        db_session,
        repo.CostRecord("apify", "apify", "ads", {"usd": "4.50"}, Decimal("0")),
        day=date(2026, 10, 5),
        run_id=None,
    )
    fake = FakeApify(PROFILES)
    out = T.instagram_search_impl(_ctx(db_session, gap=gap, apify=fake), query="torta")
    assert out == (
        "social source unavailable: Social credit used up for October — paid social checks "
        "resume Nov 1."
    )
    assert fake.calls == []
    T.instagram_search_impl(_ctx(db_session, gap=gap, apify=fake, day=date(2026, 11, 1)), query="kek")
    assert len(fake.calls) == 1


def test_failed_run_records_its_cost_and_makes_the_presence_check_partial(db_session, gap):
    fake = FakeApify(error=ApifyError("run failed", Decimal("0.02")))
    ctx = _ctx(db_session, gap=gap, apify=fake)
    assert T.instagram_search_impl(ctx, query="torta") == "social source unavailable: run failed"
    assert [c.units["usd"] for c in _apify_costs(db_session)] == ["0.02"]
    assert db_session.query(Source).filter_by(name="apify-instagram").one().failure_count == 1
    ctx.places_searches, ctx.app_store_searches = 7, 1
    T.kb_record_fact_impl(
        ctx,
        claim="presence check: absent",
        entity_type="presence_check",
        entity_key=f"gap:{gap.id}",
        confidence=0.8,
        value_json='{"verdict": "absent"}',
    )
    fact = db_session.query(Fact).filter_by(entity_type="presence_check").one()
    assert fact.value["social"] == "partial" and fact.value["verdict"] == "absent"
    assert fact.confidence == 0.5


def test_presence_check_is_not_partial_after_a_social_result(db_session, gap):
    ctx = _ctx(db_session, gap=gap, apify=FakeApify(PROFILES))
    T.instagram_search_impl(ctx, query="torta")
    ctx.places_searches, ctx.app_store_searches = 7, 1
    T.kb_record_fact_impl(
        ctx,
        claim="presence check: instagram-only",
        entity_type="presence_check",
        entity_key=f"gap:{gap.id}",
        confidence=0.8,
        value_json='{"verdict": "instagram-only"}',
    )
    fact = db_session.query(Fact).filter_by(entity_type="presence_check").one()
    assert "social" not in fact.value and fact.value["verdict"] == "instagram-only"
    assert fact.confidence == 0.8


def test_ad_library_search_stores_ads_and_a_signal_fact(db_session, gap):
    fake = FakeApify(ADS)
    out = T.ad_library_search_impl(_ctx(db_session, gap=gap, apify=fake), query="torta")
    assert "3 Meta ads" in out and "1 foreign" in out and fake.calls[0][2] == 50
    assert "q=torta" in fake.calls[0][1]["startUrls"][0]["url"]
    assert {a.ad_archive_id for a in repo.ads_for_gap(db_session, gap.id)} == {"111", "222", "333"}
    fact = db_session.query(Fact).filter_by(entity_type="ad_signal").one()
    assert fact.value["count"] == 3


def test_oversized_results_are_cut_to_the_limit(db_session, gap):
    many = [ADS[0] | {"adArchiveID": str(n)} for n in range(80)]
    T.ad_library_search_impl(_ctx(db_session, gap=gap, apify=FakeApify(many)), query="torta")
    assert db_session.query(Ad).count() == 50


def test_ads_sweep_gets_300_ads_and_no_instagram(db_session):
    seed_all(db_session)
    fake = FakeApify(ADS)
    ctx = _ctx(db_session, profile="ads-sweep", apify=fake)
    assert T.instagram_search_impl(ctx, query="torta").startswith("error: the weekly ads sweep")
    out = T.ad_library_search_impl(ctx, query="")
    assert out.startswith("3 Meta ads") and fake.calls[0][2] == 300
    assert db_session.query(Ad).filter(Ad.gap_id.is_(None)).count() == 3
    assert db_session.query(Fact).filter_by(entity_type="ad_signal").count() == 0


def test_crawl_tool_allowlist_cap_and_failures(db_session):
    seed_all(db_session)
    crawler = FakeCrawler()
    ctx = _ctx(db_session, crawler=crawler)
    assert T.kosovo_site_crawl_impl(ctx, url="https://instagram.com/x").startswith("error: only")
    for n in range(20):
        assert T.kosovo_site_crawl_impl(ctx, url=f"https://www.merrjep.com/{n}").startswith("# list")
    assert T.kosovo_site_crawl_impl(ctx, url="https://www.merrjep.com/21").startswith("crawl limit")
    assert len(crawler.urls) == 20
    for error in (CrawlRefused("robots.txt disallows this page"), RuntimeError("render died")):
        ctx2 = _ctx(db_session, crawler=FakeCrawler(error=error))
        assert T.kosovo_site_crawl_impl(ctx2, url="https://koha.net/a").startswith("page skipped")
    assert db_session.query(Source).filter_by(name="kosovo-sites").one().failure_count == 2


def test_tools_are_offered_only_when_configured(db_session, gap):
    plain = T.build_tools(_ctx(db_session, gap=gap))
    assert [t.name for t in plain] == list(T.TOOL_NAMES)
    full = T.build_tools(_ctx(db_session, gap=gap, apify=FakeApify(), crawler=FakeCrawler()))
    assert [t.name for t in full] == [*T.TOOL_NAMES, *T.SOCIAL_TOOL_NAMES, *T.CRAWL_TOOL_NAMES]
    assert T.instagram_search_impl(_ctx(db_session, gap=gap), query="x").startswith(
        "instagram_search unavailable"
    )
```

- [ ] **Step 6: Run the tests and lint**

Run: `TEST_DATABASE_URL=postgresql://scout:scout@localhost:55432/scout_test uv run pytest -q tests/test_social_tools.py tests/test_worker_tools.py`
Expected: all pass. `test_worker_tools.py` passes unchanged because its context has no `apify` or `crawler`.

Run: `uv run ruff format scout/worker tests/test_social_tools.py && uv run ruff check scout/worker tests/test_social_tools.py`

---

### Task 6: Profiles, planner, run wiring and the brief line

**Files:**
- Modify: `scout/worker/profiles.py` (verify-gap brief and iterations, new `ADS_SWEEP_BRIEF` and profile)
- Modify: `scout/director/planner.py` (`PRIORITY`, `PlannerState.social_enabled`, Monday sweep, `load_state`)
- Modify: `scout/director/run.py` (build the Apify and crawl clients, pass them to `ToolContext`, `load_state` and `write_brief`)
- Modify: `scout/editor/brief.py` (social-credit lines)
- Test: `tests/test_planner.py`, `tests/test_profiles.py`, `tests/test_brief.py` (add tests)

**Interfaces:**
- Consumes: `social_guard.resume_text`, `repo.apify_usd_in_month`, `ApifyClient`, `CrawlClient`, `crawl_available`
- Produces:
  - `load_state(..., social_enabled: bool = False)`
  - `write_brief(..., apify_cap_usd: Decimal | None = None)`
  - `collect_inputs(..., apify_cap_usd=None)`
  - `run_once(..., apify=None, crawler=None)`

- [ ] **Step 1: Update the verify-gap brief and add the sweep profile**

In `scout/worker/profiles.py`, `VERIFY_GAP_BRIEF`: after step 3 (the web queries), insert this new step. Then renumber the old steps 4–7 as 5–8.

```text
4. Social (Kosovo sells through Instagram and Facebook): run web_search with site:instagram.com,
   site:facebook.com and site:tiktok.com queries for the service in Albanian with a city name, to learn
   the words and page names local sellers use. Then, if these tools are offered: one instagram_search with
   the best keyword, one ad_library_search with the words a seller would put in an ad, and
   kosovo_site_crawl on Merrjep or KosovaJob pages with listings or prices. Paid social tools may refuse
   (score below 60, credit used up): then carry on without them. Ads (above all ones running 30+ days and
   foreign sellers shipping into Kosovo) and comment questions about price or delivery are demand
   evidence; the tools save them for this gap.
```

In the same brief, in the verdicts sentence, add `instagram-only (sellers exist only as informal Instagram or Facebook pages, no shop or app)` after `offline-only (...)`.

Change the `verify-gap` profile's `max_iterations` from `14` to `18`.

Add this after `DEEP_DIVE_BRIEF`:

```python
ADS_SWEEP_BRIEF = """Date: {today}. Task: WEEKLY ADS SWEEP of the Meta Ad Library for Kosovo.

Goal: learn which consumer businesses pay to advertise to people in Kosovo this week, and spot foreign
sellers serving Kosovo with no local equivalent.
Do, in order:
1. Call ad_library_search once with an empty query (all ads shown in Kosovo, up to 300). You get one call.
2. Group the ads by sector (use the existing sector slugs; kb_search if unsure). For each sector with
   ads, note how many advertisers there are, which ads run 30+ days (a sign they pay off), and which
   sellers are foreign and ship into Kosovo.
3. Save one fact per sector with kb_record_fact: entity_type "ad_signal", entity_key the sector slug,
   sector set, ttl_days 14, value_json {{"advertisers": n, "long_running": n, "foreign": n,
   "examples": ["page name", ...]}}.
4. When foreign sellers serve a need that no Kosovo business serves, propose it with kb_propose_gap
   (presence_level "unknown").
Businesses only: never record people.

Recent journal:
{journal_md}

{contract}"""
```

Add this to `PROFILES`:

```python
    "ads-sweep": Profile(
        "ads-sweep", "claude-sonnet-5-5", Decimal("0.20"), 8, 2, 2, 16000, "medium", ADS_SWEEP_BRIEF
    ),
```

- [ ] **Step 2: Plan the sweep on Mondays**

In `scout/director/planner.py`:
- Add `"ads-sweep": 65,` to `PRIORITY`.
- Add the field `social_enabled: bool = False` at the end of `PlannerState`.
- In `plan_tasks`, change the Monday fixture to:

```python
    if weekday == 0:
        add("chart-diff", {}, est=CHART_DIFF_EST)
        if state.social_enabled:
            add("ads-sweep", {})
```

Change the `load_state` signature to:

```python
def load_state(
    session,
    *,
    today: date,
    now: datetime,
    cap: Decimal,
    run_ids_today: list[int],
    social_enabled: bool = False,
) -> PlannerState:
```

Pass `social_enabled=social_enabled` into the returned `PlannerState(...)`.

- [ ] **Step 3: Wire the clients in the director**

In `scout/director/run.py`:

Imports:

```python
from scout.sources.apify import ApifyClient
from scout.sources.crawl import CrawlClient, crawl_available
```

`run_once` signature: add `apify: ApifyClient | None = None, crawler: CrawlClient | None = None,` right after `places: PlacesClient | None = None,`. In the body, after the `places` block, add:

```python
    if apify is None and settings.apify_token:
        apify = ApifyClient(settings.apify_token)
    if crawler is None and crawl_available():
        crawler = CrawlClient()
```

Pass `apify=apify, crawler=crawler,` into `_run_body(...)`, and add `apify, crawler,` to `_run_body`'s keyword-only parameters, after `places`.

In `_run_body`:
- Both `load_state(...)` calls gain `social_enabled=apify is not None`.
- `ToolContext(...)` gains:

```python
                        apify=apify,
                        crawler=crawler,
                        apify_monthly_usd=Decimal(settings.apify_monthly_usd),
```

- The `write_brief(...)` call gains:

```python
        apify_cap_usd=Decimal(settings.apify_monthly_usd) if apify is not None else None,
```

- [ ] **Step 4: Add the brief lines**

In `scout/editor/brief.py`:
- Import: `from scout.worker.social_guard import resume_text`
- Add two fields to `BriefInputs`, after `gap_titles`: `apify_usd: Decimal = Decimal("0")` and `apify_cap_usd: Decimal | None = None`.
- `collect_inputs` gains a keyword parameter `apify_cap_usd: Decimal | None = None`, and passes these to `BriefInputs(...)`:

```python
        apify_usd=repo.apify_usd_in_month(session, today),
        apify_cap_usd=apify_cap_usd,
```

Add this helper above `render_brief`:

```python
def _social_used_up(inputs: BriefInputs) -> str | None:
    if inputs.apify_cap_usd is None or inputs.apify_usd < inputs.apify_cap_usd:
        return None
    return resume_text(inputs.today)
```

In `render_brief`, in the quiet-day branch, change `return line + "."` to:

```python
        used_up = _social_used_up(inputs)
        return line + "." + (f" {used_up}" if used_up else "")
```

In the `## Source health` block, after the Places line, add:

```python
    if inputs.apify_cap_usd is not None:
        lines.append(
            f"- Social credit: ${inputs.apify_usd:.2f} of ${inputs.apify_cap_usd:.2f} this month"
        )
        if used_up := _social_used_up(inputs):
            lines.append(f"- {used_up}")
```

`write_brief` gains a keyword parameter `apify_cap_usd: Decimal | None = None` and passes it to `collect_inputs(...)`.

- [ ] **Step 5: Write the tests**

Add to `tests/test_planner.py`:

```python
def test_ads_sweep_only_on_monday_with_a_token():
    assert "ads-sweep" in _profiles(P.plan_tasks(_state(social_enabled=True), "foundation"))
    assert "ads-sweep" not in _profiles(P.plan_tasks(_state(), "foundation"))
    tuesday = _state(social_enabled=True, today=MONDAY + timedelta(days=1))
    assert "ads-sweep" not in _profiles(P.plan_tasks(tuesday, "foundation"))
```

(If `MONDAY` or `timedelta` is not imported at the top of `tests/test_planner.py`, use the names the file already defines; `_state` already uses `MONDAY` and `timedelta`.)

Add to `tests/test_profiles.py`:

```python
def test_ads_sweep_profile_and_verify_social_step():
    from datetime import date

    from scout.worker.profiles import PROFILES, build_brief

    sweep = build_brief(PROFILES["ads-sweep"], {}, date(2026, 10, 19))
    assert "ad_library_search once with an empty query" in sweep and "{" not in sweep.split("value_json")[0]
    verify = build_brief(
        PROFILES["verify-gap"], {"gap_id": 3, "gap_title": "Cakes", "sector": "food"}, date(2026, 10, 19)
    )
    assert "instagram_search" in verify and "instagram-only" in verify
```

Add to `tests/test_brief.py`, a pure render test with no DB. Build `BriefInputs` directly:

```python
def test_social_credit_lines():
    from datetime import date
    from decimal import Decimal
    from types import SimpleNamespace

    from scout.editor.brief import BriefInputs, render_brief

    def inputs(usd, cap, fresh):
        return BriefInputs(
            run=SimpleNamespace(),
            today=date(2026, 10, 19),
            changes=[],
            fresh_facts=fresh,
            field_checks=[],
            tasks=[],
            chart_errors=[],
            spent_today=Decimal("0"),
            spent_mtd=Decimal("0"),
            cap=Decimal("1"),
            places_calls=0,
            apify_usd=Decimal(usd),
            apify_cap_usd=cap,
        )

    fact = SimpleNamespace(confidence=0.8, claim="c", source_url=None, source_name="web")
    md = render_brief(inputs("1.20", Decimal("4.50"), [fact]))
    assert "Social credit: $1.20 of $4.50 this month" in md and "used up" not in md
    md = render_brief(inputs("4.50", Decimal("4.50"), [fact]))
    assert "Social credit used up for October — paid social checks resume Nov 1." in md
    quiet = render_brief(inputs("4.60", Decimal("4.50"), []))
    assert quiet.startswith("Quiet day") and quiet.endswith("resume Nov 1.")
    assert "Social credit" not in render_brief(inputs("0", None, [fact]))
```

- [ ] **Step 6: Run the tests and lint**

Run: `TEST_DATABASE_URL=postgresql://scout:scout@localhost:55432/scout_test uv run pytest -q tests/test_planner.py tests/test_profiles.py tests/test_brief.py tests/test_run_once.py`
Expected: all pass. `test_run_once.py` covers the wiring and should pass unchanged.

Run: `uv run ruff format scout/worker/profiles.py scout/director scout/editor tests/test_planner.py tests/test_profiles.py tests/test_brief.py && uv run ruff check scout tests`

---

### Task 7: Dashboard

**Files:**
- Modify: `scout/web/pages/gaps.py` (`gap_detail`)
- Modify: `scout/web/templates/gap.html` (add a Social card after Scores)
- Modify: `scout/web/pages/costs.py`, `scout/web/templates/costs.html` (social-credit line)
- Test: `tests/test_web_gaps.py`, `tests/test_web_pages.py` (add tests)

**Interfaces:**
- Consumes: `repo.social_facts_for_gap`, `repo.ads_for_gap`, `repo.apify_usd_in_month`, `Settings.apify_monthly_usd`

- [ ] **Step 1: Gap page data**

In `scout/web/pages/gaps.py` `gap_detail`, before `return page(...)`, add:

```python
    social = repo.social_facts_for_gap(session, gap_id, now=datetime.now(UTC))
    shops: dict[str, dict] = {}
    questions = {"price": 0, "delivery": 0, "where": 0}
    for f in social:
        value = f.value if isinstance(f.value, dict) else {}
        for s in value.get("shops") or []:
            shops.setdefault(s.get("username", ""), s)
        for k, n in (value.get("questions") or {}).items():
            if k in questions:
                questions[k] += int(n or 0)
```

Pass these into `page(...)`:

```python
        shops=list(shops.values()),
        ads=repo.ads_for_gap(session, gap_id),
        questions=questions if any(questions.values()) else None,
```

- [ ] **Step 2: Gap page card**

In `scout/web/templates/gap.html`, insert this card after the Scores `</section>`:

```html
    <section class="card">
      <h2>{{ ui.icon("sparkles") }} Social</h2>
      {% if shops or ads or questions %}
        {% if shops %}
        <h3>Instagram shops</h3>
        <ul class="list">
          {% for s in shops %}
          <li><div class="grow"><strong>{{ s.name or s.username }}</strong>
            <div class="muted">@{{ s.username }} · {{ s.followers or 0 }} followers{% if s.last_post %} · last post {{ s.last_post }}{% endif %}</div>
          </div></li>
          {% endfor %}
        </ul>
        {% endif %}
        {% if ads %}
        <h3>Ads shown in Kosovo</h3>
        <ul class="list">
          {% for a in ads %}
          <li><div class="grow"><strong>{{ a.page_name or "Unknown advertiser" }}</strong>
            {% if a.is_foreign %}{{ ui.chip("Foreign seller", "amber") }}{% elif a.is_foreign == false %}{{ ui.chip("Local seller", "blue") }}{% else %}{{ ui.chip("Seller origin unknown") }}{% endif %}
            <div class="muted">Running since {{ ui.date(a.first_seen) }}{% if not a.is_active %} · stopped{% endif %}</div>
          </div></li>
          {% endfor %}
        </ul>
        {% endif %}
        {% if questions %}
        <p class="muted">People asked in comments: price {{ questions.price }} · delivery {{ questions.delivery }} · where to buy {{ questions.where }}</p>
        {% endif %}
      {% else %}
      <p class="muted">No social checks for this gap yet.</p>
      {% endif %}
    </section>
```

- [ ] **Step 3: Costs page line**

In `scout/web/pages/costs.py`, pass these into `page(...)`:

```python
        apify_used=repo.apify_usd_in_month(session, day),
        apify_cap=Decimal(settings.apify_monthly_usd),
```

In `scout/web/templates/costs.html`, inside the Spend card, right after the `<p>Today ...</p>` line, add:

```html
    <p>Social credit <strong>${{ "%.2f" | format(apify_used) }}</strong> of ${{ "%.2f" | format(apify_cap) }} used this month <span class="muted">(Apify free plan)</span></p>
```

- [ ] **Step 4: Write the tests**

Look at `tests/test_web_gaps.py` for how it creates a gap (helper or inline `repo.propose_gap`), and use the same pattern. Add:

```python
def test_gap_page_shows_the_social_card(web, db_session):
    from datetime import UTC, datetime

    from scout.db.repo import FactIn

    repo.get_or_create_sector(db_session, "food", "Food")
    gap, _ = repo.propose_gap(
        db_session,
        title="Cake delivery",
        sector_slug="food",
        proven_model_slug=None,
        hypothesis_md="",
        presence_level="instagram-only",
        why_not_yet_md="",
        run_id=None,
    )
    now = datetime.now(UTC)
    shop = {"username": "tortat.e.mira", "name": "Tortat e Mira", "followers": 5400,
            "category": "Bakery", "last_post": "2026-10-01", "url": "https://x"}
    for claim, value in (
        ("ig", {"shops": [shop], "questions": {"price": 2, "delivery": 1, "where": 0}}),
        ("old fact without value", None),
    ):
        repo.upsert_fact(
            db_session,
            FactIn(claim=claim, entity_type="social", entity_key=f"gap:{gap.id}", confidence=0.7,
                   value=value),
            run_id=None,
            observed_at=now,
        )
    repo.upsert_ads(
        db_session,
        [{"ad_archive_id": "222", "page_name": "Shopi AL", "page_url": None, "ad_text": "x",
          "platforms": ["instagram"], "first_seen": "2026-10-01", "last_seen": "2026-10-19",
          "is_active": True, "is_foreign": True, "link_url": "https://shopi.al"}],
        gap_id=gap.id,
        sector_slug="food",
        now=now,
    )
    html = web.get(f"/gaps/{gap.id}").text
    assert "Instagram shops" in html and "Tortat e Mira" in html and "5400 followers" in html
    assert "Shopi AL" in html and "Foreign seller" in html
    assert "price 2" in html and "Only on Instagram (informal)" in html


def test_gap_page_without_social_data(web, db_session):
    repo.get_or_create_sector(db_session, "food", "Food")
    gap, _ = repo.propose_gap(
        db_session, title="Cakes", sector_slug="food", proven_model_slug=None, hypothesis_md="",
        presence_level="unknown", why_not_yet_md="", run_id=None,
    )
    assert "No social checks for this gap yet." in web.get(f"/gaps/{gap.id}").text
```

Add to `tests/test_web_pages.py`:

```python
def test_costs_page_shows_social_credit(web, db_session):
    from datetime import UTC, datetime
    from decimal import Decimal
    from zoneinfo import ZoneInfo

    from scout.db import repo
    from scout.db.repo import CostRecord

    today = datetime.now(UTC).astimezone(ZoneInfo("Europe/Belgrade")).date()
    repo.record_cost(
        db_session,
        CostRecord("apify", "apify", "ads", {"usd": "1.25"}, Decimal("0")),
        day=today,
        run_id=None,
    )
    html = web.get("/costs").text
    assert "Social credit" in html and "$1.25" in html and "$4.50" in html
```

- [ ] **Step 5: Run the tests and lint**

Run: `TEST_DATABASE_URL=postgresql://scout:scout@localhost:55432/scout_test uv run pytest -q tests/test_web_gaps.py tests/test_web_pages.py tests/test_web_ui.py`
Expected: all pass.

Run: `uv run ruff format scout/web tests/test_web_gaps.py tests/test_web_pages.py && uv run ruff check scout/web tests`

---

### Task 8: Workflow, docs and live tests

**Files:**
- Modify: `.github/workflows/scout-daily.yml`
- Modify: `README.md` (Deployment section)
- Create: `tests/test_live_social.py`

- [ ] **Step 1: Workflow**

In `.github/workflows/scout-daily.yml`:
- Add to the job `env:` block: `SCOUT_APIFY_MONTHLY_USD: ${{ vars.SCOUT_APIFY_MONTHLY_USD || '4.50' }}`
- In the header comment's Variables line, add `SCOUT_APIFY_MONTHLY_USD (default 4.50)`.
- Replace `- run: uv sync --frozen --no-dev` with:

```yaml
      - run: uv sync --frozen --no-dev --extra crawl
      - name: Cache Chromium
        uses: actions/cache@v4
        with:
          path: ~/.cache/ms-playwright
          key: playwright-${{ runner.os }}-${{ hashFiles('uv.lock') }}
      - name: Install Chromium for Crawl4AI
        run: uv run playwright install --with-deps chromium
```

`render.yaml` stays as it is: the dashboard never crawls, so it does not install the `crawl` extra.

- [ ] **Step 2: README**

In `README.md` "Deployment", after the Secrets bullet, add:

```markdown
- Social eyes (optional, free): create a free Apify account (email only, no card), copy the API token
  from Apify Console → Settings → Integrations, and add it as the repo secret `APIFY_TOKEN`. The scout
  then checks Instagram shops and Meta ads for gaps scoring 60+ and runs a Monday ads sweep. It stops at
  `$4.50` of the ~$5 monthly free credit (repo variable `SCOUT_APIFY_MONTHLY_USD`). Without the token
  it runs as before. Kosovo sites (Merrjep, KosovaJob, news) are read with Crawl4AI in the workflow.
```

Then, in the Database setup bullet, change `run uv run scout init-db and uv run scout seed` so it also says to re-run both after pulling this change. Wording: "re-run both after pulling a new migration or seed row".

- [ ] **Step 3: Live tests (run by hand only)**

Create `tests/test_live_social.py`:

```python
"""Live checks for the social sources. Run by hand: uv run pytest tests/test_live_social.py -m network -v
Each Apify test spends about $0.01–0.05 of the free credit."""

import os
from datetime import date

import pytest

from scout.sources import social
from scout.sources.apify import ADS_ACTOR, INSTAGRAM_ACTOR, ApifyClient, ad_library_url
from scout.sources.crawl import CrawlClient, crawl_available

pytestmark = pytest.mark.network


@pytest.fixture
def apify():
    token = os.environ.get("APIFY_TOKEN")
    if not token:
        pytest.skip("APIFY_TOKEN not set")
    return ApifyClient(token)


def test_instagram_account_search(apify):
    res = apify.run(
        INSTAGRAM_ACTOR,
        {"search": "torta prishtine", "searchType": "user", "searchLimit": 5,
         "resultsType": "details", "resultsLimit": 5},
        max_items=5,
    )
    assert res.items, "no items: check the actor id and input fields"
    assert {"username", "isBusinessAccount", "followersCount"} <= set(res.items[0])
    print(social.instagram_summary(res.items), res.cost_usd)


def test_ad_library_kosovo(apify):
    res = apify.run(
        ADS_ACTOR,
        {"startUrls": [{"url": ad_library_url("")}], "resultsLimit": 5, "isDetailsPerAd": False},
        max_items=5,
    )
    assert res.items, "no items: check the actor id and input fields"
    out = social.ads_summary(res.items, today=date.today())
    assert out["count"] == len(res.items), f"unparsed ad keys: {sorted(res.items[0])}"
    print(out, res.cost_usd)


def test_crawl_merrjep():
    if not crawl_available():
        pytest.skip("crawl extra not installed")
    md = CrawlClient().fetch("https://www.merrjep.com/")
    assert len(md) > 200
```

- [ ] **Step 4: Lint**

Run: `uv run ruff format tests/test_live_social.py && uv run ruff check tests/test_live_social.py`

Do not run this file; the founder runs it by hand once the Apify account exists.

- [ ] **Step 5: Rollout checklist for the founder (not code)**

The founder does these after reviewing and committing:
1. Run `uv run scout init-db` and `uv run scout seed` locally against Neon, which adds the tables and the `kosovo-sites` row.
2. Push the branch; Render redeploys the dashboard.
3. Create a free Apify account and add the repo secret `APIFY_TOKEN`.
4. Run `uv sync --extra crawl && uv run playwright install chromium`, then `APIFY_TOKEN=... uv run pytest tests/test_live_social.py -m network -v` once. If a field name differs, fix `scout/sources/social.py`.
5. Start one run by hand from the Actions tab and read the brief's "Social credit" line.
