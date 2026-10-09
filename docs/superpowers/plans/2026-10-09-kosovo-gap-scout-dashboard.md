# Kosovo Gap Scout — Dashboard (M2, B11) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A password-protected, mobile-first web dashboard where the founder reads the daily brief and takes the hand actions (spec B11). It runs as the Render web service `scout-dashboard` over the same Neon database the cron job writes.

**Architecture:**
- `scout/founder.py` holds every founder action: change a gap's status, ask for verification, choose finalists, answer field checks, add or retry tasks, edit a digest, set the phase, set sector priority and set today's cap. The CLI and the dashboard both call it, and every action writes a line to the journal (spec A10).
- `scout/web/` is a FastAPI app with server-rendered Jinja2 pages and plain HTML forms. Each form posts and gets a 303 redirect back. Each page is one `APIRouter` module.
- Auth is a single `DASHBOARD_TOKEN` that sets an HttpOnly cookie.

**Tech Stack:** Python 3.12 · FastAPI · Jinja2 · uvicorn · python-multipart · markdown-it-py · SQLAlchemy 2 · pytest with `fastapi.testclient.TestClient` · Render web service.

**Spec:** `docs/superpowers/specs/2026-10-09-kosovo-gap-scout-design.md`. The relevant sections are B11 (dashboard), A10 (decision rules), B12 (field-check loop) and B16 (deployment).

## Global Constraints

- Python 3.12, managed with `uv`. Lint with `uv run ruff check -q && uv run ruff format --check -q` (line-length 100).
- Tests: `TEST_DATABASE_URL=postgresql://scout:scout@localhost:55432/scout_test uv run pytest -q`.
  - The default addopts deselect `network` tests.
  - DB tests carry `pytestmark = pytest.mark.db`.
- Never run network tests or call real APIs. Never put real secrets in committed files.
- Single user. Auth is the `DASHBOARD_TOKEN` env var:
  - The login page sets an HttpOnly cookie, and every route except `/login`, `/logout` and `/healthz` checks it.
  - If `DASHBOARD_TOKEN` is unset, every protected route returns 503.
- A founder change to a gap's status, the queue, a digest, the phase, a sector priority or today's cap goes through `scout/founder.py`, and each one appends a journal line (spec A10: "every change is journaled").
- Model-written Markdown is rendered with raw HTML disabled.
- "Verify" never sets `verified` by hand. It only flags the gap for one re-verification, because A10 sets the evidence rules for `verified`.
- The Ask page (LLM chat) is **out of scope**. It is deferred to M2b.
- Commit trailers on every commit:
  ```
  Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_01363MMeXh1CX8iLQ1mddmG7
  ```

## Review Focus

1. **Cross-site POSTs:** a state-changing form posted from another site must not act as the founder. The cookie is `SameSite=Lax`, so a cross-site POST carries no cookie. T1 pins the cookie flags.
2. **A `next=` redirect field pointing off-site** (`//evil.com`, `https://evil.com`) must redirect to `/`. T1 tests `local_path`.
3. **Bad founder input** (blank answer, cap `abc`/`NaN`/`-1`/`50`, unknown gap id, failed task that isn't failed) must show a readable error on the page, never a 500. T2 and T3–T5 test this.
4. **A `<script>` or `javascript:` link inside a brief or digest** must render as text, not run. T1 tests the `md` filter.
5. **An empty database** (first deploy: no brief, no runs, no costs) must still render every page with 200. Each page task has an empty-DB test.

---

## File structure

| File | Responsibility | Task |
|---|---|---|
| `pyproject.toml`, `uv.lock` | add fastapi, jinja2, uvicorn[standard], python-multipart, markdown-it-py | T1 |
| `scout/config.py` | `dashboard_token` setting (T1); `anthropic_api_key` optional (T6) | T1, T6 |
| `scout/clock.py` | `local_today(tz, now=None)` | T1 |
| `scout/web/__init__.py` | package marker | T1 |
| `scout/web/auth.py` | cookie HMAC, token compare, https detection | T1 |
| `scout/web/render.py` | safe Markdown → HTML filter `md` | T1 |
| `scout/web/deps.py` | `get_session`, `templates`, `page`, `back`, `local_day`, `local_path`, `NAV` | T1 |
| `scout/web/app.py` | `create_app(settings, session_factory)`: middleware auth, login/logout/healthz, includes every page router | T1 |
| `scout/web/main.py` | uvicorn entry `app` | T1 |
| `scout/web/pages/__init__.py` | package marker | T1 |
| `scout/web/pages/today.py` + `templates/today.html` | Today page, mark-read | T1 |
| `scout/web/pages/{gaps,field_checks,pipeline,knowledge,journal,costs,settings_page}.py` | **T1 creates each as a stub** (`router = APIRouter()`), later tasks fill them | T1 → T3/T4/T5 |
| `scout/web/templates/base.html`, `login.html` | layout, nav, CSS, flash messages | T1 |
| `scout/founder.py` | founder actions + journal + caps | T2 |
| `scout/cli.py` | refactored onto `scout.founder` | T2 |
| `scout/director/run.py` | cap from `founder.effective_cap` (founder's cap for today wins) | T2 |
| `scout/web/pages/gaps.py`, `field_checks.py` + templates | Gaps board/detail/actions; field-check answers | T3 |
| `scout/web/pages/pipeline.py`, `journal.py` + templates | queue/runs/failures/retry/add; journal | T4 |
| `scout/web/pages/knowledge.py`, `costs.py`, `settings_page.py` + templates | sectors/digests/facts; costs/cap/sources; phase/finalists/priorities | T5 |
| `render.yaml`, `README.md` | `scout-dashboard` web service, region frankfurt; docs | T6 |
| `tests/conftest.py` | `DASHBOARD_TOKEN` on `settings`; `web` fixture | T1 |
| `tests/test_web_app.py`, `tests/test_web_render.py` | T1 tests | T1 |
| `tests/test_founder.py` | T2 tests | T2 |
| `tests/test_web_gaps.py` | T3 tests | T3 |
| `tests/test_web_pipeline.py` | T4 tests | T4 |
| `tests/test_web_knowledge.py` | T5 tests | T5 |

**Execution waves:**
1. T1 ∥ T2. They share no files.
2. T3 ∥ T4 ∥ T5. Each fills only its own stub page modules, templates and test file.
3. T6.

Page tasks import `scout.founder` (T2) and `scout.web.deps` (T1), so wave 2 starts after both are merged.

---

### Task 1: Web skeleton, auth, Today page

**Files:**
- Modify: `pyproject.toml` (dependencies), `uv.lock`, `scout/config.py`, `tests/conftest.py`
- Create:
  - `scout/clock.py`
  - `scout/web/__init__.py`, `scout/web/auth.py`, `scout/web/render.py`, `scout/web/deps.py`, `scout/web/app.py`, `scout/web/main.py`
  - `scout/web/pages/__init__.py`, `scout/web/pages/today.py`, plus stubs `gaps.py`, `field_checks.py`, `pipeline.py`, `knowledge.py`, `journal.py`, `costs.py`, `settings_page.py`
  - `scout/web/templates/base.html`, `login.html`, `today.html`
- Test: `tests/test_web_render.py`, `tests/test_web_app.py`

**Interfaces:**
- Consumes (existing):
  - `scout.config.Settings`
  - `scout.db.repo`: `latest_brief`, `last_run`, `spent_on`, `spent_between`, `queued_tasks`, `open_field_checks`, `get_setting`, `set_setting`
  - `scout.db.base.make_engine`, `make_session_factory`
- Produces (later tasks rely on these exact names):
  - `scout.clock.local_today(tz: str, now: datetime | None = None) -> date`
  - `scout.web.deps`:
    - `get_session(request) -> Iterator[Session]`, a FastAPI dependency
    - `page(request, name: str, *, status_code: int = 200, **ctx) -> TemplateResponse`. It adds `msg`/`err` from the query string to ctx.
    - `back(url: str, *, msg: str | None = None, err: str | None = None) -> RedirectResponse`, a 303 redirect
    - `local_day(request) -> date`, Kosovo's local date
    - `local_path(url: str) -> str`, which returns `url` if it is a same-site path, else `"/"`
    - `templates`, a `Jinja2Templates` with filter `md` and global `NAV`
  - `scout.web.app.create_app(settings: Settings, session_factory) -> FastAPI`
  - Every page module exposes `router: APIRouter`.
  - `create_app` includes, in this order: `today, gaps, field_checks, pipeline, knowledge, journal, costs, settings_page`.
  - Test fixture `web`: a logged-in `TestClient` with base_url `https://testserver`. It depends on `db_session`, so every table is truncated first.
  - `settings.dashboard_token == "test-dashboard-token"` in tests.
  - Every template extends `base.html` and fills `{% block content %}`, and sets the page title with `{% block title %}`.

- [ ] **Step 1: Add dependencies**

In `pyproject.toml`, add these to `[project].dependencies`, after `"google-play-scraper>=1.2.7",`:

```toml
  "fastapi>=0.115",
  "jinja2>=3.1",
  "uvicorn[standard]>=0.30",
  "python-multipart>=0.0.9",
  "markdown-it-py>=3",
```

Run: `uv lock && uv sync --extra dev`
Expected: the lock file updates and install succeeds. This step reaches the package index; that is allowed, and it is not a network test.

- [ ] **Step 2: Settings field and test fixtures**

In `scout/config.py`, add this right after the `apify_token` line:

```python
    dashboard_token: str | None = Field(default=None, alias="DASHBOARD_TOKEN")
```

In `tests/conftest.py`:
- Add `DASHBOARD_TOKEN="test-dashboard-token",` to the `Settings(...)` call in the `settings` fixture, after `DATABASE_URL=test_db_url,`.
- Append this fixture:

```python
@pytest.fixture
def web(db_session, db_engine, settings):
    """A logged-in dashboard client over the (truncated) test database."""
    from fastapi.testclient import TestClient

    from scout.web.app import create_app

    client = TestClient(
        create_app(settings, make_session_factory(db_engine)), base_url="https://testserver"
    )
    r = client.post("/login", data={"token": settings.dashboard_token}, follow_redirects=False)
    assert r.status_code == 303
    return client
```

- [ ] **Step 3: Write the failing render/unit tests**

`tests/test_web_render.py`:

```python
from datetime import UTC, date, datetime

from scout.clock import local_today
from scout.web.auth import cookie_value, token_matches
from scout.web.deps import local_path
from scout.web.render import md


def test_md_renders_markdown_and_escapes_html():
    out = str(md("# Title\n\n<script>alert(1)</script>\n\n| a | b |\n|---|---|\n| 1 | 2 |"))
    assert "<h1>Title</h1>" in out
    assert "<script>" not in out and "&lt;script&gt;" in out
    assert "<table>" in out


def test_md_drops_javascript_links_and_handles_none():
    assert 'href="javascript:' not in str(md("[x](javascript:alert(1))"))
    assert str(md(None)) == ""


def test_cookie_value_is_stable_and_not_the_token():
    assert cookie_value("abc") == cookie_value("abc")
    assert cookie_value("abc") != cookie_value("abd")
    assert "abc" not in cookie_value("abc")
    assert token_matches("abc", "abc") and not token_matches("abc", "abd")


def test_local_path_only_allows_same_site_paths():
    assert local_path("/gaps?x=1") == "/gaps?x=1"
    for bad in ("//evil.com", "https://evil.com", "evil.com", "", "/\\evil.com"):
        assert local_path(bad) == "/"


def test_local_today_uses_the_kosovo_date():
    # 23:30 UTC on 2026-10-09 is already 2026-10-10 in Kosovo (CEST, UTC+2)
    now = datetime(2026, 10, 9, 23, 30, tzinfo=UTC)
    assert local_today("Europe/Belgrade", now) == date(2026, 10, 10)
```

Run: `uv run pytest tests/test_web_render.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'scout.clock'`.

- [ ] **Step 4: Implement clock, auth, render, deps**

`scout/clock.py`:

```python
"""Kosovo's calendar date. Days, caps and journal entries follow it, never the UTC date."""

from __future__ import annotations

from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo


def local_today(tz: str, now: datetime | None = None) -> date:
    return (now or datetime.now(UTC)).astimezone(ZoneInfo(tz)).date()
```

`scout/web/__init__.py`:

```python
"""The founder's dashboard (spec B11)."""
```

`scout/web/pages/__init__.py`:

```python
"""One APIRouter per dashboard page."""
```

`scout/web/auth.py`:

```python
"""Single-user login. The founder types DASHBOARD_TOKEN once, and an HttpOnly cookie then carries
an HMAC of it. The cookie never holds the token itself, and changing the token logs every browser
out."""

from __future__ import annotations

import hashlib
import hmac

from fastapi import Request

COOKIE = "scout_auth"
OPEN_PATHS = frozenset({"/login", "/logout", "/healthz"})
MAX_AGE = 60 * 60 * 24 * 30  # 30 days


def cookie_value(token: str) -> str:
    return hmac.new(token.encode(), b"scout-dashboard-v1", hashlib.sha256).hexdigest()


def token_matches(given: str, token: str) -> bool:
    return hmac.compare_digest(given.encode(), token.encode())


def is_logged_in(request: Request, token: str) -> bool:
    got = request.cookies.get(COOKIE, "")
    return hmac.compare_digest(got.encode(), cookie_value(token).encode())


def is_https(request: Request) -> bool:
    """Render terminates TLS and forwards plain HTTP with X-Forwarded-Proto: https."""
    return request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https"
```

`scout/web/render.py`:

```python
"""Safe Markdown for model-written text: raw HTML is escaped, and markdown-it drops javascript: links."""

from __future__ import annotations

from markdown_it import MarkdownIt
from markupsafe import Markup

_md = MarkdownIt("commonmark", {"html": False}).enable("table")


def md(text: str | None) -> Markup:
    return Markup(_md.render(text or ""))
```

`scout/web/deps.py`:

```python
"""Shared request helpers: DB session, templates, Kosovo's date, flash-message redirects."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date
from pathlib import Path
from urllib.parse import urlencode

from fastapi import Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from scout.clock import local_today
from scout.web.render import md

NAV = [
    ("/", "Today"),
    ("/gaps", "Gaps"),
    ("/field-checks", "Field checks"),
    ("/pipeline", "Pipeline"),
    ("/knowledge", "Knowledge"),
    ("/journal", "Journal"),
    ("/costs", "Costs"),
    ("/settings", "Settings"),
]

templates = Jinja2Templates(directory=Path(__file__).parent / "templates")
templates.env.filters["md"] = md
templates.env.globals["NAV"] = NAV


def get_session(request: Request) -> Iterator[Session]:
    session = request.app.state.session_factory()
    try:
        yield session
    finally:
        session.close()


def local_day(request: Request) -> date:
    return local_today(request.app.state.settings.timezone)


def page(request: Request, name: str, *, status_code: int = 200, **ctx):
    ctx = {"msg": request.query_params.get("msg"), "err": request.query_params.get("err"), **ctx}
    return templates.TemplateResponse(request, name, ctx, status_code=status_code)


def local_path(url: str) -> str:
    """Only same-site paths may be redirect targets (`next=` fields come from the browser)."""
    if url.startswith("/") and not url.startswith("//") and "\\" not in url:
        return url
    return "/"


def back(url: str, *, msg: str | None = None, err: str | None = None) -> RedirectResponse:
    params = {k: v for k, v in (("msg", msg), ("err", err)) if v}
    if params:
        url += ("&" if "?" in url else "?") + urlencode(params)
    return RedirectResponse(url, status_code=303)
```

Run: `uv run pytest tests/test_web_render.py -q`
Expected: PASS (5 passed).

- [ ] **Step 5: Write the failing app tests**

`tests/test_web_app.py`:

```python
import pytest
from fastapi.testclient import TestClient

from scout.db import repo
from scout.db.base import make_session_factory
from scout.web.app import create_app

pytestmark = pytest.mark.db


def _client(settings, db_engine, **overrides):
    s = settings.model_copy(update=overrides)
    return TestClient(create_app(s, make_session_factory(db_engine)), base_url="https://testserver")


def test_healthz_is_open_and_pages_need_login(db_session, db_engine, settings):
    c = _client(settings, db_engine)
    assert c.get("/healthz").text == "ok"
    r = c.get("/", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/login"
    assert c.get("/login").status_code == 200


def test_wrong_token_is_refused_without_a_cookie(db_session, db_engine, settings):
    c = _client(settings, db_engine)
    r = c.post("/login", data={"token": "nope"}, follow_redirects=False)
    assert r.status_code == 401 and "set-cookie" not in r.headers
    assert "Wrong token" in r.text


def test_login_sets_a_locked_down_cookie_and_logout_clears_it(db_session, db_engine, settings):
    c = _client(settings, db_engine)
    r = c.post("/login", data={"token": "test-dashboard-token"}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/"
    cookie = r.headers["set-cookie"].lower()
    assert "scout_auth=" in cookie and "httponly" in cookie
    assert "samesite=lax" in cookie and "secure" in cookie
    assert "test-dashboard-token" not in cookie
    assert c.get("/").status_code == 200
    c.post("/logout")
    assert c.get("/", follow_redirects=False).status_code == 303


def test_forged_cookie_is_refused(db_session, db_engine, settings):
    c = _client(settings, db_engine)
    c.cookies.set("scout_auth", "0" * 64)
    assert c.get("/", follow_redirects=False).status_code == 303


def test_unset_token_locks_the_dashboard(db_session, db_engine, settings):
    c = _client(settings, db_engine, dashboard_token=None)
    assert c.get("/").status_code == 503
    assert c.post("/login", data={"token": ""}).status_code == 503
    assert c.get("/healthz").status_code == 200


def test_today_with_an_empty_database(web):
    r = web.get("/")
    assert r.status_code == 200 and "No brief yet" in r.text
    for path, _ in [("/", "Today")]:
        assert web.get(path).status_code == 200


def test_today_renders_the_brief_and_mark_read(web, db_session):
    from datetime import date

    b = repo.save_brief(
        db_session, run_id=None, day=date(2026, 10, 9), markdown="# Big day\n\n<script>x</script>"
    )
    r = web.get("/")
    assert "<h1>Big day</h1>" in r.text and "&lt;script&gt;" in r.text and "New" in r.text
    r = web.post(f"/brief/{b.id}/read", follow_redirects=False)
    assert r.status_code == 303
    db_session.expire_all()
    assert repo.get_setting(db_session, "brief_read") == {"id": b.id}
    assert "badge-new" not in web.get("/").text
```

Run: `uv run pytest tests/test_web_app.py -q` (with `TEST_DATABASE_URL` set)
Expected: FAIL with `ModuleNotFoundError: No module named 'scout.web.app'`.

- [ ] **Step 6: Implement the app, the Today page, the stubs and the templates**

`scout/web/app.py`:

```python
"""The founder's dashboard (spec B11): server-rendered pages over the database the scout writes.
Forms post and redirect back (303). There is no JavaScript framework and no API surface."""

from __future__ import annotations

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse

from scout.config import Settings
from scout.web import auth
from scout.web.deps import page
from scout.web.pages import (
    costs,
    field_checks,
    gaps,
    journal,
    knowledge,
    pipeline,
    settings_page,
    today,
)

LOCKED = "DASHBOARD_TOKEN is not set; the dashboard is locked."


def create_app(settings: Settings, session_factory) -> FastAPI:
    app = FastAPI(title="Kosovo Gap Scout", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.settings = settings
    app.state.session_factory = session_factory

    @app.middleware("http")
    async def require_login(request: Request, call_next):
        if request.url.path in auth.OPEN_PATHS:
            return await call_next(request)
        if not settings.dashboard_token:
            return PlainTextResponse(LOCKED, status_code=503)
        if not auth.is_logged_in(request, settings.dashboard_token):
            return RedirectResponse("/login", status_code=303)
        return await call_next(request)

    @app.get("/healthz")
    def healthz():
        return PlainTextResponse("ok")

    @app.get("/login", response_class=HTMLResponse)
    def login_form(request: Request):
        return page(request, "login.html")

    @app.post("/login")
    def login(request: Request, token: str = Form("")):
        expected = settings.dashboard_token
        if not expected:
            return PlainTextResponse(LOCKED, status_code=503)
        if not auth.token_matches(token, expected):
            return page(request, "login.html", status_code=401, err="Wrong token.")
        resp = RedirectResponse("/", status_code=303)
        resp.set_cookie(
            auth.COOKIE,
            auth.cookie_value(expected),
            max_age=auth.MAX_AGE,
            httponly=True,
            samesite="lax",
            secure=auth.is_https(request),
        )
        return resp

    @app.post("/logout")
    def logout():
        resp = RedirectResponse("/login", status_code=303)
        resp.delete_cookie(auth.COOKIE)
        return resp

    for module in (today, gaps, field_checks, pipeline, knowledge, journal, costs, settings_page):
        app.include_router(module.router)
    return app
```

`scout/web/main.py`:

```python
"""uvicorn entry point: `uv run uvicorn scout.web.main:app`."""

from scout.config import get_settings
from scout.db.base import make_engine, make_session_factory
from scout.web.app import create_app

_settings = get_settings()
app = create_app(_settings, make_session_factory(make_engine(_settings.database_url)))
```

`scout/web/pages/today.py`:

```python
"""Today: the latest brief and a one-line status."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from scout.db import repo
from scout.web.deps import back, get_session, local_day, page

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
def today_page(request: Request, session: Session = Depends(get_session)):
    day = local_day(request)
    brief = repo.latest_brief(session)
    read_id = (repo.get_setting(session, "brief_read") or {}).get("id")
    return page(
        request,
        "today.html",
        brief=brief,
        unread=brief is not None and brief.id != read_id,
        last=repo.last_run(session),
        spent_today=repo.spent_on(session, day),
        spent_month=repo.spent_between(session, day.replace(day=1), day),
        queued=len(repo.queued_tasks(session)),
        open_checks=len(repo.open_field_checks(session)),
    )


@router.post("/brief/{brief_id}/read")
def mark_read(brief_id: int, session: Session = Depends(get_session)):
    repo.set_setting(session, "brief_read", {"id": brief_id})
    return back("/")
```

Stubs. Create each of these 7 files with exactly this content, changing only the docstring line:
- `gaps.py`: "Gaps board (Task 3)."
- `field_checks.py`: "Field checks (Task 3)."
- `pipeline.py`: "Pipeline (Task 4)."
- `journal.py`: "Journal (Task 4)."
- `knowledge.py`: "Knowledge (Task 5)."
- `costs.py`: "Costs (Task 5)."
- `settings_page.py`: "Settings (Task 5)."

```python
"""Gaps board (Task 3)."""

from fastapi import APIRouter

router = APIRouter()
```

`scout/web/templates/base.html`:

```html
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{% block title %}Scout{% endblock %} · Kosovo Gap Scout</title>
  <style>
    :root { --bg:#fafaf7; --fg:#1d1d1b; --muted:#6b6b66; --card:#ffffff; --line:#e4e2dc;
            --accent:#1f5fbf; --ok:#1f7a3d; --warn:#a15c00; --bad:#b3261e; }
    @media (prefers-color-scheme: dark) {
      :root { --bg:#141413; --fg:#ecebe6; --muted:#a3a29b; --card:#1e1e1c; --line:#33332f;
              --accent:#7fb0ff; --ok:#6fcf8f; --warn:#f0b35a; --bad:#ff8a80; }
    }
    * { box-sizing:border-box; }
    body { margin:0; background:var(--bg); color:var(--fg);
           font:16px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif; }
    header { position:sticky; top:0; background:var(--card); border-bottom:1px solid var(--line);
             padding:8px 16px; z-index:1; }
    nav { display:flex; gap:4px; overflow-x:auto; white-space:nowrap; }
    nav a { padding:6px 10px; border-radius:6px; color:var(--fg); text-decoration:none; }
    nav a.on { background:var(--accent); color:#fff; }
    main { max-width:860px; margin:0 auto; padding:16px; }
    a { color:var(--accent); }
    h1 { font-size:1.4rem; } h2 { font-size:1.15rem; margin-top:1.6em; }
    .card { background:var(--card); border:1px solid var(--line); border-radius:10px;
            padding:12px 14px; margin:10px 0; overflow-wrap:anywhere; }
    .muted { color:var(--muted); font-size:.9rem; }
    .row { display:flex; flex-wrap:wrap; gap:6px; align-items:center; }
    .flash { padding:10px 12px; border-radius:8px; margin:10px 0; }
    .flash.ok { background:color-mix(in srgb, var(--ok) 15%, transparent); }
    .flash.err { background:color-mix(in srgb, var(--bad) 15%, transparent); }
    .badge { display:inline-block; padding:1px 8px; border-radius:99px; font-size:.8rem;
             border:1px solid var(--line); }
    .badge-new { background:var(--accent); color:#fff; border-color:var(--accent); }
    button, .btn { font:inherit; padding:6px 12px; border-radius:8px; border:1px solid var(--line);
                   background:var(--card); color:var(--fg); cursor:pointer; }
    button.primary { background:var(--accent); color:#fff; border-color:var(--accent); }
    button.danger { color:var(--bad); }
    form.inline { display:inline; }
    input, select, textarea { font:inherit; padding:6px 8px; border-radius:8px;
                              border:1px solid var(--line); background:var(--bg); color:var(--fg);
                              max-width:100%; }
    textarea { width:100%; min-height:6em; }
    table { border-collapse:collapse; width:100%; display:block; overflow-x:auto; }
    th, td { text-align:left; padding:6px 8px; border-bottom:1px solid var(--line);
             vertical-align:top; }
    details > summary { cursor:pointer; }
    .md img { max-width:100%; }
  </style>
</head>
<body>
  {% if not hide_nav %}
  <header>
    <nav>
      {% for href, label in NAV %}
        <a href="{{ href }}" class="{{ 'on' if request.url.path == href else '' }}">{{ label }}</a>
      {% endfor %}
      <form class="inline" method="post" action="/logout"><button>Log out</button></form>
    </nav>
  </header>
  {% endif %}
  <main>
    {% if msg %}<div class="flash ok">{{ msg }}</div>{% endif %}
    {% if err %}<div class="flash err">{{ err }}</div>{% endif %}
    {% block content %}{% endblock %}
  </main>
</body>
</html>
```

`scout/web/templates/login.html`:

```html
{% extends "base.html" %}
{% set hide_nav = True %}
{% block title %}Log in{% endblock %}
{% block content %}
<h1>Kosovo Gap Scout</h1>
<form method="post" action="/login" class="card">
  <label for="token">Dashboard token</label><br>
  <input id="token" name="token" type="password" autocomplete="current-password" required autofocus>
  <button class="primary">Log in</button>
</form>
{% endblock %}
```

`scout/web/templates/today.html`:

```html
{% extends "base.html" %}
{% block title %}Today{% endblock %}
{% block content %}
<p class="muted">
  Last run: {% if last %}{{ last.day }} · {{ last.status }}{% else %}none yet{% endif %}
  · spent today €{{ spent_today }} · month €{{ spent_month }}
  · <a href="/pipeline">{{ queued }} queued</a>
  · <a href="/field-checks">{{ open_checks }} field check{{ '' if open_checks == 1 else 's' }}</a>
  · <a href="/gaps">gaps →</a>
</p>
{% if brief %}
  <div class="row">
    <span class="muted">Brief for {{ brief.day }}</span>
    {% if unread %}
      <span class="badge badge-new">New</span>
      <form class="inline" method="post" action="/brief/{{ brief.id }}/read"><button>Mark read</button></form>
    {% endif %}
  </div>
  <article class="card md">{{ brief.markdown | md }}</article>
{% else %}
  <div class="card">No brief yet. The first one appears after the next run.</div>
{% endif %}
{% endblock %}
```

Note on `test_today_renders_the_brief_and_mark_read`: the CSS in `base.html` contains the text `.badge-new`, so `"badge-new" not in` would always fail. Fix this in the template, not the test: the unread badge uses `class="badge badge-new"`. Change the CSS selector to `.badge.new-brief` and the badge element to `<span class="badge new-brief">New</span>`. Then edit the test's last assertion to `assert "new-brief\">New" not in web.get("/").text`. Do both edits.

Run: `uv run pytest tests/test_web_app.py tests/test_web_render.py -q`
Expected: PASS.

- [ ] **Step 7: Full suite, lint, commit**

Run: `uv run pytest -q && uv run ruff check -q && uv run ruff format --check -q`
Expected: all pass. Run `uv run ruff format` if formatting differs.

```bash
git add pyproject.toml uv.lock scout/config.py scout/clock.py scout/web tests/conftest.py tests/test_web_app.py tests/test_web_render.py
git commit -m "feat(web): dashboard skeleton, token login, Today page"
```

---

### Task 2: Founder actions module, CLI refactor, founder cap in the run

**Files:**
- Create: `scout/founder.py`
- Modify: `scout/cli.py` (add-task, field-check answer, flag-gap, set-phase delegate to `scout.founder`), `scout/director/run.py:178-182` (cap)
- Test: `tests/test_founder.py`, `tests/test_run_once.py` (one new test)

**Interfaces:**
- Consumes (existing):
  - `scout.db.repo`: `get_gap`, `get_sector`, `list_sectors`, `get_setting`, `set_setting`, `enqueue_task`, `upsert_fact`, `FactIn`, `answer_field_check`, `set_digest`
  - `scout.db.models`: `Digest`, `FieldCheck`, `Gap`, `JournalEntry`, `Sector`, `Task`
  - `scout.director.planner`: `PHASES`, `PHASE_RULES` (`PHASE_RULES[phase]["cap"]` is a `Decimal`)
  - `scout.worker.profiles.PROFILES` (each value has `.est_cost_eur`)
- Produces (exact signatures used by T3–T5; every function commits):
  - `class FounderError(ValueError)`. Its message is safe to show to the founder.
  - `GAP_ACTIONS = {"park": "parked", "kill": "killed", "reopen": "candidate"}`
  - `TASK_PROFILES: tuple[str, ...]`, which is `(*PROFILES, "chart-diff")`
  - `MAX_TODAY_CAP_EUR = Decimal("10.00")`
  - `journal(session, *, today: date, line: str) -> None`
  - `flagged(session) -> list[int]` and `finalists(session) -> list[int]`
  - `set_gap_status(session, gap_id: int, action: str, *, today: date, now: datetime) -> Gap`
  - `flag_gap(session, gap_id: int, *, today: date, unflag: bool = False) -> list[int]`
  - `toggle_finalist(session, gap_id: int, *, today: date) -> list[int]`
  - `answer_field_check(session, check_id: int, answer: str, *, today: date, now: datetime) -> FieldCheck`
  - `add_task(session, profile: str, *, today: date, sector: str | None = None, gap_id: int | None = None, theme: str | None = None, priority: int = 70) -> Task`
  - `retry_task(session, task_id: int, *, today: date) -> Task`
  - `edit_digest(session, key: str, body_md: str, *, today: date, now: datetime) -> Digest`
  - `set_phase(session, phase: str, *, today: date) -> None`
  - `set_sector_priority(session, slug: str, priority: int, *, today: date) -> Sector`
  - `set_today_cap(session, eur: str | Decimal | None, *, today: date) -> Decimal | None`. Blank or `None` clears the cap.
  - `today_cap(session, today: date) -> Decimal | None`
  - `effective_cap(session, settings: Settings, phase: str, today: date) -> Decimal`
  - Settings keys:
    - `"finalists"`: sorted `list[int]`
    - `"cap:<YYYY-MM-DD>"`: `{"value": "1.50"}`, or `None` when cleared
    - `"flagged_gaps"`: unchanged from M1
  - Journal: one `JournalEntry` per day with `run_id = NULL`. Each action appends `- Founder: <line>` to its `did_md`.

- [ ] **Step 1: Write the failing tests**

`tests/test_founder.py`:

```python
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from scout import founder
from scout.db import repo
from scout.db.models import Digest, JournalEntry, Task
from scout.founder import FounderError
from scout.seeds import seed_all

pytestmark = pytest.mark.db
TODAY = date(2026, 10, 9)
NOW = datetime(2026, 10, 9, 12, 0, tzinfo=UTC)


@pytest.fixture
def gap(db_session):
    seed_all(db_session)
    g, _ = repo.propose_gap(db_session, title="Pet sitting", sector_slug="pets")
    return g


def _founder_journal(session) -> str:
    entries = session.query(JournalEntry).filter(JournalEntry.run_id.is_(None)).all()
    assert len(entries) == 1  # one founder entry per day, appended to
    return entries[0].did_md


def test_set_gap_status_park_kill_reopen_and_journal(db_session, gap):
    founder.toggle_finalist(db_session, gap.id, today=TODAY)
    founder.flag_gap(db_session, gap.id, today=TODAY)
    assert founder.set_gap_status(db_session, gap.id, "park", today=TODAY, now=NOW).status == "parked"
    assert founder.set_gap_status(db_session, gap.id, "kill", today=TODAY, now=NOW).status == "killed"
    assert founder.finalists(db_session) == [] and founder.flagged(db_session) == []
    assert founder.set_gap_status(db_session, gap.id, "reopen", today=TODAY, now=NOW).status == (
        "candidate"
    )
    did = _founder_journal(db_session)
    assert "- Founder: kill gap #" in did and "parked → killed" in did
    assert did.count("- Founder:") == 5


def test_set_gap_status_rejects_bad_input(db_session, gap):
    with pytest.raises(FounderError, match="action must be one of"):
        founder.set_gap_status(db_session, gap.id, "verify", today=TODAY, now=NOW)
    with pytest.raises(FounderError, match="unknown gap 999"):
        founder.set_gap_status(db_session, 999, "park", today=TODAY, now=NOW)


def test_flag_and_finalist_toggle(db_session, gap):
    assert founder.flag_gap(db_session, gap.id, today=TODAY) == [gap.id]
    assert founder.flag_gap(db_session, gap.id, today=TODAY, unflag=True) == []
    assert founder.toggle_finalist(db_session, gap.id, today=TODAY) == [gap.id]
    assert founder.toggle_finalist(db_session, gap.id, today=TODAY) == []
    founder.set_gap_status(db_session, gap.id, "kill", today=TODAY, now=NOW)
    with pytest.raises(FounderError, match="killed"):
        founder.toggle_finalist(db_session, gap.id, today=TODAY)
    with pytest.raises(FounderError, match="killed"):
        founder.flag_gap(db_session, gap.id, today=TODAY)


def test_answer_field_check(db_session, gap):
    fc = repo.add_field_check(db_session, gap_id=gap.id, question="Sitters?", why="w", due=TODAY)
    with pytest.raises(FounderError, match="empty"):
        founder.answer_field_check(db_session, fc.id, "   ", today=TODAY, now=NOW)
    done = founder.answer_field_check(db_session, fc.id, " None in Prizren ", today=TODAY, now=NOW)
    assert done.status != "open" and done.answer == "None in Prizren"
    task = repo.queued_tasks(db_session)[0]
    assert task.profile == "verify-gap" and task.priority == 90 and task.payload["gap_id"] == gap.id
    with pytest.raises(FounderError, match="no open field check"):
        founder.answer_field_check(db_session, fc.id, "again", today=TODAY, now=NOW)


def test_add_task_validates_and_marks_founder(db_session, gap):
    t = founder.add_task(db_session, "map-sector", today=TODAY, sector="pets", priority=80)
    assert t.payload == {"sector": "pets", "sector_name": "Pets (vets, sitting, supplies)", "founder": True}
    assert t.priority == 80
    g = founder.add_task(db_session, "verify-gap", today=TODAY, gap_id=gap.id)
    assert g.payload["gap_id"] == gap.id and g.payload["founder"] is True
    for kwargs, match in (
        ({"profile": "bogus"}, "profile must be one of"),
        ({"profile": "map-sector", "sector": "nope"}, "unknown sector nope"),
        ({"profile": "verify-gap", "gap_id": 999}, "unknown gap 999"),
        ({"profile": "map-sector", "priority": 101}, "priority"),
    ):
        with pytest.raises(FounderError, match=match):
            founder.add_task(db_session, today=TODAY, **kwargs)


def test_retry_task_requeues_only_failed_tasks(db_session):
    t = repo.enqueue_task(db_session, profile="news-scan", payload={}, priority=40)
    with pytest.raises(FounderError, match="not failed"):
        founder.retry_task(db_session, t.id, today=TODAY)
    t.status, t.attempts, t.error = "failed", 2, "boom"
    db_session.commit()
    r = founder.retry_task(db_session, t.id, today=TODAY)
    assert (r.status, r.attempts, r.error) == ("queued", 0, None)
    assert r.payload["founder"] is True
    assert db_session.get(Task, t.id).payload["founder"] is True


def test_edit_digest(db_session, gap):
    repo.set_digest(db_session, "sector:pets", "Pets", "old", now=NOW)
    d = founder.edit_digest(db_session, "sector:pets", "new body", today=TODAY, now=NOW)
    assert d.body_md == "new body" and db_session.get(Digest, "sector:pets").title == "Pets"
    with pytest.raises(FounderError, match="unknown digest"):
        founder.edit_digest(db_session, "sector:nope", "x", today=TODAY, now=NOW)


def test_set_phase_and_sector_priority(db_session, gap):
    founder.set_phase(db_session, "verification", today=TODAY)
    assert repo.get_setting(db_session, "phase") == {"value": "verification"}
    with pytest.raises(FounderError, match="phase must be one of"):
        founder.set_phase(db_session, "nonsense", today=TODAY)
    assert founder.set_sector_priority(db_session, "pets", 95, today=TODAY).priority == 95
    with pytest.raises(FounderError):
        founder.set_sector_priority(db_session, "pets", 500, today=TODAY)
    with pytest.raises(FounderError, match="unknown sector"):
        founder.set_sector_priority(db_session, "nope", 10, today=TODAY)


@pytest.mark.parametrize("bad", ["abc", "NaN", "-1", "10.01", "Infinity"])
def test_set_today_cap_rejects_bad_values(db_session, bad):
    with pytest.raises(FounderError):
        founder.set_today_cap(db_session, bad, today=TODAY)


def test_today_cap_and_effective_cap(db_session, settings):
    assert founder.effective_cap(db_session, settings, "foundation", TODAY) == min(
        Decimal("3.00"), settings.daily_budget_eur
    )
    assert founder.set_today_cap(db_session, "1.5", today=TODAY) == Decimal("1.50")
    assert repo.get_setting(db_session, "cap:2026-10-09") == {"value": "1.50"}
    assert founder.today_cap(db_session, TODAY) == Decimal("1.50")
    assert founder.today_cap(db_session, date(2026, 10, 10)) is None
    assert founder.effective_cap(db_session, settings, "foundation", TODAY) == Decimal("1.50")
    assert founder.set_today_cap(db_session, "", today=TODAY) is None
    assert founder.today_cap(db_session, TODAY) is None
```

Add this test to `tests/test_run_once.py`. Use that file's existing fixtures and fakes, and follow the pattern of an existing dry-run test there. The test must:
- seed;
- call `founder.set_today_cap(db_session, "0.40", today=<the day run_once uses>)`;
- run `run_once(..., dry_run=True)` without `budget_override`;
- assert that the created `Run.budget_cap_eur == Decimal("0.40")`;
- then run again with `budget_override=Decimal("0.70")` and assert that cap is `0.70`, because the explicit override wins.

Name it `test_founder_cap_for_today_sets_the_run_cap_and_override_wins`.

Run: `uv run pytest tests/test_founder.py -q`
Expected: FAIL with `ImportError: cannot import name 'founder' from 'scout'`.

- [ ] **Step 2: Implement `scout/founder.py`**

```python
"""Founder actions, shared by the CLI and the dashboard. Spec A10: hand changes go through here,
and every one is journaled. Founder lines go into one journal entry per day (run_id NULL), which the
scout reads back as memory."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from sqlalchemy import select
from sqlalchemy.orm import Session

from scout.config import Settings
from scout.db import repo
from scout.db.models import Digest, FieldCheck, Gap, JournalEntry, Sector, Task
from scout.db.repo import FactIn
from scout.director.planner import PHASE_RULES, PHASES
from scout.worker.profiles import PROFILES

GAP_ACTIONS = {"park": "parked", "kill": "killed", "reopen": "candidate"}
TASK_PROFILES: tuple[str, ...] = (*PROFILES, "chart-diff")
MAX_TODAY_CAP_EUR = Decimal("10.00")


class FounderError(ValueError):
    """A founder action was refused; the message is safe to show as-is."""


def journal(session: Session, *, today: date, line: str) -> None:
    entry = session.scalars(
        select(JournalEntry)
        .where(JournalEntry.run_id.is_(None), JournalEntry.day == today)
        .order_by(JournalEntry.id)
    ).first()
    if entry is None:
        entry = JournalEntry(run_id=None, day=today, did_md="", learned_md="", tomorrow_md="")
        session.add(entry)
    entry.did_md = f"{entry.did_md}\n- Founder: {line}".lstrip("\n")
    session.commit()


def _gap(session: Session, gap_id: int) -> Gap:
    gap = repo.get_gap(session, gap_id)
    if gap is None:
        raise FounderError(f"unknown gap {gap_id}")
    return gap


def _ids(session: Session, key: str) -> list[int]:
    return [int(i) for i in (repo.get_setting(session, key, []) or [])]


def flagged(session: Session) -> list[int]:
    return _ids(session, "flagged_gaps")


def finalists(session: Session) -> list[int]:
    return _ids(session, "finalists")


def set_gap_status(
    session: Session, gap_id: int, action: str, *, today: date, now: datetime
) -> Gap:
    if action not in GAP_ACTIONS:
        raise FounderError(f"action must be one of {', '.join(GAP_ACTIONS)}")
    gap = _gap(session, gap_id)
    old = gap.status
    gap.status = GAP_ACTIONS[action]
    gap.updated_at = now
    session.commit()
    if action == "kill":  # a killed gap is neither verified next nor a finalist
        repo.set_setting(session, "flagged_gaps", [g for g in flagged(session) if g != gap_id])
        repo.set_setting(session, "finalists", [g for g in finalists(session) if g != gap_id])
    journal(session, today=today, line=f'{action} gap #{gap.id} "{gap.title}" ({old} → {gap.status})')
    return gap


def flag_gap(session: Session, gap_id: int, *, today: date, unflag: bool = False) -> list[int]:
    """'Verify this': one flagged gap per day is verified first; the flag clears when it completes."""
    gap = _gap(session, gap_id)
    if not unflag and gap.status == "killed":
        raise FounderError("this gap is killed; reopen it before asking to verify it")
    current = flagged(session)
    ids = [g for g in current if g != gap_id] if unflag else sorted({*current, gap_id})
    repo.set_setting(session, "flagged_gaps", ids)
    verb = "withdrew verify request for" if unflag else "asked to verify"
    journal(session, today=today, line=f'{verb} gap #{gap.id} "{gap.title}"')
    return ids


def toggle_finalist(session: Session, gap_id: int, *, today: date) -> list[int]:
    gap = _gap(session, gap_id)
    current = finalists(session)
    if gap_id in current:
        ids, verb = [g for g in current if g != gap_id], "removed finalist"
    else:
        if gap.status == "killed":
            raise FounderError("a killed gap cannot be a finalist")
        ids, verb = sorted({*current, gap_id}), "chose as finalist"
    repo.set_setting(session, "finalists", ids)
    journal(session, today=today, line=f'{verb} gap #{gap.id} "{gap.title}"')
    return ids


def answer_field_check(
    session: Session, check_id: int, answer: str, *, today: date, now: datetime
) -> FieldCheck:
    """Spec B12: the answer becomes a fact (confidence 0.95, source founder), the check closes, and
    a verify-gap for its gap is queued at priority 90."""
    answer = answer.strip()
    if not answer:
        raise FounderError("the answer is empty")
    fc = session.get(FieldCheck, check_id)
    if fc is None or fc.status != "open":
        raise FounderError(f"no open field check #{check_id}")
    gap = repo.get_gap(session, fc.gap_id) if fc.gap_id else None
    sec = next((x for x in repo.list_sectors(session) if gap and x.id == gap.sector_id), None)
    repo.upsert_fact(
        session,
        FactIn(
            claim=f"Founder field check — Q: {fc.question} A: {answer}",
            entity_type="gap",
            entity_key=f"gap:{fc.gap_id}" if fc.gap_id else "general",
            confidence=0.95,
            sector_slug=sec.slug if sec else None,
            ttl_days=180,
            source_name="founder",
        ),
        run_id=None,
        observed_at=now,
    )
    repo.answer_field_check(session, fc, answer=answer, answered_at=now)
    if gap is not None:
        repo.enqueue_task(
            session,
            profile="verify-gap",
            priority=90,
            est_cost_eur=PROFILES["verify-gap"].est_cost_eur,
            payload={"gap_id": gap.id, "gap_title": gap.title, "sector": sec.slug if sec else ""},
        )
    journal(session, today=today, line=f"answered field check #{fc.id}: {fc.question} → {answer}")
    return fc


def add_task(
    session: Session,
    profile: str,
    *,
    today: date,
    sector: str | None = None,
    gap_id: int | None = None,
    theme: str | None = None,
    priority: int = 70,
) -> Task:
    if profile not in TASK_PROFILES:
        raise FounderError(f"profile must be one of {', '.join(TASK_PROFILES)}")
    if not 0 <= priority <= 100:
        raise FounderError("priority must be between 0 and 100")
    payload: dict = {}
    if sector:
        sec = repo.get_sector(session, sector)
        if sec is None:
            raise FounderError(f"unknown sector {sector}")
        payload = {"sector": sec.slug, "sector_name": sec.name_en}
    if gap_id is not None:
        gap = _gap(session, gap_id)
        sec = next((x for x in repo.list_sectors(session) if x.id == gap.sector_id), None)
        payload = {"gap_id": gap.id, "gap_title": gap.title, "sector": sec.slug if sec else ""}
    if theme:
        payload = {"theme": theme, "theme_name": theme.replace("-", " ")}
    payload["founder"] = True  # the director review never drops a task the founder queued
    est = PROFILES[profile].est_cost_eur if profile in PROFILES else Decimal("0.05")
    task = repo.enqueue_task(
        session, profile=profile, payload=payload, priority=priority, est_cost_eur=est
    )
    shown = {k: v for k, v in payload.items() if k != "founder"}
    journal(session, today=today, line=f"queued {profile} task #{task.id} {shown}")
    return task


def retry_task(session: Session, task_id: int, *, today: date) -> Task:
    task = session.get(Task, task_id)
    if task is None or task.status != "failed":
        raise FounderError(f"task #{task_id} is not failed")
    task.status, task.attempts, task.error, task.locked_by = "queued", 0, None, None
    task.payload = {**(task.payload or {}), "founder": True}  # new dict so the JSON change is saved
    session.commit()
    journal(session, today=today, line=f"retried {task.profile} task #{task.id}")
    return task


def edit_digest(session: Session, key: str, body_md: str, *, today: date, now: datetime) -> Digest:
    digest = session.get(Digest, key)
    if digest is None:
        raise FounderError(f"unknown digest {key}")
    saved = repo.set_digest(session, key, digest.title, body_md, now=now)
    journal(session, today=today, line=f"edited digest {key}")
    return saved


def set_phase(session: Session, phase: str, *, today: date) -> None:
    if phase not in PHASES:
        raise FounderError(f"phase must be one of {', '.join(PHASES)}")
    repo.set_setting(session, "phase", {"value": phase})
    journal(session, today=today, line=f"set phase to {phase}")


def set_sector_priority(session: Session, slug: str, priority: int, *, today: date) -> Sector:
    if not 0 <= priority <= 100:
        raise FounderError("priority must be between 0 and 100")
    sector = repo.get_sector(session, slug)
    if sector is None:
        raise FounderError(f"unknown sector {slug}")
    old, sector.priority = sector.priority, priority
    session.commit()
    journal(session, today=today, line=f"set sector {slug} priority {old} → {priority}")
    return sector


def _cap_key(today: date) -> str:
    return f"cap:{today.isoformat()}"


def set_today_cap(session: Session, eur: str | Decimal | None, *, today: date) -> Decimal | None:
    raw = "" if eur is None else str(eur).strip()
    if not raw:
        repo.set_setting(session, _cap_key(today), None)
        journal(session, today=today, line="cleared today's cap")
        return None
    try:
        value = Decimal(raw)
    except InvalidOperation:
        raise FounderError("the cap must be a number of euros, like 1.50") from None
    if not value.is_finite() or not Decimal("0") <= value <= MAX_TODAY_CAP_EUR:
        raise FounderError(f"the cap must be between €0 and €{MAX_TODAY_CAP_EUR}")
    value = value.quantize(Decimal("0.01"))
    repo.set_setting(session, _cap_key(today), {"value": str(value)})
    journal(session, today=today, line=f"set today's cap to €{value}")
    return value


def today_cap(session: Session, today: date) -> Decimal | None:
    v = repo.get_setting(session, _cap_key(today))
    return Decimal(v["value"]) if isinstance(v, dict) and v.get("value") is not None else None


def effective_cap(session: Session, settings: Settings, phase: str, today: date) -> Decimal:
    """The founder's cap for today if set; otherwise the phase cap limited by SCOUT_DAILY_BUDGET_EUR."""
    founder_cap = today_cap(session, today)
    if founder_cap is not None:
        return founder_cap
    return min(PHASE_RULES[phase]["cap"], Decimal(settings.daily_budget_eur))
```

Run: `uv run pytest tests/test_founder.py -q`
Expected: PASS. Ruff format may reflow long lines; let it.

- [ ] **Step 3: Use the founder cap in `run_once`**

In `scout/director/run.py`:
- Add the import `from scout.founder import effective_cap`.
- Replace the `cap = (...)` expression at lines 178–182 with:

```python
        cap = (
            Decimal(budget_override)
            if budget_override is not None
            else effective_cap(session, settings, phase, today)
        )
```

Run: `uv run pytest tests/test_run_once.py -q`
Expected: PASS, including the new test. If an import cycle appears, report it. Do not work around it. There should be none: `scout.founder` imports `scout.director.planner`, never `scout.director.run`.

- [ ] **Step 4: Refactor the CLI onto `scout.founder`**

In `scout/cli.py`, replace the bodies of four commands, `add-task`, `field-check answer`, `flag-gap` and `set-phase`, as shown below. Keep the signatures and docstrings. Remove the imports that become unused (`FieldCheck`, `FactIn`, `PHASES`, `PROFILES`). Run `ruff check` to confirm.

```python
from scout import founder
from scout.founder import FounderError
```

```python
@app.command("add-task")
def add_task(
    profile: str,
    sector: str | None = typer.Option(None),
    gap_id: int | None = typer.Option(None),
    theme: str | None = typer.Option(None),
    priority: int = typer.Option(70),
) -> None:
    """Queue a task for the next run."""
    settings = get_settings()
    with session_factory(settings)() as s:
        try:
            t = founder.add_task(
                s,
                profile,
                today=_local_today(settings),
                sector=sector,
                gap_id=gap_id,
                theme=theme,
                priority=priority,
            )
        except FounderError as e:
            raise typer.BadParameter(str(e)) from None
        console.print(f"queued task #{t.id} {profile} {t.payload}")


@field_check_app.command("answer")
def field_check_answer(check_id: int, answer: str) -> None:
    """Record the founder's answer as a high-confidence fact and re-queue verification of the gap."""
    settings = get_settings()
    with session_factory(settings)() as s:
        try:
            fc = founder.answer_field_check(
                s, check_id, answer, today=_local_today(settings), now=datetime.now(UTC)
            )
        except FounderError as e:
            raise typer.BadParameter(str(e)) from None
        console.print(
            f"answered #{check_id}; verify-gap queued" if fc.gap_id else f"answered #{check_id}"
        )


@app.command("flag-gap")
def flag_gap(gap_id: int, unflag: bool = typer.Option(False, "--unflag")) -> None:
    """(keep the existing docstring)"""
    settings = get_settings()
    with session_factory(settings)() as s:
        try:
            ids = founder.flag_gap(s, gap_id, today=_local_today(settings), unflag=unflag)
        except FounderError as e:
            raise typer.BadParameter(str(e)) from None
        console.print(f"flagged gaps: {ids}")


@app.command("set-phase")
def set_phase(phase: str) -> None:
    """Switch phase: foundation | verification | maintenance."""
    settings = get_settings()
    with session_factory(settings)() as s:
        try:
            founder.set_phase(s, phase, today=_local_today(settings))
        except FounderError as e:
            raise typer.BadParameter(str(e)) from None
        console.print(f"phase = {phase}")
```

Also add a new command after `set-phase`:

```python
@app.command("set-cap")
def set_cap(eur: str = typer.Argument("", help="EUR for today; empty clears")) -> None:
    """Set (or clear) today's spend cap; the next run uses it instead of the phase cap."""
    settings = get_settings()
    with session_factory(settings)() as s:
        try:
            value = founder.set_today_cap(s, eur, today=_local_today(settings))
        except FounderError as e:
            raise typer.BadParameter(str(e)) from None
        console.print(f"today's cap = €{value}" if value is not None else "today's cap cleared")
```

Add this test to `tests/test_cli.py`:

```python
def test_set_cap_and_cli_actions_are_journaled(db_session):
    from scout.db.models import JournalEntry

    assert runner.invoke(cli.app, ["set-cap", "1.25"]).exit_code == 0
    assert runner.invoke(cli.app, ["set-cap", "abc"]).exit_code != 0
    assert runner.invoke(cli.app, ["set-phase", "verification"]).exit_code == 0
    did = db_session.query(JournalEntry).filter(JournalEntry.run_id.is_(None)).one().did_md
    assert "set today's cap to €1.25" in did and "set phase to verification" in did
```

Run: `uv run pytest tests/test_cli.py tests/test_founder.py -q`
Expected: PASS, and the existing CLI tests are unchanged.

- [ ] **Step 5: Full suite, lint, commit**

Run: `uv run pytest -q && uv run ruff check -q && uv run ruff format --check -q`
Expected: all pass.

```bash
git add scout/founder.py scout/cli.py scout/director/run.py tests/test_founder.py tests/test_run_once.py tests/test_cli.py
git commit -m "feat: founder actions module (journaled), CLI on top of it, founder cap for today"
```

---

### Task 3: Gaps board and Field checks pages

**Files:**
- Modify (replace the T1 stubs): `scout/web/pages/gaps.py`, `scout/web/pages/field_checks.py`
- Create: `scout/web/templates/gaps.html`, `gap.html`, `field_checks.html`
- Test: `tests/test_web_gaps.py`

**Interfaces:**
- Consumes:
  - `scout.web.deps`: `get_session`, `page`, `back`, `local_day`, `local_path`
  - `scout.founder`: `set_gap_status`, `flag_gap`, `toggle_finalist`, `answer_field_check`, `finalists`, `flagged`, `FounderError`, `GAP_ACTIONS`
  - `scout.db.repo`: `list_gaps`, `list_sectors`, `get_gap`, `open_field_checks`
  - `scout.db.models`: `GapAssessment`, `FieldCheck`, `ProvenModel`
  - The `web` fixture
- Produces (Task 5's Settings page posts to these):
  - `POST /gaps/{id}/status` with form `action` ∈ {park, kill, reopen} and optional `next`
  - `POST /gaps/{id}/flag` with optional form `unflag=1` and `next`
  - `POST /gaps/{id}/finalist` with optional `next`
  - `GET /gaps`, `GET /gaps/{id}`
  - `GET /field-checks`, `POST /field-checks/{id}/answer` with form `answer`
  - Every POST redirects 303 to `local_path(next)` (default `/gaps`), with `msg` on success and `err` on `FounderError`.

- [ ] **Step 1: Write the failing tests**

`tests/test_web_gaps.py`:

```python
from datetime import date

import pytest

from scout import founder
from scout.db import repo
from scout.seeds import seed_all

pytestmark = pytest.mark.db


@pytest.fixture
def gap(db_session):
    seed_all(db_session)
    g, _ = repo.propose_gap(
        db_session, title="Pet sitting", sector_slug="pets", hypothesis_md="**bold** idea"
    )
    return g


def test_pages_render_on_an_empty_database(web):
    for path in ("/gaps", "/field-checks"):
        assert web.get(path).status_code == 200


def test_board_and_detail(web, gap):
    r = web.get("/gaps")
    assert "Pet sitting" in r.text and f'action="/gaps/{gap.id}/status"' in r.text
    d = web.get(f"/gaps/{gap.id}")
    assert d.status_code == 200 and "<strong>bold</strong>" in d.text
    assert web.get("/gaps/999").status_code == 404


def test_park_kill_reopen_buttons(web, gap, db_session):
    r = web.post(f"/gaps/{gap.id}/status", data={"action": "park"}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"].startswith("/gaps?msg=")
    db_session.expire_all()
    assert repo.get_gap(db_session, gap.id).status == "parked"
    web.post(f"/gaps/{gap.id}/status", data={"action": "kill", "next": f"/gaps/{gap.id}"})
    db_session.expire_all()
    assert repo.get_gap(db_session, gap.id).status == "killed"
    bad = web.post(f"/gaps/{gap.id}/status", data={"action": "verified"}, follow_redirects=False)
    assert bad.status_code == 303 and "err=" in bad.headers["location"]


def test_verify_and_finalist_buttons(web, gap, db_session):
    web.post(f"/gaps/{gap.id}/flag")
    web.post(f"/gaps/{gap.id}/finalist")
    db_session.expire_all()
    assert founder.flagged(db_session) == [gap.id] and founder.finalists(db_session) == [gap.id]
    assert "Finalist" in web.get("/gaps").text
    web.post(f"/gaps/{gap.id}/flag", data={"unflag": "1"})
    db_session.expire_all()
    assert founder.flagged(db_session) == []


def test_next_cannot_redirect_off_site(web, gap):
    r = web.post(
        f"/gaps/{gap.id}/flag", data={"next": "https://evil.com"}, follow_redirects=False
    )
    assert r.headers["location"].startswith("/?msg=")


def test_answer_field_check_from_the_page(web, gap, db_session):
    fc = repo.add_field_check(
        db_session, gap_id=gap.id, question="Sitters in Prizren?", why="w", due=date(2026, 10, 11)
    )
    assert "Sitters in Prizren?" in web.get("/field-checks").text
    empty = web.post(f"/field-checks/{fc.id}/answer", data={"answer": " "}, follow_redirects=False)
    assert "err=" in empty.headers["location"]
    ok = web.post(f"/field-checks/{fc.id}/answer", data={"answer": "Two vets, no sitters"})
    assert ok.status_code == 200 and "verify-gap queued" in ok.text
    db_session.expire_all()
    assert repo.open_field_checks(db_session) == []
    assert repo.queued_tasks(db_session)[0].profile == "verify-gap"
```

Run: `uv run pytest tests/test_web_gaps.py -q`
Expected: FAIL (404s, because the stubs have no routes).

- [ ] **Step 2: Implement `scout/web/pages/gaps.py`**

```python
"""Gaps board: status columns, detail, and the founder's Verify / Park / Kill / Finalist buttons."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from scout import founder
from scout.db import repo
from scout.db.models import FieldCheck, GapAssessment, ProvenModel
from scout.founder import FounderError
from scout.web.deps import back, get_session, local_day, local_path, page

router = APIRouter()
STATUS_ORDER = ("verified", "verifying", "candidate", "parked", "killed")


@router.get("/gaps", response_class=HTMLResponse)
def gaps_page(request: Request, session: Session = Depends(get_session)):
    all_gaps = repo.list_gaps(session)
    return page(
        request,
        "gaps.html",
        board=[(st, [g for g in all_gaps if g.status == st]) for st in STATUS_ORDER],
        sectors={s.id: s for s in repo.list_sectors(session)},
        finalists=set(founder.finalists(session)),
        flagged=set(founder.flagged(session)),
    )


@router.get("/gaps/{gap_id}", response_class=HTMLResponse)
def gap_detail(gap_id: int, request: Request, session: Session = Depends(get_session)):
    gap = repo.get_gap(session, gap_id)
    if gap is None:
        raise HTTPException(status_code=404, detail="no such gap")
    assessments = session.scalars(
        select(GapAssessment)
        .where(GapAssessment.gap_id == gap_id)
        .order_by(GapAssessment.id.desc())
        .limit(5)
    ).all()
    checks = session.scalars(
        select(FieldCheck).where(FieldCheck.gap_id == gap_id).order_by(FieldCheck.id.desc())
    ).all()
    model = session.get(ProvenModel, gap.proven_model_id) if gap.proven_model_id else None
    sector = next((s for s in repo.list_sectors(session) if s.id == gap.sector_id), None)
    return page(
        request,
        "gap.html",
        gap=gap,
        sector=sector,
        model=model,
        assessments=assessments,
        checks=checks,
        is_finalist=gap.id in founder.finalists(session),
        is_flagged=gap.id in founder.flagged(session),
    )


@router.post("/gaps/{gap_id}/status")
def gap_status(
    gap_id: int,
    request: Request,
    action: str = Form(""),
    next: str = Form("/gaps"),
    session: Session = Depends(get_session),
):
    try:
        gap = founder.set_gap_status(
            session, gap_id, action, today=local_day(request), now=datetime.now(UTC)
        )
    except FounderError as e:
        return back(local_path(next), err=str(e))
    return back(local_path(next), msg=f"{gap.title}: {gap.status}")


@router.post("/gaps/{gap_id}/flag")
def gap_flag(
    gap_id: int,
    request: Request,
    unflag: str = Form(""),
    next: str = Form("/gaps"),
    session: Session = Depends(get_session),
):
    try:
        founder.flag_gap(session, gap_id, today=local_day(request), unflag=unflag == "1")
    except FounderError as e:
        return back(local_path(next), err=str(e))
    return back(
        local_path(next),
        msg="Verify request withdrawn" if unflag == "1" else "Queued for re-verification",
    )


@router.post("/gaps/{gap_id}/finalist")
def gap_finalist(
    gap_id: int,
    request: Request,
    next: str = Form("/gaps"),
    session: Session = Depends(get_session),
):
    try:
        ids = founder.toggle_finalist(session, gap_id, today=local_day(request))
    except FounderError as e:
        return back(local_path(next), err=str(e))
    return back(local_path(next), msg="Finalist added" if gap_id in ids else "Finalist removed")
```

Python treats a parameter named `next` as shadowing the builtin. That is fine here, and ruff's default rule set (E, F, I, UP, B) does not flag it.

- [ ] **Step 3: Implement `scout/web/pages/field_checks.py`**

```python
"""Field checks: the founder's ≤ 5 open questions; an answer becomes a fact and re-queues verify-gap."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from scout import founder
from scout.db import repo
from scout.db.models import FieldCheck
from scout.founder import FounderError
from scout.web.deps import back, get_session, local_day, page

router = APIRouter()


@router.get("/field-checks", response_class=HTMLResponse)
def field_checks_page(request: Request, session: Session = Depends(get_session)):
    answered = session.scalars(
        select(FieldCheck)
        .where(FieldCheck.status != "open")
        .order_by(FieldCheck.answered_at.desc().nulls_last(), FieldCheck.id.desc())
        .limit(10)
    ).all()
    gaps = {g.id: g for g in repo.list_gaps(session)}
    return page(
        request,
        "field_checks.html",
        open_checks=repo.open_field_checks(session),
        answered=answered,
        gaps=gaps,
    )


@router.post("/field-checks/{check_id}/answer")
def answer(
    check_id: int, request: Request, answer: str = Form(""), session: Session = Depends(get_session)
):
    try:
        fc = founder.answer_field_check(
            session, check_id, answer, today=local_day(request), now=datetime.now(UTC)
        )
    except FounderError as e:
        return back("/field-checks", err=str(e))
    return back(
        "/field-checks", msg="Answered; verify-gap queued" if fc.gap_id else "Answered"
    )
```

- [ ] **Step 4: Templates**

`scout/web/templates/gaps.html`:

```html
{% extends "base.html" %}
{% block title %}Gaps{% endblock %}
{% block content %}
<h1>Gaps</h1>
{% for status, items in board %}
  {% if status == 'killed' %}<details><summary><h2 style="display:inline">Killed ({{ items|length }})</h2></summary>{% else %}
  <h2>{{ status|capitalize }} ({{ items|length }})</h2>{% endif %}
  {% for g in items %}
    <div class="card">
      <div class="row">
        <a href="/gaps/{{ g.id }}"><strong>{{ g.title }}</strong></a>
        {% if g.id in finalists %}<span class="badge">★ Finalist</span>{% endif %}
        {% if g.id in flagged %}<span class="badge">verify queued</span>{% endif %}
        {% if g.critic_flag %}<span class="badge">{{ g.critic_flag }}</span>{% endif %}
      </div>
      <div class="muted">
        {{ sectors[g.sector_id].name_en if g.sector_id in sectors else '' }}
        · score {{ g.score_total }} · conf {{ '%.2f'|format(g.confidence) }}
        · presence {{ g.presence_level }} · updated {{ g.updated_at.strftime('%Y-%m-%d') }}
      </div>
      {% set next = '/gaps' %}
      {% include "_gap_actions.html" %}
    </div>
  {% else %}
    <p class="muted">None.</p>
  {% endfor %}
  {% if status == 'killed' %}</details>{% endif %}
{% endfor %}
{% endblock %}
```

Also create `scout/web/templates/_gap_actions.html`. Both the board and the detail page use it, and Task 5's Settings page may use it too:

```html
<div class="row" style="margin-top:6px">
  {% if g.status != 'killed' %}
  <form class="inline" method="post" action="/gaps/{{ g.id }}/flag">
    <input type="hidden" name="next" value="{{ next }}">
    {% if g.id in flagged %}<input type="hidden" name="unflag" value="1"><button>Unverify</button>
    {% else %}<button>Verify</button>{% endif %}
  </form>
  <form class="inline" method="post" action="/gaps/{{ g.id }}/finalist">
    <input type="hidden" name="next" value="{{ next }}">
    <button>{{ 'Unfinalist' if g.id in finalists else 'Finalist' }}</button>
  </form>
  {% endif %}
  {% if g.status not in ('parked', 'killed') %}
  <form class="inline" method="post" action="/gaps/{{ g.id }}/status">
    <input type="hidden" name="next" value="{{ next }}"><input type="hidden" name="action" value="park">
    <button>Park</button>
  </form>
  {% endif %}
  {% if g.status != 'killed' %}
  <form class="inline" method="post" action="/gaps/{{ g.id }}/status"
        onsubmit="return confirm('Kill this gap? It stays killed until you reopen it.')">
    <input type="hidden" name="next" value="{{ next }}"><input type="hidden" name="action" value="kill">
    <button class="danger">Kill</button>
  </form>
  {% endif %}
  {% if g.status in ('parked', 'killed') %}
  <form class="inline" method="post" action="/gaps/{{ g.id }}/status">
    <input type="hidden" name="next" value="{{ next }}"><input type="hidden" name="action" value="reopen">
    <button>Reopen</button>
  </form>
  {% endif %}
</div>
```

The `test_board_and_detail` assertion `f'action="/gaps/{gap.id}/status"'` holds for a candidate gap, because a candidate shows Park.

`scout/web/templates/gap.html`:

```html
{% extends "base.html" %}
{% block title %}{{ gap.title }}{% endblock %}
{% block content %}
<p><a href="/gaps">← Gaps</a></p>
<h1>{{ gap.title }}</h1>
<p class="muted">
  {{ sector.name_en if sector else '' }} · <strong>{{ gap.status }}</strong>
  · score {{ gap.score_total }} · conf {{ '%.2f'|format(gap.confidence) }} · presence {{ gap.presence_level }}
  {% if gap.critic_flag %}· <span class="badge">{{ gap.critic_flag }}</span>{% endif %}
  {% if is_finalist %}· <span class="badge">★ Finalist</span>{% endif %}
</p>
{% set g = gap %}{% set next = '/gaps/' ~ gap.id %}
{% set finalists = [gap.id] if is_finalist else [] %}{% set flagged = [gap.id] if is_flagged else [] %}
{% include "_gap_actions.html" %}
<h2>Hypothesis</h2><div class="card md">{{ gap.hypothesis_md | md }}</div>
<h2>Why not yet</h2><div class="card md">{{ gap.why_not_yet_md | md }}</div>
<h2>Test plan</h2><div class="card md">{{ gap.test_plan_md | md }}</div>
{% if gap.score_components %}
<h2>Score</h2>
<table>{% for k, v in gap.score_components.items() %}<tr><th>{{ k }}</th><td>{{ v }}</td></tr>{% endfor %}</table>
{% endif %}
{% if model %}
<h2>Proven model</h2>
<div class="card"><strong>{{ model.name }}</strong> — {{ model.description }}
  <div class="muted">markets: {{ model.markets | join(', ') }}</div>
  {% for u in model.source_urls %}<div><a href="{{ u }}" rel="noopener noreferrer" target="_blank">{{ u }}</a></div>{% endfor %}
</div>
{% endif %}
<h2>Field checks</h2>
{% for fc in checks %}<div class="card">{{ fc.question }} — <em>{{ fc.status }}</em>{% if fc.answer %}: {{ fc.answer }}{% endif %}</div>
{% else %}<p class="muted">None.</p>{% endfor %}
<h2>Recent assessments</h2>
{% for a in assessments %}
  <details class="card"><summary>{{ a.created_at.strftime('%Y-%m-%d') }} · {{ a.model }} · score {{ a.score_total }} · conf {{ '%.2f'|format(a.confidence) }}</summary>
    <pre style="white-space:pre-wrap">{{ a.critic | tojson(indent=2) if a.critic else '' }}</pre>
  </details>
{% else %}<p class="muted">None yet.</p>{% endfor %}
{% endblock %}
```

A `javascript:` URL in `model.source_urls` would be clickable. Guard it in the template: wrap the `<a>` in `{% if u.startswith('http://') or u.startswith('https://') %}…{% else %}{{ u }}{% endif %}`.

`scout/web/templates/field_checks.html`:

```html
{% extends "base.html" %}
{% block title %}Field checks{% endblock %}
{% block content %}
<h1>Field checks</h1>
<p class="muted">Answer from what you know or one phone call (≤ 3 minutes each).</p>
{% for fc in open_checks %}
  <form class="card" method="post" action="/field-checks/{{ fc.id }}/answer">
    <div><strong>{{ fc.question }}</strong></div>
    <div class="muted">
      {% if fc.gap_id and fc.gap_id in gaps %}<a href="/gaps/{{ fc.gap_id }}">{{ gaps[fc.gap_id].title }}</a> · {% endif %}
      {% if fc.due %}due {{ fc.due }} · {% endif %}{{ fc.why }}
    </div>
    <textarea name="answer" required></textarea>
    <button class="primary">Answer</button>
  </form>
{% else %}
  <div class="card">No open field checks.</div>
{% endfor %}
{% if answered %}
<h2>Recently answered</h2>
{% for fc in answered %}
  <div class="card"><div>{{ fc.question }}</div><div class="muted">{{ fc.answer or fc.status }}</div></div>
{% endfor %}
{% endif %}
{% endblock %}
```

Run: `uv run pytest tests/test_web_gaps.py -q`
Expected: PASS.

- [ ] **Step 5: Full suite, lint, commit**

Run: `uv run pytest -q && uv run ruff check -q && uv run ruff format --check -q`

```bash
git add scout/web/pages/gaps.py scout/web/pages/field_checks.py scout/web/templates/gaps.html scout/web/templates/gap.html scout/web/templates/_gap_actions.html scout/web/templates/field_checks.html tests/test_web_gaps.py
git commit -m "feat(web): gaps board with verify/park/kill/finalist, field-check answers"
```

---

### Task 4: Pipeline and Journal pages

**Files:**
- Modify (replace the T1 stubs): `scout/web/pages/pipeline.py`, `scout/web/pages/journal.py`
- Create: `scout/web/templates/pipeline.html`, `journal.html`
- Test: `tests/test_web_pipeline.py`

**Interfaces:**
- Consumes:
  - `scout.web.deps`: `get_session`, `page`, `back`, `local_day`
  - `scout.founder`: `add_task`, `retry_task`, `TASK_PROFILES`, `FounderError`
  - `scout.db.repo`: `queued_tasks`, `last_run`, `tasks_for_run`, `list_sectors`, `latest_journal`
  - `scout.db.models`: `Run`, `Task`
- Produces:
  - `GET /pipeline`
  - `POST /tasks` with form fields `profile`, `sector`, `gap_id`, `theme`, `priority` (all strings; blank means not given)
  - `POST /tasks/{id}/retry`
  - `GET /journal`

- [ ] **Step 1: Write the failing tests**

`tests/test_web_pipeline.py`:

```python
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from scout.db import repo
from scout.seeds import seed_all

pytestmark = pytest.mark.db


def test_pages_render_on_an_empty_database(web):
    for path in ("/pipeline", "/journal"):
        assert web.get(path).status_code == 200


def test_add_task_from_the_form(web, db_session):
    seed_all(db_session)
    r = web.post(
        "/tasks",
        data={"profile": "map-sector", "sector": "pets", "gap_id": "", "theme": "", "priority": "80"},
    )
    assert r.status_code == 200 and "Queued task #" in r.text
    db_session.expire_all()
    t = repo.queued_tasks(db_session)[0]
    assert t.profile == "map-sector" and t.priority == 80 and t.payload["founder"] is True
    for data in (
        {"profile": "bogus"},
        {"profile": "verify-gap", "gap_id": "abc"},
        {"profile": "map-sector", "priority": "x"},
    ):
        bad = web.post("/tasks", data=data, follow_redirects=False)
        assert bad.status_code == 303 and "err=" in bad.headers["location"]


def test_queue_runs_failures_and_retry(web, db_session):
    run = repo.start_run(
        db_session,
        day=date(2026, 10, 9),
        phase="foundation",
        budget_cap_eur=Decimal("1.00"),
        started_at=datetime(2026, 10, 9, 6, tzinfo=UTC),
    )
    t = repo.enqueue_task(db_session, profile="news-scan", payload={}, priority=40, run_id=run.id)
    t.status, t.error = "failed", "boom: <b>bad</b>"
    db_session.commit()
    q = repo.enqueue_task(db_session, profile="culture", payload={"theme": "x"}, priority=30)
    r = web.get("/pipeline")
    assert f"#{q.id}" in r.text and "boom: &lt;b&gt;bad&lt;/b&gt;" in r.text and "foundation" in r.text
    web.post(f"/tasks/{t.id}/retry")
    db_session.expire_all()
    assert db_session.get(type(t), t.id).status == "queued"
    again = web.post(f"/tasks/{t.id}/retry", follow_redirects=False)
    assert "err=" in again.headers["location"]


def test_journal_shows_scout_and_founder_entries(web, db_session):
    repo.write_journal(
        db_session, run_id=1, day=date(2026, 10, 9), did_md="mapped **pets**", learned_md="l",
        tomorrow_md="t",
    )
    repo.write_journal(
        db_session, run_id=None, day=date(2026, 10, 9), did_md="- Founder: kill gap #1",
        learned_md="", tomorrow_md="",
    )
    r = web.get("/journal")
    assert "<strong>pets</strong>" in r.text and "Founder: kill gap #1" in r.text
    assert "Run #1" in r.text and "Founder" in r.text
```

Check `repo.start_run`'s real signature in `scout/db/repo.py` (around line 540). Adjust only the call in the test if the keyword names differ.

Run: `uv run pytest tests/test_web_pipeline.py -q`
Expected: FAIL (404).

- [ ] **Step 2: Implement `scout/web/pages/pipeline.py`**

```python
"""Pipeline: what ran, what is queued, what failed; retry and add tasks."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from scout import founder
from scout.db import repo
from scout.db.models import Run, Task
from scout.founder import FounderError
from scout.web.deps import back, get_session, local_day, page

router = APIRouter()


@router.get("/pipeline", response_class=HTMLResponse)
def pipeline_page(request: Request, session: Session = Depends(get_session)):
    last = repo.last_run(session)
    return page(
        request,
        "pipeline.html",
        queue=repo.queued_tasks(session),
        last=last,
        last_tasks=repo.tasks_for_run(session, last.id if last else None),
        runs=session.scalars(select(Run).order_by(Run.id.desc()).limit(14)).all(),
        failed=session.scalars(
            select(Task).where(Task.status == "failed").order_by(Task.id.desc()).limit(20)
        ).all(),
        profiles=founder.TASK_PROFILES,
        sectors=repo.list_sectors(session),
    )


def _int_or_none(raw: str, name: str) -> int | None:
    raw = raw.strip()
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        raise FounderError(f"{name} must be a whole number") from None


@router.post("/tasks")
def add_task(
    request: Request,
    profile: str = Form(""),
    sector: str = Form(""),
    gap_id: str = Form(""),
    theme: str = Form(""),
    priority: str = Form("70"),
    session: Session = Depends(get_session),
):
    try:
        task = founder.add_task(
            session,
            profile,
            today=local_day(request),
            sector=sector.strip() or None,
            gap_id=_int_or_none(gap_id, "gap id"),
            theme=theme.strip() or None,
            priority=_int_or_none(priority, "priority") or 0 if priority.strip() else 70,
        )
    except FounderError as e:
        return back("/pipeline", err=str(e))
    return back("/pipeline", msg=f"Queued task #{task.id} ({task.profile})")


@router.post("/tasks/{task_id}/retry")
def retry(task_id: int, request: Request, session: Session = Depends(get_session)):
    try:
        task = founder.retry_task(session, task_id, today=local_day(request))
    except FounderError as e:
        return back("/pipeline", err=str(e))
    return back("/pipeline", msg=f"Task #{task.id} re-queued")
```

The `priority=` expression above is hard to read. Replace it with this before the `founder.add_task` call, inside the `try:`:

```python
        prio = _int_or_none(priority, "priority")
```

and pass `priority=70 if prio is None else prio`.

- [ ] **Step 3: Implement `scout/web/pages/journal.py`**

```python
"""Journal: what the scout did, learned and plans, per day; founder actions appear as their own entry."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from scout.db import repo
from scout.web.deps import get_session, page

router = APIRouter()


@router.get("/journal", response_class=HTMLResponse)
def journal_page(request: Request, session: Session = Depends(get_session)):
    return page(request, "journal.html", entries=repo.latest_journal(session, limit=60))
```

- [ ] **Step 4: Templates**

`scout/web/templates/pipeline.html`:

```html
{% extends "base.html" %}
{% block title %}Pipeline{% endblock %}
{% block content %}
<h1>Pipeline</h1>

<h2>Add a task</h2>
<form class="card" method="post" action="/tasks">
  <div class="row">
    <select name="profile" required>{% for p in profiles %}<option value="{{ p }}">{{ p }}</option>{% endfor %}</select>
    <select name="sector"><option value="">(no sector)</option>{% for s in sectors %}<option value="{{ s.slug }}">{{ s.name_en }}</option>{% endfor %}</select>
    <input name="gap_id" inputmode="numeric" placeholder="gap id" size="6">
    <input name="theme" placeholder="culture theme" size="14">
    <input name="priority" inputmode="numeric" value="70" size="4" aria-label="priority">
    <button class="primary">Queue</button>
  </div>
  <div class="muted">map-sector/hunt-models take a sector; verify-gap/deep-dive take a gap id; culture takes a theme.</div>
</form>

<h2>Queue ({{ queue|length }})</h2>
{% for t in queue %}
  <div class="card">#{{ t.id }} <strong>{{ t.profile }}</strong> · prio {{ t.priority }} · est €{{ t.est_cost_eur }}
    <div class="muted">{{ t.payload }}</div></div>
{% else %}<p class="muted">Empty.</p>{% endfor %}

<h2>Last run</h2>
{% if last %}
  <div class="card">#{{ last.id }} · {{ last.day }} · {{ last.phase }} · {{ last.status }}
    · cap €{{ last.budget_cap_eur }} · spent €{{ last.spent_eur }} · done {{ last.tasks_done }} · failed {{ last.tasks_failed }}</div>
  {% for t in last_tasks %}
    <details class="card"><summary>#{{ t.id }} {{ t.profile }} · {{ t.status }} · €{{ t.actual_cost_eur }}</summary>
      {% if t.error %}<pre style="white-space:pre-wrap">{{ t.error }}</pre>{% endif %}
      <div class="md">{{ t.result_md | md }}</div>
    </details>
  {% endfor %}
{% else %}<p class="muted">No runs yet.</p>{% endif %}

<h2>Failures</h2>
{% for t in failed %}
  <div class="card">#{{ t.id }} <strong>{{ t.profile }}</strong> · attempts {{ t.attempts }}
    <pre style="white-space:pre-wrap">{{ t.error }}</pre>
    <form class="inline" method="post" action="/tasks/{{ t.id }}/retry"><button>Retry</button></form>
  </div>
{% else %}<p class="muted">None.</p>{% endfor %}

<h2>Recent runs</h2>
<table>
  <tr><th>#</th><th>day</th><th>phase</th><th>status</th><th>cap</th><th>spent</th><th>done</th><th>failed</th></tr>
  {% for r in runs %}
  <tr><td>{{ r.id }}</td><td>{{ r.day }}</td><td>{{ r.phase }}</td><td>{{ r.status }}</td>
      <td>€{{ r.budget_cap_eur }}</td><td>€{{ r.spent_eur }}</td><td>{{ r.tasks_done }}</td><td>{{ r.tasks_failed }}</td></tr>
  {% endfor %}
</table>
{% endblock %}
```

`scout/web/templates/journal.html`:

```html
{% extends "base.html" %}
{% block title %}Journal{% endblock %}
{% block content %}
<h1>Journal</h1>
{% for e in entries %}
  <div class="card">
    <div class="muted">{{ e.day }} · {% if e.run_id %}Run #{{ e.run_id }}{% else %}Founder{% endif %}</div>
    {% if e.did_md %}<div class="md"><strong>Did</strong>{{ e.did_md | md }}</div>{% endif %}
    {% if e.learned_md %}<div class="md"><strong>Learned</strong>{{ e.learned_md | md }}</div>{% endif %}
    {% if e.tomorrow_md %}<div class="md"><strong>Tomorrow</strong>{{ e.tomorrow_md | md }}</div>{% endif %}
  </div>
{% else %}<div class="card">Nothing yet.</div>{% endfor %}
{% endblock %}
```

Run: `uv run pytest tests/test_web_pipeline.py -q`
Expected: PASS.

- [ ] **Step 5: Full suite, lint, commit**

Run: `uv run pytest -q && uv run ruff check -q && uv run ruff format --check -q`

```bash
git add scout/web/pages/pipeline.py scout/web/pages/journal.py scout/web/templates/pipeline.html scout/web/templates/journal.html tests/test_web_pipeline.py
git commit -m "feat(web): pipeline (queue, runs, failures, retry, add task) and journal pages"
```

---

### Task 5: Knowledge, Costs and Settings pages

**Files:**
- Modify (replace the T1 stubs): `scout/web/pages/knowledge.py`, `scout/web/pages/costs.py`, `scout/web/pages/settings_page.py`
- Create: `scout/web/templates/knowledge.html`, `sector.html`, `digest.html`, `costs.html`, `settings.html`
- Test: `tests/test_web_knowledge.py`

**Interfaces:**
- Consumes:
  - `scout.web.deps`: `get_session`, `page`, `back`, `local_day`
  - `scout.founder`: `edit_digest`, `set_today_cap`, `today_cap`, `effective_cap`, `set_phase`, `set_sector_priority`, `finalists`, `flagged`, `FounderError`
  - `scout.db.repo`: `list_sectors`, `get_sector`, `list_businesses`, `list_gaps`, `search_facts`, `spent_on`, `spent_between`, `get_setting`, `get_gap`
  - `scout.db.models`: `Business`, `Cost`, `Digest`, `ProvenModel`, `Source`
  - `scout.director.planner.PHASES`
  - Task 3's routes: `POST /gaps/{id}/finalist` and `POST /gaps/{id}/flag` with `unflag=1`. Settings only links to them; the tests here do not post to them.
- Produces:
  - `GET /knowledge?q=`
  - `GET /knowledge/sectors/{slug}`
  - `GET` and `POST /knowledge/digests/{key}` with form `body_md`
  - `GET /costs` and `POST /costs/cap` with form `eur`
  - `GET /settings`
  - `POST /settings/phase` with form `phase`
  - `POST /settings/sector-priority` with forms `slug` and `priority`

- [ ] **Step 1: Write the failing tests**

`tests/test_web_knowledge.py`:

```python
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from scout import founder
from scout.db import repo
from scout.db.repo import CostRecord, FactIn
from scout.seeds import seed_all

pytestmark = pytest.mark.db
NOW = datetime(2026, 10, 9, 12, tzinfo=UTC)


def test_pages_render_on_an_empty_database(web):
    for path in ("/knowledge", "/costs", "/settings"):
        assert web.get(path).status_code == 200


def test_knowledge_sector_digest_and_fact_search(web, db_session):
    seed_all(db_session)
    repo.set_digest(db_session, "sector:pets", "Pets", "## Vets\n<script>x</script>", now=NOW)
    repo.upsert_business(db_session, sector_slug="pets", name="PetVet Prishtina", now=NOW)
    repo.upsert_fact(
        db_session,
        FactIn(claim="No pet sitting apps in Kosovo", entity_type="sector", entity_key="pets",
               confidence=0.7, sector_slug="pets"),
        run_id=None,
        observed_at=datetime.now(UTC),
    )
    assert "Pets (vets, sitting, supplies)" in web.get("/knowledge").text
    s = web.get("/knowledge/sectors/pets")
    assert "<h2>Vets</h2>" in s.text and "&lt;script&gt;" in s.text and "PetVet Prishtina" in s.text
    assert web.get("/knowledge/sectors/nope").status_code == 404
    assert "No pet sitting apps" in web.get("/knowledge", params={"q": "sitting apps"}).text
    r = web.post("/knowledge/digests/sector:pets", data={"body_md": "edited by founder"})
    assert r.status_code == 200 and "Saved" in r.text
    db_session.expire_all()
    assert repo.get_digest(db_session, "sector:pets") == "edited by founder"
    assert web.get("/knowledge/digests/sector:nope").status_code == 404


def test_costs_page_and_cap(web, db_session):
    today = founder_today = date.today()  # noqa: F841 — the page uses Kosovo's date; costs below use it
    from scout.clock import local_today

    day = local_today("Europe/Belgrade")
    repo.record_cost(
        db_session,
        CostRecord(kind="llm", provider="anthropic", model="claude-sonnet-5-5", units={},
                   cost_eur=Decimal("0.42")),
        day=day,
        run_id=None,
    )
    r = web.get("/costs")
    assert "claude-sonnet-5-5" in r.text and "0.42" in r.text
    ok = web.post("/costs/cap", data={"eur": "1.75"})
    assert ok.status_code == 200 and "1.75" in ok.text
    db_session.expire_all()
    assert founder.today_cap(db_session, day) == Decimal("1.75")
    bad = web.post("/costs/cap", data={"eur": "NaN"}, follow_redirects=False)
    assert "err=" in bad.headers["location"]


def test_settings_phase_priority_and_finalists(web, db_session):
    seed_all(db_session)
    g, _ = repo.propose_gap(db_session, title="Pet sitting", sector_slug="pets")
    founder.toggle_finalist(db_session, g.id, today=date(2026, 10, 9))
    r = web.get("/settings")
    assert "Pet sitting" in r.text and "foundation" in r.text
    web.post("/settings/phase", data={"phase": "verification"})
    db_session.expire_all()
    assert repo.get_setting(db_session, "phase") == {"value": "verification"}
    bad = web.post("/settings/phase", data={"phase": "x"}, follow_redirects=False)
    assert "err=" in bad.headers["location"]
    web.post("/settings/sector-priority", data={"slug": "pets", "priority": "99"})
    db_session.expire_all()
    assert repo.get_sector(db_session, "pets").priority == 99
    bad = web.post(
        "/settings/sector-priority", data={"slug": "pets", "priority": "lots"}, follow_redirects=False
    )
    assert "err=" in bad.headers["location"]
```

Before running, check the real signatures of `repo.upsert_business`, `repo.record_cost`/`CostRecord` and `FactIn` in `scout/db/repo.py`. Adjust only the test's calls if the field names differ. Delete the stray `today = founder_today = ...` line in `test_costs_page_and_cap`; it is noise.

Run: `uv run pytest tests/test_web_knowledge.py -q`
Expected: FAIL (404).

- [ ] **Step 2: Implement `scout/web/pages/knowledge.py`**

```python
"""Knowledge: sectors with digests, businesses and proven models; fact search; digest editing."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from scout import founder
from scout.db import repo
from scout.db.models import Business, Digest, ProvenModel
from scout.founder import FounderError
from scout.web.deps import back, get_session, local_day, page

router = APIRouter()


@router.get("/knowledge", response_class=HTMLResponse)
def knowledge_page(request: Request, q: str = "", session: Session = Depends(get_session)):
    counts = dict(
        session.execute(select(Business.sector_id, func.count()).group_by(Business.sector_id)).all()
    )
    models = dict(
        session.execute(
            select(ProvenModel.sector_id, func.count()).group_by(ProvenModel.sector_id)
        ).all()
    )
    other_digests = session.scalars(
        select(Digest).where(~Digest.key.startswith("sector:")).order_by(Digest.key)
    ).all()
    facts = repo.search_facts(session, q, now=datetime.now(UTC), limit=50) if q.strip() else []
    return page(
        request,
        "knowledge.html",
        sectors=sorted(repo.list_sectors(session), key=lambda s: (-s.priority, s.slug)),
        business_counts=counts,
        model_counts=models,
        other_digests=other_digests,
        q=q,
        facts=facts,
    )


@router.get("/knowledge/sectors/{slug}", response_class=HTMLResponse)
def sector_page(slug: str, request: Request, session: Session = Depends(get_session)):
    sector = repo.get_sector(session, slug)
    if sector is None:
        raise HTTPException(status_code=404, detail="no such sector")
    return page(
        request,
        "sector.html",
        sector=sector,
        digest=session.get(Digest, f"sector:{slug}"),
        businesses=repo.list_businesses(session, slug),
        models=session.scalars(
            select(ProvenModel).where(ProvenModel.sector_id == sector.id).order_by(ProvenModel.name)
        ).all(),
        gaps=repo.list_gaps(session, sector_slugs=[slug]),
    )


@router.get("/knowledge/digests/{key}", response_class=HTMLResponse)
def digest_page(key: str, request: Request, session: Session = Depends(get_session)):
    digest = session.get(Digest, key)
    if digest is None:
        raise HTTPException(status_code=404, detail="no such digest")
    return page(request, "digest.html", digest=digest)


@router.post("/knowledge/digests/{key}")
def digest_save(
    key: str, request: Request, body_md: str = Form(""), session: Session = Depends(get_session)
):
    try:
        founder.edit_digest(session, key, body_md, today=local_day(request), now=datetime.now(UTC))
    except FounderError as e:
        return back(f"/knowledge/digests/{key}", err=str(e))
    return back(f"/knowledge/digests/{key}", msg="Saved")
```

`POST` to an unknown digest redirects to its GET, which then returns 404. That is acceptable.

- [ ] **Step 3: Implement `scout/web/pages/costs.py`**

```python
"""Costs: spend per day and per model, today's cap, source health; the founder can set today's cap."""

from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from scout import founder
from scout.db import repo
from scout.db.models import Cost, Source
from scout.founder import FounderError
from scout.web.deps import back, get_session, local_day, page

router = APIRouter()


@router.get("/costs", response_class=HTMLResponse)
def costs_page(request: Request, session: Session = Depends(get_session)):
    settings = request.app.state.settings
    day = local_day(request)
    month_start = day.replace(day=1)
    total = func.sum(Cost.cost_eur)
    per_day = session.execute(
        select(Cost.day, total)
        .where(Cost.day >= day - timedelta(days=29))
        .group_by(Cost.day)
        .order_by(Cost.day.desc())
    ).all()
    per_model = session.execute(
        select(Cost.kind, Cost.provider, Cost.model, func.count(), total)
        .where(Cost.day >= month_start, Cost.day <= day)
        .group_by(Cost.kind, Cost.provider, Cost.model)
        .order_by(total.desc())
    ).all()
    phase = (repo.get_setting(session, "phase") or {}).get("value") or settings.phase
    return page(
        request,
        "costs.html",
        day=day,
        spent_today=repo.spent_on(session, day),
        spent_month=repo.spent_between(session, month_start, day),
        cap=founder.effective_cap(session, settings, phase, day),
        founder_cap=founder.today_cap(session, day),
        max_cap=founder.MAX_TODAY_CAP_EUR,
        per_day=per_day,
        per_model=per_model,
        sources=session.scalars(select(Source).order_by(Source.tier, Source.name)).all(),
    )


@router.post("/costs/cap")
def set_cap(request: Request, eur: str = Form(""), session: Session = Depends(get_session)):
    try:
        value = founder.set_today_cap(session, eur, today=local_day(request))
    except FounderError as e:
        return back("/costs", err=str(e))
    return back("/costs", msg=f"Today's cap: €{value}" if value is not None else "Today's cap cleared")
```

- [ ] **Step 4: Implement `scout/web/pages/settings_page.py`**

```python
"""Settings: phase, sector priorities, finalists and verify requests; read-only env settings."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from scout import founder
from scout.db import repo
from scout.director.planner import PHASES
from scout.founder import FounderError
from scout.web.deps import back, get_session, local_day, page

router = APIRouter()


@router.get("/settings", response_class=HTMLResponse)
def settings_view(request: Request, session: Session = Depends(get_session)):
    settings = request.app.state.settings

    def gaps_for(ids: list[int]):
        return [g for g in (repo.get_gap(session, i) for i in ids) if g is not None]

    return page(
        request,
        "settings.html",
        phase=(repo.get_setting(session, "phase") or {}).get("value") or settings.phase,
        phases=PHASES,
        sectors=sorted(repo.list_sectors(session), key=lambda s: (-s.priority, s.slug)),
        finalist_gaps=gaps_for(founder.finalists(session)),
        flagged_gaps=gaps_for(founder.flagged(session)),
        env={
            "SCOUT_DAILY_BUDGET_EUR": settings.daily_budget_eur,
            "SCOUT_TIMEZONE": settings.timezone,
            "SCOUT_DIRECTOR_REVIEW": settings.director_review,
            "Google Places key": "set" if settings.google_places_api_key else "missing",
            "Apify token": "set" if settings.apify_token else "missing",
        },
    )


@router.post("/settings/phase")
def set_phase(request: Request, phase: str = Form(""), session: Session = Depends(get_session)):
    try:
        founder.set_phase(session, phase, today=local_day(request))
    except FounderError as e:
        return back("/settings", err=str(e))
    return back("/settings", msg=f"Phase: {phase}")


@router.post("/settings/sector-priority")
def set_priority(
    request: Request,
    slug: str = Form(""),
    priority: str = Form(""),
    session: Session = Depends(get_session),
):
    try:
        try:
            value = int(priority.strip())
        except ValueError:
            raise FounderError("priority must be a whole number from 0 to 100") from None
        founder.set_sector_priority(session, slug, value, today=local_day(request))
    except FounderError as e:
        return back("/settings", err=str(e))
    return back("/settings", msg=f"{slug} priority: {value}")
```

- [ ] **Step 5: Templates**

`scout/web/templates/knowledge.html`:

```html
{% extends "base.html" %}
{% block title %}Knowledge{% endblock %}
{% block content %}
<h1>Knowledge</h1>
<form method="get" action="/knowledge" class="row">
  <input name="q" value="{{ q }}" placeholder="search facts (e.g. pet sitting Prizren)" style="flex:1">
  <button>Search</button>
</form>
{% if q %}
  <h2>Facts for “{{ q }}”</h2>
  {% for f in facts %}
    <div class="card">{{ f.claim }}
      <div class="muted">{{ f.entity_type }}:{{ f.entity_key }} · conf {{ '%.2f'|format(f.confidence) }} · {{ f.source_name }}
        · {{ f.observed_at.strftime('%Y-%m-%d') }}
        {% if f.source_url and (f.source_url.startswith('http://') or f.source_url.startswith('https://')) %}
          · <a href="{{ f.source_url }}" rel="noopener noreferrer" target="_blank">source</a>{% endif %}</div>
    </div>
  {% else %}<p class="muted">No matching facts.</p>{% endfor %}
{% endif %}
<h2>Sectors</h2>
<table>
  <tr><th>sector</th><th>status</th><th>prio</th><th>businesses</th><th>models</th><th>mapped</th></tr>
  {% for s in sectors %}
  <tr><td><a href="/knowledge/sectors/{{ s.slug }}">{{ s.name_en }}</a></td><td>{{ s.status }}</td><td>{{ s.priority }}</td>
      <td>{{ business_counts.get(s.id, 0) }}</td><td>{{ model_counts.get(s.id, 0) }}</td>
      <td>{{ s.last_mapped_at.strftime('%Y-%m-%d') if s.last_mapped_at else '—' }}</td></tr>
  {% endfor %}
</table>
<h2>Other digests</h2>
{% for d in other_digests %}<div><a href="/knowledge/digests/{{ d.key }}">{{ d.title }}</a> <span class="muted">{{ d.key }}</span></div>
{% else %}<p class="muted">None.</p>{% endfor %}
{% endblock %}
```

`scout/web/templates/sector.html`:

```html
{% extends "base.html" %}
{% block title %}{{ sector.name_en }}{% endblock %}
{% block content %}
<p><a href="/knowledge">← Knowledge</a></p>
<h1>{{ sector.name_en }}</h1>
<p class="muted">{{ sector.status }} · priority {{ sector.priority }} · presence {{ sector.presence_level or '—' }}</p>
<h2>Digest {% if digest %}<a class="muted" href="/knowledge/digests/{{ digest.key }}">edit</a>{% endif %}</h2>
{% if digest %}<div class="card md">{{ digest.body_md | md }}</div>{% else %}<p class="muted">Not mapped yet.</p>{% endif %}
<h2>Gaps</h2>
{% for g in gaps %}<div><a href="/gaps/{{ g.id }}">{{ g.title }}</a> <span class="muted">{{ g.status }} · {{ g.score_total }}</span></div>
{% else %}<p class="muted">None.</p>{% endfor %}
<h2>Businesses ({{ businesses|length }})</h2>
{% for b in businesses %}<div class="card"><strong>{{ b.name }}</strong> <span class="muted">{{ b.kind }}{% if b.city %} · {{ b.city }}{% endif %}</span>
  {% if b.note %}<div>{{ b.note }}</div>{% endif %}</div>
{% else %}<p class="muted">None.</p>{% endfor %}
<h2>Proven models ({{ models|length }})</h2>
{% for m in models %}<div class="card"><strong>{{ m.name }}</strong> — {{ m.description }}
  <div class="muted">markets: {{ m.markets | join(', ') }} · nearby {{ m.nearby_count }}</div></div>
{% else %}<p class="muted">None.</p>{% endfor %}
{% endblock %}
```

`scout/web/templates/digest.html`:

```html
{% extends "base.html" %}
{% block title %}{{ digest.title }}{% endblock %}
{% block content %}
<p><a href="/knowledge">← Knowledge</a></p>
<h1>{{ digest.title }}</h1>
<p class="muted">{{ digest.key }} · updated {{ digest.updated_at.strftime('%Y-%m-%d %H:%M') }} · ~{{ digest.token_estimate }} tokens</p>
<div class="card md">{{ digest.body_md | md }}</div>
<h2>Edit</h2>
<form method="post" action="/knowledge/digests/{{ digest.key }}">
  <textarea name="body_md" style="min-height:20em">{{ digest.body_md }}</textarea>
  <button class="primary">Save</button>
  <span class="muted">The scout reads this digest in every task on this sector; your edit is journaled.</span>
</form>
{% endblock %}
```

`scout/web/templates/costs.html`:

```html
{% extends "base.html" %}
{% block title %}Costs{% endblock %}
{% block content %}
<h1>Costs</h1>
<div class="card">
  Today ({{ day }}): <strong>€{{ spent_today }}</strong> of cap €{{ cap }}
  {% if founder_cap is not none %}<span class="badge">your cap</span>{% endif %}
  · month to date <strong>€{{ spent_month }}</strong>
</div>
<form class="card row" method="post" action="/costs/cap">
  <label for="eur">Cap for today (€0–{{ max_cap }}, blank clears)</label>
  <input id="eur" name="eur" inputmode="decimal" size="6" value="{{ founder_cap if founder_cap is not none else '' }}">
  <button class="primary">Set</button>
</form>
<h2>This month by model</h2>
<table>
  <tr><th>kind</th><th>provider</th><th>model</th><th>calls</th><th>€</th></tr>
  {% for kind, provider, model, n, eur in per_model %}
  <tr><td>{{ kind }}</td><td>{{ provider }}</td><td>{{ model or '—' }}</td><td>{{ n }}</td><td>{{ '%.4f'|format(eur) }}</td></tr>
  {% else %}<tr><td colspan="5" class="muted">No spend yet.</td></tr>{% endfor %}
</table>
<h2>Last 30 days</h2>
<table>
  <tr><th>day</th><th>€</th></tr>
  {% for d, eur in per_day %}<tr><td>{{ d }}</td><td>{{ '%.4f'|format(eur) }}</td></tr>
  {% else %}<tr><td colspan="2" class="muted">No spend yet.</td></tr>{% endfor %}
</table>
<h2>Source health</h2>
<table>
  <tr><th>tier</th><th>source</th><th>enabled</th><th>last ok</th><th>failures</th></tr>
  {% for s in sources %}
  <tr><td>{{ s.tier }}</td><td>{{ s.name }}</td><td>{{ 'yes' if s.enabled else 'no' }}</td>
      <td>{{ s.last_ok_at.strftime('%Y-%m-%d') if s.last_ok_at else '—' }}</td><td>{{ s.failure_count }}</td></tr>
  {% else %}<tr><td colspan="5" class="muted">No sources.</td></tr>{% endfor %}
</table>
{% endblock %}
```

`scout/web/templates/settings.html`:

```html
{% extends "base.html" %}
{% block title %}Settings{% endblock %}
{% block content %}
<h1>Settings</h1>
<h2>Phase</h2>
<form class="card row" method="post" action="/settings/phase">
  <select name="phase">{% for p in phases %}<option value="{{ p }}" {{ 'selected' if p == phase else '' }}>{{ p }}</option>{% endfor %}</select>
  <button class="primary">Save</button>
  <span class="muted">current: {{ phase }}</span>
</form>
<h2>Finalists</h2>
{% for g in finalist_gaps %}
  <div class="card row"><a href="/gaps/{{ g.id }}">{{ g.title }}</a> <span class="muted">{{ g.status }} · {{ g.score_total }}</span>
    <form class="inline" method="post" action="/gaps/{{ g.id }}/finalist"><input type="hidden" name="next" value="/settings"><button>Remove</button></form></div>
{% else %}<p class="muted">None chosen yet. Use “Finalist” on the Gaps page.</p>{% endfor %}
<h2>Verify requests</h2>
{% for g in flagged_gaps %}
  <div class="card row"><a href="/gaps/{{ g.id }}">{{ g.title }}</a>
    <form class="inline" method="post" action="/gaps/{{ g.id }}/flag"><input type="hidden" name="next" value="/settings"><input type="hidden" name="unflag" value="1"><button>Withdraw</button></form></div>
{% else %}<p class="muted">None.</p>{% endfor %}
<h2>Sector priorities</h2>
<table>
  {% for s in sectors %}
  <tr><td>{{ s.name_en }}</td><td>
    <form class="inline" method="post" action="/settings/sector-priority">
      <input type="hidden" name="slug" value="{{ s.slug }}">
      <input name="priority" value="{{ s.priority }}" size="3" inputmode="numeric" aria-label="priority for {{ s.name_en }}">
      <button>Save</button>
    </form></td></tr>
  {% endfor %}
</table>
<h2>Environment (set on Render)</h2>
<table>{% for k, v in env.items() %}<tr><th>{{ k }}</th><td>{{ v }}</td></tr>{% endfor %}</table>
{% endblock %}
```

Run: `uv run pytest tests/test_web_knowledge.py -q`
Expected: PASS.

- [ ] **Step 6: Full suite, lint, commit**

Run: `uv run pytest -q && uv run ruff check -q && uv run ruff format --check -q`

```bash
git add scout/web/pages/knowledge.py scout/web/pages/costs.py scout/web/pages/settings_page.py scout/web/templates/knowledge.html scout/web/templates/sector.html scout/web/templates/digest.html scout/web/templates/costs.html scout/web/templates/settings.html tests/test_web_knowledge.py
git commit -m "feat(web): knowledge (sectors, digests, fact search), costs with today's cap, settings"
```

---

### Task 6: Deployment config, optional Anthropic key for the dashboard, README

**Files:**
- Modify: `render.yaml`, `README.md`, `scout/config.py`, `scout/director/run.py`, `tests/test_config.py`

**Interfaces:**
- Consumes: everything above.
- Produces:
  - A `scout-dashboard` web service definition.
  - The dashboard boots without `ANTHROPIC_API_KEY`, so the key lives only on the cron job.
  - `run_once` refuses to start without the key.

- [ ] **Step 1: Failing test for the optional key**

Append to `tests/test_config.py`:

```python
def test_anthropic_key_is_optional_for_the_dashboard(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@h/db")
    s = Settings(_env_file=None)
    assert s.anthropic_api_key == "" and s.dashboard_token is None


def test_run_once_refuses_without_an_anthropic_key(monkeypatch):
    import pytest

    from scout.director.run import run_once

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    s = Settings(_env_file=None, DATABASE_URL="postgresql://u:p@h/db")
    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
        run_once(s, session_factory=lambda: None)
```

Run: `uv run pytest tests/test_config.py -q`
Expected: FAIL. The first test raises a validation error, because the field is required.

- [ ] **Step 2: Make the key optional and guard `run_once`**

In `scout/config.py`, change the key line to:

```python
    anthropic_api_key: str = Field(default="", alias="ANTHROPIC_API_KEY")  # the dashboard runs without it
```

In `scout/director/run.py`, make this the first statement of `run_once`'s body, before `clock = ...`:

```python
    if not settings.anthropic_api_key and client is None:
        raise RuntimeError("ANTHROPIC_API_KEY is not set; the scout cannot run without it")
```

Run: `uv run pytest tests/test_config.py tests/test_run_once.py -q`
Expected: PASS. The existing run tests pass `client=` fakes and the settings fixture carries `sk-test`, so they are unaffected.

- [ ] **Step 3: render.yaml**

Add `region: frankfurt` under the existing cron service's `plan: starter` line; Neon is in eu-central-1. Then append this service:

```yaml
  - type: web
    name: scout-dashboard
    runtime: python
    plan: free                     # sleeps after 15 min idle; first load ~30–60 s. Upgrade to starter to keep it warm.
    region: frankfurt
    buildCommand: pip install uv && uv sync --frozen --no-dev
    startCommand: uv run uvicorn scout.web.main:app --host 0.0.0.0 --port $PORT
    healthCheckPath: /healthz
    envVars:
      - key: PYTHON_VERSION
        value: "3.12"
      - key: DATABASE_URL
        sync: false
      - key: DASHBOARD_TOKEN       # long random string; you type it once per browser
        sync: false
      - key: SCOUT_PHASE
        value: foundation
      - key: SCOUT_DAILY_BUDGET_EUR
        value: "1.00"
      - key: SCOUT_TIMEZONE
        value: Europe/Belgrade
```

- [ ] **Step 4: README**

Add this section after "## Deployment (Render cron + Neon)":

````markdown
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
````

- [ ] **Step 5: Full suite, lint, commit**

Run: `uv run pytest -q && uv run ruff check -q && uv run ruff format --check -q`

```bash
git add render.yaml README.md scout/config.py scout/director/run.py tests/test_config.py
git commit -m "feat(deploy): scout-dashboard web service; dashboard runs without the Anthropic key"
```
