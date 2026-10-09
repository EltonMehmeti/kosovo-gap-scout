# Dashboard Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restyle the founder dashboard into a clean SaaS design with plain-language labels, five
sections, and a sidebar on wide screens or a bottom tab bar on phones. No behaviour changes.

**Architecture:**
- **Plain words:** a pure module `scout/web/ui.py` turns internal values (statuses, profiles,
  phases, scores, dates, money) into plain words with tones.
- **Shell:** a hand-written design system (`static/app.css`, `static/app.js`, the Inter font, a
  Lucide icon sprite) and Jinja macros (`templates/_ui.html`) give every page the same parts.
  `deps.page()` adds sidebar badges.
- **Pages:** each page is then rewritten on top of those parts. Every URL, form and field name
  stays the same.

**Tech Stack:** Python 3.12, FastAPI + Starlette `StaticFiles`, Jinja2 (autoescape on),
SQLAlchemy 2, pytest, ruff (line length 100). Plain CSS and vanilla JS, with no build step and no
CDN.

**Spec:** `docs/superpowers/specs/2026-10-09-dashboard-redesign-design.md`

## Global Constraints

- **Behaviour:**
  - No new founder actions and no scout behaviour change.
  - Every existing URL, form `action`, form field `name` and HTTP method stays exactly as it is.
- **Assets:**
  - No build step, no CDN, no external URL in any template.
  - Assets live only in `scout/web/static/`: `app.css`, `app.js`, `icons.svg` and `fonts/`. The
    fonts and icons are already committed.
- **Security:**
  - CSP stays `img-src 'self' data:`.
  - No inline event handlers (`onsubmit=`, `onclick=`, …) and no inline `<script>`.
  - Inline `style=` only for computed widths and heights of bars.
  - Autoescape stays on. Never apply `|safe` to database or model text. Markdown goes only
    through the `md` filter.
  - External links only after the existing http/https guard, with
    `rel="noopener noreferrer" target="_blank"`.
- **Wording:**
  - Templates show plain labels from `scout/web/ui.py` and never print raw
    status/profile/phase/presence values (except as form `value=`s).
  - Money uses the `eur` filter (`€0.00`). Dates use the `ui.date(...)` macro (human text, ISO
    tooltip).
- **Accessibility:**
  - visible focus rings;
  - `aria-current="page"` on the active nav and tab;
  - chips always carry text;
  - phone tap targets are at least 44px;
  - the sidebar is `<nav aria-label="Main">`.
- **Python:**
  - Python 3.12.
  - `uv run ruff check scout tests` and `uv run ruff format scout tests` must be clean (line
    length 100).
- **Tests:**
  - Test command: `TEST_DATABASE_URL=postgresql://scout:scout@localhost:55432/<db> uv run pytest -q`.
    The `<db>` is named in each task.
  - Never run `-m network`, never call a real API, never read or print `.env`.
- **Worktrees:** if you work in a worktree that forked from `main`, first run
  `git merge --ff-only feat/dashboard-redesign | cat` and then `uv sync --extra dev`. Append
  `| cat` to git commands.
- **Commit trailers:** every commit message ends with:
  ```
  Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_01363MMeXh1CX8iLQ1mddmG7
  ```
- **File ownership:**
  - Tasks 3–6 run in parallel and may touch **only the files their task lists**.
  - They never edit `ui.py`, `deps.py`, `app.py`, `auth.py`, `_ui.html`, `base.html`, `app.css`
    or `app.js`. If one of these needs a change, report it as a concern instead.

## Review Focus

1. **Junk `?status=` on `/gaps`** (an unknown word, `killed`, HTML). Expected: a 200 that falls
   back to the first non-empty column, with nothing unescaped. Owner: Task 4.
2. **The badge or phase lookup fails** (a DB hiccup while computing sidebar badges). Expected:
   the page still renders, just without badges. Owner: Task 2.
3. **Database values the labels don't know.** Examples: a run with status `dry-run`, a task with
   status `skipped`, an unknown status or profile. Expected: a gray chip with the raw word, never
   a 500. Owners: Task 1 (unit tests) and Task 5 (`dry-run` on `/pipeline`).
4. **Zero and tiny money.** Examples: today's cap is €0.00, or a cost is below one cent.
   Expected: no division error; tiny costs show `<€0.01`. Owners: Task 1 and Task 3.
5. **Model-written JSON in odd shapes.** Examples: critic lists, nested objects and nulls, or a
   gap that was never scored. Expected: readable output, "not scored yet", never a 500. Owner:
   Task 4.

---

## Execution waves

| Wave | Tasks | Mode | Test DB |
|---|---|---|---|
| 1 | Task 1, then Task 2 | sequential | `scout_test_t1` |
| 2 | Tasks 3, 4, 5, 6 | parallel worktrees, disjoint files | `scout_test_t2`…`t5` (Task 3→t2, 4→t3, 5→t4, 6→t5) |
| 3 | Task 7 | after wave 2 is merged into `feat/dashboard-redesign` | `scout_test` |

Every wave-2 page template starts with
`{% extends "base.html" %}{% import "_ui.html" as ui with context %}`. Task 2 provides both
files.

---

### Task 1: Plain-language helpers (`scout/web/ui.py`)

**Files:**
- Create: `scout/web/ui.py`
- Test: `tests/test_web_ui.py` (pure; no DB)

**Interfaces:**
- Consumes: nothing.
- Produces (Task 2 registers all of these in Jinja):
  - `Label(text, tone, tip)`, a frozen dataclass. Tones are `gray|blue|amber|green|red|indigo`.
  - Label lookups:
    - `status_label(s) -> Label` for gap statuses;
    - `task_label(s) -> Label`;
    - `run_label(s) -> Label`;
    - `flag_label(s) -> Label`;
    - `phase_info(p) -> Label`.
  - Plain names:
    - `profile_label(p) -> str`;
    - `presence_label(level) -> str`;
    - `task_target(payload) -> str`.
  - Scores and formatting:
    - `score_band(score: int | None) -> tuple[str, str]`;
    - `eur(x) -> str`;
    - `pct(x) -> str`;
    - `iso(d) -> str`.
  - Time:
    - `human_date(d, today, tz=DEFAULT_TZ) -> str`;
    - `greeting(now_local) -> str`;
    - `next_run_local(now_utc, tz) -> datetime`;
    - `next_run_text(now_utc, tz) -> str`.
  - Navigation:
    - `Section(key, label, icon, href, prefixes)`;
    - `SECTIONS`, a tuple of 5;
    - `SECTION_TABS: dict[str, tuple[tuple[str, str], ...]]`;
    - `active_section(path) -> str`.
  - Constants: `SCORE_PARTS` (tuples of key, label, max), `OPEN_GAP_STATUSES` and
    `DEFAULT_TZ`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_web_ui.py
from datetime import UTC, date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from scout.director.planner import PHASES
from scout.founder import TASK_PROFILES
from scout.web import ui

TZ = "Europe/Belgrade"
GAP_STATUSES = ("candidate", "verifying", "verified", "parked", "killed")


def test_gap_status_labels_tones_and_unknown_fallback():
    assert [ui.status_label(s).text for s in GAP_STATUSES] == [
        "New idea",
        "Being checked",
        "Confirmed gap",
        "On hold",
        "Rejected",
    ]
    assert [ui.status_label(s).tone for s in GAP_STATUSES] == [
        "blue",
        "amber",
        "green",
        "gray",
        "red",
    ]
    assert all(ui.status_label(s).tip for s in GAP_STATUSES)
    assert ui.status_label("weird") == ui.Label("weird", "gray", "")
    assert ui.status_label(None).text == "—"


def test_task_and_run_labels_cover_what_the_database_holds():
    assert [ui.task_label(s).text for s in ("queued", "running", "done", "failed", "skipped")] == [
        "Waiting",
        "Running",
        "Done",
        "Failed",
        "Skipped",
    ]
    assert ui.task_label("failed").tone == "red" and ui.task_label("queued").tone == "gray"
    runs = ("running", "done", "completed", "failed", "stopped", "dry-run")
    assert [ui.run_label(s).text for s in runs] == [
        "Running",
        "Finished",
        "Finished",
        "Failed",
        "Stopped",
        "Plan only",
    ]
    assert ui.run_label("exploded") == ui.Label("exploded", "gray", "")


def test_profiles_phases_flags_and_presence_have_plain_names():
    assert ui.profile_label("map-sector") == "Map a sector"
    assert ui.profile_label("hunt-models") == "Find proven models"
    assert ui.profile_label("verify-gap") == "Check a gap"
    assert ui.profile_label("brand-new") == "brand-new"
    assert all(ui.profile_label(p) != p for p in TASK_PROFILES)
    assert all(ui.phase_info(p).text == p.capitalize() and ui.phase_info(p).tip for p in PHASES)
    assert "€3/day" in ui.phase_info("foundation").tip
    assert ui.flag_label("critic-says-kill").tone == "red"
    assert ui.flag_label("odd-flag").text == "odd-flag"
    assert ui.presence_label("prishtina-only") == "Only in Prishtina"
    assert ui.presence_label(None) == "Not checked yet"
    assert ui.presence_label("galaxy-wide") == "galaxy-wide"


@pytest.mark.parametrize(
    ("score", "band"),
    [
        (None, ("not scored yet", "gray")),
        (0, ("poor", "red")),
        (39, ("poor", "red")),
        (40, ("weak", "amber")),
        (59, ("weak", "amber")),
        (60, ("promising", "blue")),
        (74, ("promising", "blue")),
        (75, ("strong", "green")),
        (100, ("strong", "green")),
    ],
)
def test_score_bands_at_the_boundaries(score, band):
    assert ui.score_band(score) == band


def test_money_and_percent():
    assert ui.eur(Decimal("0.42")) == "€0.42"
    assert ui.eur(Decimal("3")) == "€3.00"
    assert ui.eur(0) == "€0.00"
    assert ui.eur(Decimal("0.0042")) == "<€0.01"
    assert ui.eur(None) == "—"
    assert ui.pct(0.7) == "70%" and ui.pct(1) == "100%" and ui.pct(None) == "—"


def test_human_dates_and_iso_tooltips():
    today = date(2026, 10, 9)
    assert ui.human_date(today, today) == "today"
    assert ui.human_date(date(2026, 10, 8), today) == "yesterday"
    assert ui.human_date(date(2026, 10, 10), today) == "tomorrow"
    assert ui.human_date(date(2026, 10, 7), today) == "Oct 7"
    assert ui.human_date(date(2025, 12, 31), today) == "Dec 31, 2025"
    assert ui.human_date(None, today) == "—"
    late = datetime(2026, 10, 8, 23, 30, tzinfo=UTC)  # already Oct 9 in Kosovo
    assert ui.human_date(late, today, TZ) == "today"
    assert ui.iso(date(2026, 10, 7)) == "2026-10-07"
    assert ui.iso(late) == "2026-10-08T23:30+00:00"
    assert ui.iso(None) == ""


def test_greeting_follows_the_local_hour():
    tz = ZoneInfo(TZ)
    assert ui.greeting(datetime(2026, 10, 9, 8, tzinfo=tz)) == "Good morning"
    assert ui.greeting(datetime(2026, 10, 9, 13, tzinfo=tz)) == "Good afternoon"
    assert ui.greeting(datetime(2026, 10, 9, 19, tzinfo=tz)) == "Good evening"
    assert ui.greeting(datetime(2026, 10, 9, 2, tzinfo=tz)) == "Good evening"


def test_next_run_is_the_06_utc_cron_in_kosovo_time():
    before = datetime(2026, 12, 1, 5, 59, tzinfo=UTC)
    assert ui.next_run_local(before, TZ) == datetime(2026, 12, 1, 6, tzinfo=UTC)
    assert ui.next_run_text(before, TZ) == "Today 07:00"
    assert ui.next_run_text(datetime(2026, 12, 1, 6, 0, tzinfo=UTC), TZ) == "Tomorrow 07:00"
    assert ui.next_run_text(datetime(2026, 7, 1, 5, 0, tzinfo=UTC), TZ) == "Today 08:00"
    # Summer time ends overnight on Oct 25 2026: tomorrow's run is at 07:00, not 08:00.
    assert ui.next_run_text(datetime(2026, 10, 24, 12, tzinfo=UTC), TZ) == "Tomorrow 07:00"
    # 00:30 in Kosovo but still before the 06:00 UTC run: that run is "today" locally.
    assert ui.next_run_text(datetime(2026, 10, 9, 22, 30, tzinfo=UTC), TZ) == "Today 08:00"


def test_sections_tabs_and_the_active_section():
    assert [s.key for s in ui.SECTIONS] == ["home", "gaps", "activity", "knowledge", "settings"]
    cases = {
        "/": "home",
        "/gaps": "gaps",
        "/gaps/12": "gaps",
        "/field-checks": "gaps",
        "/pipeline": "activity",
        "/journal": "activity",
        "/knowledge/sectors/pets": "knowledge",
        "/settings": "settings",
        "/costs": "settings",
        "/gapsx": "home",
    }
    for path, key in cases.items():
        assert ui.active_section(path) == key, path
    assert ui.SECTION_TABS["settings"] == (("/settings", "General"), ("/costs", "Budget & costs"))
    assert ui.SECTION_TABS["gaps"] == (("/gaps", "Board"), ("/field-checks", "Field checks"))


def test_task_target_names_what_a_task_is_about():
    assert ui.task_target({"sector": "pets", "sector_name": "Pets"}) == "Pets"
    assert ui.task_target({"gap_id": 3, "gap_title": "Pet sitting", "sector": "pets"}) == (
        "Pet sitting"
    )
    assert ui.task_target({"gap_id": 3}) == "gap #3"
    assert ui.task_target({"theme": "weddings", "theme_name": "weddings"}) == "weddings"
    assert ui.task_target({}) == "" and ui.task_target(None) == ""


def test_score_parts_match_the_rubric_maxima():
    assert sum(top for _, _, top in ui.SCORE_PARTS) == 100
    assert [k for k, _, _ in ui.SCORE_PARTS] == ["proof", "absence", "demand", "founder_fit", "risk"]
```

- [ ] **Step 2: Run the tests and confirm they fail**

Run: `uv run pytest tests/test_web_ui.py -q`
Expected: FAIL with `ImportError: cannot import name 'ui' from 'scout.web'`.

- [ ] **Step 3: Write the implementation**

```python
# scout/web/ui.py
"""Plain words for the dashboard: labels, tones and tooltips for internal values, plus human dates
and money. Templates show these instead of raw database values (spec: understandability rules).
Pure functions only, so they are unit-tested without a database."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

DEFAULT_TZ = "Europe/Belgrade"
CRON_UTC_HOUR = 6  # render.yaml schedules the daily run at "0 6 * * *" (UTC)


@dataclass(frozen=True)
class Label:
    text: str
    tone: str  # gray | blue | amber | green | red | indigo
    tip: str = ""


GAP_STATUS = {
    "candidate": Label(
        "New idea", "blue", "The scout proposed this; it is not checked against real data yet."
    ),
    "verifying": Label("Being checked", "amber", "The scout is checking this against real data."),
    "verified": Label(
        "Confirmed gap", "green", "Checked: the model works elsewhere and is missing in Kosovo."
    ),
    "parked": Label("On hold", "gray", "Set aside; the scout leaves it alone until reopened."),
    "killed": Label("Rejected", "red", "Ruled out; it stays rejected until you reopen it."),
}
TASK_STATUS = {
    "queued": Label("Waiting", "gray", "Waiting for the next daily run."),
    "running": Label("Running", "blue", "Running now."),
    "done": Label("Done", "green", "Finished successfully."),
    "failed": Label("Failed", "red", "Stopped with an error; you can retry it."),
    "skipped": Label("Skipped", "gray", "Dropped by the scout's daily review."),
}
RUN_STATUS = {
    "running": Label("Running", "blue", "This run is in progress."),
    "done": Label("Finished", "green", "This run finished."),
    "completed": Label("Finished", "green", "This run finished."),
    "failed": Label("Failed", "red", "This run stopped with an error."),
    "stopped": Label("Stopped", "amber", "This run was stopped before it finished."),
    "dry-run": Label("Plan only", "gray", "A dry run: it planned tasks and ran nothing."),
}
PHASES = {
    "foundation": Label("Foundation", "indigo", "building the knowledge base, ~€3/day"),
    "verification": Label("Verification", "indigo", "checking the best gaps against real data"),
    "maintenance": Label("Maintenance", "indigo", "light daily watch"),
}
FLAGS = {
    "critic-says-kill": Label(
        "Critic says reject",
        "red",
        "The critic model wants this rejected; the scout put it on hold for you to decide.",
    ),
    "strategist-says-kill": Label(
        "Strategist says reject",
        "red",
        "The strategist model wants this rejected; the scout put it on hold for you to decide.",
    ),
}
PROFILE_NAMES = {
    "map-sector": "Map a sector",
    "hunt-models": "Find proven models",
    "verify-gap": "Check a gap",
    "culture": "Culture research",
    "news-scan": "News scan",
    "deep-dive": "Deep dive",
    "chart-diff": "App chart comparison",
}
PRESENCE = {
    "absent": "Not in Kosovo",
    "exists-but-poor": "Exists but poor",
    "prishtina-only": "Only in Prishtina",
    "offline-only": "Offline only",
    "decent": "Already done well",
    "unknown": "Not checked yet",
}
OPEN_GAP_STATUSES = ("candidate", "verifying", "verified")
SCORE_PARTS = (
    ("proof", "Proven elsewhere", 25),
    ("absence", "Missing in Kosovo", 25),
    ("demand", "Demand signals", 20),
    ("founder_fit", "Fits you", 15),
    ("risk", "Low risk", 15),
)


def _lookup(table: dict[str, Label], value: object) -> Label:
    if isinstance(value, str) and value in table:
        return table[value]
    return Label("—" if value is None else str(value), "gray")


def status_label(status: object) -> Label:
    return _lookup(GAP_STATUS, status)


def task_label(status: object) -> Label:
    return _lookup(TASK_STATUS, status)


def run_label(status: object) -> Label:
    return _lookup(RUN_STATUS, status)


def flag_label(flag: object) -> Label:
    return _lookup(FLAGS, flag)


def phase_info(phase: object) -> Label:
    return _lookup(PHASES, phase)


def profile_label(profile: str) -> str:
    return PROFILE_NAMES.get(profile, profile)


def presence_label(level: str | None) -> str:
    return PRESENCE.get(level or "unknown", level or "")


def task_target(payload: dict | None) -> str:
    """What a task is about, in words: a gap title, a sector name or a culture theme."""
    p = payload or {}
    if p.get("gap_title"):
        return str(p["gap_title"])
    if p.get("gap_id"):
        return f"gap #{p['gap_id']}"
    for key in ("sector_name", "sector", "theme_name", "theme"):
        if p.get(key):
            return str(p[key])
    return ""


def score_band(score: int | None) -> tuple[str, str]:
    if score is None:
        return "not scored yet", "gray"
    if score >= 75:
        return "strong", "green"
    if score >= 60:
        return "promising", "blue"
    if score >= 40:
        return "weak", "amber"
    return "poor", "red"


def eur(value: object) -> str:
    if value is None:
        return "—"
    amount = Decimal(str(value))
    if 0 < abs(amount) < Decimal("0.01"):
        return "<€0.01"
    return f"€{amount:.2f}"


def pct(value: float | None) -> str:
    return "—" if value is None else f"{round(float(value) * 100)}%"


def iso(value: date | datetime | None) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.isoformat(timespec="minutes")
    return value.isoformat()


def human_date(value: date | datetime | None, today: date, tz: str = DEFAULT_TZ) -> str:
    """"today", "yesterday", "Oct 7" (with the year when it is not this year)."""
    if value is None:
        return "—"
    if isinstance(value, datetime):
        value = (value.astimezone(ZoneInfo(tz)) if value.tzinfo else value).date()
    days = (today - value).days
    if days == 0:
        return "today"
    if days == 1:
        return "yesterday"
    if days == -1:
        return "tomorrow"
    text = f"{value:%b} {value.day}"
    return text if value.year == today.year else f"{text}, {value.year}"


def greeting(now_local: datetime) -> str:
    if 5 <= now_local.hour < 12:
        return "Good morning"
    if 12 <= now_local.hour < 18:
        return "Good afternoon"
    return "Good evening"


def next_run_local(now_utc: datetime, tz: str) -> datetime:
    """The next daily cron start (06:00 UTC), in Kosovo time."""
    run = now_utc.astimezone(UTC).replace(hour=CRON_UTC_HOUR, minute=0, second=0, microsecond=0)
    if run <= now_utc:
        run += timedelta(days=1)
    return run.astimezone(ZoneInfo(tz))


def next_run_text(now_utc: datetime, tz: str) -> str:
    nxt = next_run_local(now_utc, tz)
    word = "Today" if nxt.date() == now_utc.astimezone(ZoneInfo(tz)).date() else "Tomorrow"
    return f"{word} {nxt:%H:%M}"


@dataclass(frozen=True)
class Section:
    key: str
    label: str
    icon: str
    href: str
    prefixes: tuple[str, ...]


SECTIONS = (
    Section("home", "Home", "home", "/", ()),
    Section("gaps", "Gaps", "lightbulb", "/gaps", ("/gaps", "/field-checks")),
    Section("activity", "Activity", "activity", "/pipeline", ("/pipeline", "/journal")),
    Section("knowledge", "Knowledge", "book-open", "/knowledge", ("/knowledge",)),
    Section("settings", "Settings", "settings", "/settings", ("/settings", "/costs")),
)
SECTION_TABS = {
    "gaps": (("/gaps", "Board"), ("/field-checks", "Field checks")),
    "activity": (("/pipeline", "Pipeline"), ("/journal", "Journal")),
    "settings": (("/settings", "General"), ("/costs", "Budget & costs")),
}


def active_section(path: str) -> str:
    for section in SECTIONS:
        if any(path == p or path.startswith(p + "/") for p in section.prefixes):
            return section.key
    return "home"
```

- [ ] **Step 4: Run the tests and confirm they pass**

Run: `uv run pytest tests/test_web_ui.py -q && uv run ruff check scout tests && uv run ruff format --check scout tests`
Expected: all pass; ruff reports no issues.

- [ ] **Step 5: Commit**

```bash
git add scout/web/ui.py tests/test_web_ui.py
git commit -m "feat(web): plain-language labels, human dates and nav sections (ui.py)" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01363MMeXh1CX8iLQ1mddmG7" | cat
```

---

### Task 2: Design system and app shell

**Files:**
- Create:
  - `scout/web/static/app.css`
  - `scout/web/static/app.js`
  - `scout/web/templates/_ui.html`
  - `tests/test_web_shell.py`
- Modify:
  - `scout/web/auth.py` (add `STATIC_PREFIX`)
  - `scout/web/app.py` (static mount, open static prefix, cache header)
  - `scout/web/deps.py` (full replacement: helpers registered, `ASSET_VERSION`, badges)
- Replace:
  - `scout/web/templates/base.html`
  - `scout/web/templates/login.html`
  - `scout/web/templates/error.html`

**Interfaces:**
- Consumes: everything Task 1 produces.
- Produces (wave-2 pages rely on these exact names):
  - **Jinja filters:**
    - `md`;
    - `eur`;
    - `pct`;
    - `iso`;
    - `when` (a datetime or date becomes human text in Kosovo time).
  - **Jinja globals:**
    - `ASSET_VERSION`, `SECTIONS`, `SECTION_TABS`, `SCORE_PARTS`;
    - `active_section`, `status_label`, `task_label`, `run_label`, `flag_label`;
    - `phase_info`, `profile_label`, `presence_label`, `task_target`, `score_band`.
  - **`_ui.html` macros** (import with `{% import "_ui.html" as ui with context %}`):
    - `icon(name, cls="")`;
    - `chip(text, tone="gray", title="", cls="")`;
    - `status_chip(kind, value)`, where kind is `"gap"|"task"|"run"`;
    - `date(d)`;
    - `page_header(title, subtitle="")`, which accepts an optional `{% call %}` body for the
      actions and also renders the section tabs;
    - `score_bar(score)`, where score is an int or `none`;
    - `part_bar(label, value, top)`;
    - `stat_tile(label, value, sub="", href="", progress=none, icon_name="")`;
    - `empty_state(icon_name, text, href="", link_text="")`;
    - `post_button(action, label, fields={}, cls="", icon_name="", confirm="")`;
    - `confirm_button(action, label, message, fields={}, cls="danger", icon_name="x")`;
    - `gap_actions(g, finalists, flagged, next)`.
  - **`deps.page(request, name, *, status_code=200, session=None, **ctx)`**:
    - It adds `msg`, `err`, `nav_badges` (a dict from section key to int) and `nav_phase`.
    - A route may pass `session=` to reuse its DB session for the badge queries.
  - **`deps.nav_badges(session) -> dict[str, int]`**, which returns the keys `home`, `gaps` and
    `activity`.
  - **CSS classes:** used by wave-2 markup and all defined in `app.css` below.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_web_shell.py
import re
from datetime import date

import pytest
from fastapi.testclient import TestClient

from scout.db import repo
from scout.db.base import make_session_factory
from scout.web import deps, ui
from scout.web.app import create_app

pytestmark = pytest.mark.db


def _anon(settings, db_engine):
    app = create_app(settings, make_session_factory(db_engine))
    return TestClient(app, base_url="https://testserver")


def test_static_files_are_public_and_cached(db_session, db_engine, settings):
    c = _anon(settings, db_engine)
    for path in (
        "/static/app.css",
        "/static/app.js",
        "/static/icons.svg",
        "/static/fonts/inter-latin-wght-normal.woff2",
    ):
        r = c.get(path, follow_redirects=False)
        assert r.status_code == 200, path
        assert r.headers["cache-control"] == "public, max-age=86400", path
    assert "text/css" in c.get("/static/app.css").headers["content-type"]
    assert c.get("/static/nope.css").status_code == 404


def test_only_the_static_prefix_is_open(db_session, db_engine, settings):
    c = _anon(settings, db_engine)
    for path in ("/staticx", "/static", "/staticapp.css"):
        r = c.get(path, follow_redirects=False)
        assert r.status_code == 303 and r.headers["location"] == "/login", path


def test_login_page_is_styled_and_has_no_navigation(db_session, db_engine, settings):
    html = _anon(settings, db_engine).get("/login").text
    assert re.fullmatch(r"[0-9a-f]{10}", deps.ASSET_VERSION)
    assert f"/static/app.css?v={deps.ASSET_VERSION}" in html
    assert f"/static/app.js?v={deps.ASSET_VERSION}" in html
    assert 'aria-label="Main"' not in html and "Dashboard token" in html


def test_shell_has_five_sections_and_marks_the_current_one(web):
    html = web.get("/journal").text
    assert '<nav class="side-nav" aria-label="Main">' in html
    for label in ("Home", "Gaps", "Activity", "Knowledge", "Settings"):
        assert f"<span>{label}</span>" in html
    assert '<a href="/pipeline" aria-current="page">' in html
    assert '<a href="/" aria-current="page">' not in html
    assert "Foundation" in html  # phase pill


def test_every_section_icon_exists_in_the_sprite():
    sprite = (deps.STATIC_DIR / "icons.svg").read_text()
    for s in ui.SECTIONS:
        assert f'id="i-{s.icon}"' in sprite, s.icon


def test_nav_badges_count_what_needs_attention(web, db_session):
    assert "data-badge=" not in web.get("/journal").text
    repo.save_brief(db_session, run_id=None, day=date(2026, 10, 9), markdown="b")
    repo.add_field_check(db_session, gap_id=None, question="q?", why="w", due=date(2026, 10, 11))
    t = repo.enqueue_task(db_session, profile="news-scan", payload={}, priority=40)
    t.status = "failed"
    db_session.commit()
    html = web.get("/journal").text
    for key in ("home", "gaps", "activity"):
        assert re.search(rf'data-badge="{key}"[^>]*>1<', html), key


def test_badges_never_break_a_page(web, monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("db hiccup")

    monkeypatch.setattr(repo, "open_field_checks", boom)
    r = web.get("/journal")
    assert r.status_code == 200 and "data-badge=" not in r.text


def test_flash_messages_render_as_escaped_toasts(web):
    ok = web.get("/journal", params={"msg": "<b>Saved</b>"}).text
    assert "data-toast" in ok and "&lt;b&gt;Saved&lt;/b&gt;" in ok and "data-sticky" not in ok
    err = web.get("/journal", params={"err": "Nope"}).text
    assert 'role="alert" data-toast data-sticky' in err and "Nope" in err


def test_error_page_uses_the_bare_layout(web):
    r = web.get("/gaps/99999999999")
    assert r.status_code == 400 and "out of range or not allowed" in r.text
    assert 'aria-label="Main"' not in r.text
```

- [ ] **Step 2: Run the tests and confirm they fail**

Run: `TEST_DATABASE_URL=postgresql://scout:scout@localhost:55432/scout_test_t1 uv run pytest tests/test_web_shell.py -q`
Expected: FAIL. Static paths redirect to /login, and `deps.ASSET_VERSION` does not exist.

- [ ] **Step 3: Open the static prefix and mount the files**

In `scout/web/auth.py`, add `STATIC_PREFIX` below `OPEN_PATHS`:

```python
OPEN_PATHS = frozenset({"/login", "/logout", "/healthz"})
STATIC_PREFIX = "/static/"  # CSS, JS, fonts and icons: the login page needs them before login
```

In `scout/web/app.py`:
- add `from fastapi.staticfiles import StaticFiles`;
- change `from scout.web.deps import page` to `from scout.web.deps import STATIC_DIR, page`;
- replace the start of `require_login`;
- mount the files just before the router loop.

```python
    @app.middleware("http")
    async def require_login(request: Request, call_next):
        path = request.url.path
        if path.startswith(auth.STATIC_PREFIX):
            response = await call_next(request)
            if response.status_code == 200:  # asset URLs carry ?v=<hash>, so a day is safe
                response.headers["Cache-Control"] = "public, max-age=86400"
            return response
        if path in auth.OPEN_PATHS:
            return await call_next(request)
        token = auth.usable_token(settings)
        if token is None:
            return PlainTextResponse(LOCKED, status_code=503)
        if not auth.is_logged_in(request, token):
            return RedirectResponse("/login", status_code=303)
        return await call_next(request)
```

```python
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    for module in (today, gaps, field_checks, pipeline, knowledge, journal, costs, settings_page):
        app.include_router(module.router)
    return app
```

- [ ] **Step 4: Replace `scout/web/deps.py`**

```python
"""Shared request helpers: DB session, templates, Kosovo's date, flash-message redirects, and the
sidebar's badges."""

from __future__ import annotations

import hashlib
import logging
from collections.abc import Iterator
from datetime import date
from pathlib import Path
from urllib.parse import urlencode

from fastapi import Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from jinja2 import pass_context
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from scout.clock import local_today
from scout.db import repo
from scout.db.models import Task
from scout.web import ui
from scout.web.render import md

log = logging.getLogger(__name__)
STATIC_DIR = Path(__file__).parent / "static"
BARE_PAGES = frozenset({"login.html", "error.html"})  # no sidebar, so no badges to compute


def _asset_version() -> str:
    """Changes whenever a served asset changes, so browsers drop their day-long cached copy."""
    digest = hashlib.sha256()
    for name in ("app.css", "app.js", "icons.svg"):
        digest.update((STATIC_DIR / name).read_bytes())
    return digest.hexdigest()[:10]


ASSET_VERSION = _asset_version()


@pass_context
def _when(ctx, value) -> str:
    request = ctx.get("request")
    tz = request.app.state.settings.timezone if request is not None else ui.DEFAULT_TZ
    return ui.human_date(value, local_today(tz), tz)


templates = Jinja2Templates(directory=Path(__file__).parent / "templates")
templates.env.filters.update(md=md, eur=ui.eur, pct=ui.pct, iso=ui.iso, when=_when)
templates.env.globals.update(
    ASSET_VERSION=ASSET_VERSION,
    SECTIONS=ui.SECTIONS,
    SECTION_TABS=ui.SECTION_TABS,
    SCORE_PARTS=ui.SCORE_PARTS,
    active_section=ui.active_section,
    status_label=ui.status_label,
    task_label=ui.task_label,
    run_label=ui.run_label,
    flag_label=ui.flag_label,
    phase_info=ui.phase_info,
    profile_label=ui.profile_label,
    presence_label=ui.presence_label,
    task_target=ui.task_target,
    score_band=ui.score_band,
)


def get_session(request: Request) -> Iterator[Session]:
    session = request.app.state.session_factory()
    try:
        yield session
    finally:
        session.close()


def local_day(request: Request) -> date:
    return local_today(request.app.state.settings.timezone)


def nav_badges(session: Session) -> dict[str, int]:
    """Counts shown next to the sidebar sections; 0 hides the badge."""
    brief = repo.latest_brief(session)
    read_id = (repo.get_setting(session, "brief_read") or {}).get("id")
    failed = session.scalar(select(func.count()).select_from(Task).where(Task.status == "failed"))
    return {
        "home": int(brief is not None and brief.id != read_id),
        "gaps": len(repo.open_field_checks(session)),
        "activity": failed or 0,
    }


def _shell(request: Request, session: Session | None) -> dict:
    """Badges and the phase pill for the sidebar. A failure here never fails the page."""
    own = session is None
    s = request.app.state.session_factory() if own else session
    try:
        phase = (repo.get_setting(s, "phase") or {}).get("value") or request.app.state.settings.phase
        return {"nav_badges": nav_badges(s), "nav_phase": phase}
    except Exception:
        log.warning("sidebar badges unavailable", exc_info=True)
        if not own:
            s.rollback()
        return {"nav_badges": {}, "nav_phase": None}
    finally:
        if own:
            s.close()


def page(
    request: Request,
    name: str,
    *,
    status_code: int = 200,
    session: Session | None = None,
    **ctx,
):
    base = {"msg": request.query_params.get("msg"), "err": request.query_params.get("err")}
    if name in BARE_PAGES:
        base |= {"nav_badges": {}, "nav_phase": None}
    else:
        base |= _shell(request, session)
    return templates.TemplateResponse(request, name, {**base, **ctx}, status_code=status_code)


def local_path(url: str) -> str:
    """Only same-site paths may be redirect targets (`next=` fields come from the browser)."""
    if (
        url.startswith("/")
        and not url.startswith("//")
        and not any(c in url for c in "\\\t\r\n")  # browsers drop tab/CR/LF: "/\t/x" is "//x"
    ):
        return url
    return "/"


def back(url: str, *, msg: str | None = None, err: str | None = None) -> RedirectResponse:
    params = {k: v for k, v in (("msg", msg), ("err", err)) if v}
    if params:
        url += ("&" if "?" in url else "?") + urlencode(params)
    return RedirectResponse(url, status_code=303)
```

- [ ] **Step 5: Create `scout/web/static/app.css`**

```css
/* Gap Scout dashboard. One hand-written stylesheet, no build step. Light and dark follow the OS. */

@font-face {
  font-family: "Inter";
  font-style: normal;
  font-weight: 100 900;
  font-display: swap;
  src: url("fonts/inter-latin-wght-normal.woff2") format("woff2");
  unicode-range: U+0000-00FF, U+0131, U+0152-0153, U+02BB-02BC, U+02C6, U+02DA, U+02DC, U+0304,
    U+0308, U+0329, U+2000-206F, U+20AC, U+2122, U+2191, U+2193, U+2212, U+2215, U+FEFF, U+FFFD;
}
@font-face {
  font-family: "Inter";
  font-style: normal;
  font-weight: 100 900;
  font-display: swap;
  src: url("fonts/inter-latin-ext-wght-normal.woff2") format("woff2");
  unicode-range: U+0100-02BA, U+02BD-02C5, U+02C7-02CC, U+02CE-02D7, U+02DD-02FF, U+0304, U+0308,
    U+0329, U+1D00-1DBF, U+1E00-1E9F, U+1EF2-1EFF, U+2020, U+20A0-20AB, U+20AD-20C0, U+2113,
    U+2C60-2C7F, U+A720-A7FF;
}

:root {
  --font: "Inter", ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
  --mono: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  --radius: 12px;
  --radius-sm: 8px;
  --bg: #f8fafc;
  --surface: #ffffff;
  --surface-2: #f1f5f9;
  --border: #e2e8f0;
  --border-strong: #cbd5e1;
  --text: #0f172a;
  --text-2: #334155;
  --muted: #64748b;
  --accent: #4f46e5;
  --accent-hover: #4338ca;
  --accent-fg: #ffffff;
  --accent-soft: #eef2ff;
  --shadow: 0 1px 2px rgb(15 23 42 / 0.05), 0 1px 3px rgb(15 23 42 / 0.07);
  --shadow-lg: 0 12px 32px rgb(15 23 42 / 0.14);
  --gray-bg: #f1f5f9;   --gray-fg: #334155;
  --blue-bg: #dbeafe;   --blue-fg: #1e40af;
  --amber-bg: #fef3c7;  --amber-fg: #92400e;
  --green-bg: #dcfce7;  --green-fg: #166534;
  --red-bg: #fee2e2;    --red-fg: #991b1b;
  --indigo-bg: #e0e7ff; --indigo-fg: #3730a3;
  --fill-gray: #94a3b8;
  --fill-blue: #3b82f6;
  --fill-amber: #f59e0b;
  --fill-green: #16a34a;
  --fill-red: #dc2626;
  --fill-indigo: #4f46e5;
  color-scheme: light;
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #0b1020;
    --surface: #121a2b;
    --surface-2: #1a2336;
    --border: #24304a;
    --border-strong: #334155;
    --text: #e2e8f0;
    --text-2: #cbd5e1;
    --muted: #94a3b8;
    --accent: #818cf8;
    --accent-hover: #a5b4fc;
    --accent-fg: #0b1020;
    --accent-soft: rgb(129 140 248 / 0.14);
    --shadow: 0 1px 2px rgb(0 0 0 / 0.4);
    --shadow-lg: 0 12px 32px rgb(0 0 0 / 0.55);
    --gray-bg: #1e293b;               --gray-fg: #cbd5e1;
    --blue-bg: rgb(59 130 246 / 0.18); --blue-fg: #93c5fd;
    --amber-bg: rgb(245 158 11 / 0.18); --amber-fg: #fcd34d;
    --green-bg: rgb(34 197 94 / 0.16); --green-fg: #86efac;
    --red-bg: rgb(239 68 68 / 0.18);   --red-fg: #fca5a5;
    --indigo-bg: rgb(129 140 248 / 0.18); --indigo-fg: #c7d2fe;
    --fill-gray: #64748b;
    --fill-blue: #60a5fa;
    --fill-amber: #fbbf24;
    --fill-green: #4ade80;
    --fill-red: #f87171;
    --fill-indigo: #818cf8;
    color-scheme: dark;
  }
}

/* Base */
*, *::before, *::after { box-sizing: border-box; }
html { -webkit-text-size-adjust: 100%; }
body {
  margin: 0;
  background: var(--bg);
  color: var(--text);
  font: 15px/1.55 var(--font);
  -webkit-font-smoothing: antialiased;
}
a { color: var(--accent); text-decoration: none; }
a:hover { text-decoration: underline; }
:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; border-radius: 4px; }
h1, h2, h3 { margin: 0; line-height: 1.25; letter-spacing: -0.01em; }
h1 { font-size: 1.6rem; font-weight: 700; }
h2 { font-size: 1.05rem; font-weight: 600; }
h3 { font-size: 0.95rem; font-weight: 600; margin: 1rem 0 0.4rem; }
p { margin: 0 0 0.75rem; }
pre, code { font-family: var(--mono); font-size: 0.85em; }
pre {
  margin: 8px 0;
  padding: 10px 12px;
  border-radius: var(--radius-sm);
  background: var(--surface-2);
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}
details > summary { cursor: pointer; }
.icon {
  width: 18px;
  height: 18px;
  flex: none;
  fill: none;
  stroke: currentColor;
  stroke-width: 2;
  stroke-linecap: round;
  stroke-linejoin: round;
  vertical-align: -3px;
}
.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  margin: -1px;
  padding: 0;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  border: 0;
}
.js-only { display: none !important; }
.js .js-only { display: inline-flex !important; }

/* Shell: sidebar on wide screens, top bar + bottom tab bar on phones */
body.shell { display: grid; grid-template-columns: 240px minmax(0, 1fr); min-height: 100vh; }
.sidebar {
  position: sticky;
  top: 0;
  height: 100vh;
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 20px 12px;
  background: var(--surface);
  border-right: 1px solid var(--border);
}
.brand {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 4px 10px 18px;
  color: var(--text);
  font-weight: 700;
  font-size: 1.05rem;
}
.brand:hover { text-decoration: none; }
.brand .icon {
  width: 30px;
  height: 30px;
  padding: 6px;
  border-radius: 8px;
  background: var(--accent);
  color: var(--accent-fg);
}
.side-nav { display: flex; flex-direction: column; gap: 2px; }
.side-nav a {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 9px 12px;
  border-radius: var(--radius-sm);
  color: var(--text-2);
  font-weight: 500;
}
.side-nav a:hover { background: var(--surface-2); text-decoration: none; }
.side-nav a[aria-current="page"] { background: var(--accent-soft); color: var(--accent); }
.count {
  margin-left: auto;
  min-width: 20px;
  padding: 0 6px;
  border-radius: 99px;
  background: var(--accent);
  color: var(--accent-fg);
  font-size: 0.72rem;
  font-weight: 700;
  line-height: 20px;
  text-align: center;
}
.side-foot {
  margin-top: auto;
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 12px 4px 0;
  border-top: 1px solid var(--border);
}
.phase-pill {
  display: flex;
  flex-direction: column;
  padding: 10px 12px;
  border-radius: var(--radius-sm);
  background: var(--surface-2);
  color: var(--muted);
  font-size: 0.78rem;
}
.phase-pill strong { color: var(--text); font-size: 0.85rem; }
.content { width: 100%; max-width: 1100px; padding: 32px 40px 64px; }
.topbar, .tabbar { display: none; }

/* Bare layout: login and error pages */
body.bare { min-height: 100vh; display: grid; place-items: center; padding: 16px; }
body.bare .content { max-width: 420px; padding: 0; }
.auth-card { padding: 28px; }
.auth-card .brand { padding: 0 0 6px; }

/* Page header and section tabs */
.page-head {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-end;
  justify-content: space-between;
  gap: 12px 24px;
  margin-bottom: 20px;
}
.page-head .chips { margin-top: 10px; }
.subtitle { margin: 6px 0 0; max-width: 70ch; color: var(--muted); }
.page-actions { display: flex; flex-wrap: wrap; gap: 8px; }
.back { display: inline-block; margin-bottom: 12px; color: var(--muted); font-size: 0.9rem; }
.section-title { margin: 28px 0 12px; }
.tabs {
  display: inline-flex;
  max-width: 100%;
  gap: 2px;
  margin: -4px 0 20px;
  padding: 3px;
  overflow-x: auto;
  border: 1px solid var(--border);
  border-radius: 10px;
  background: var(--surface-2);
}
.tabs a {
  padding: 6px 14px;
  border-radius: 7px;
  color: var(--text-2);
  font-size: 0.9rem;
  font-weight: 500;
  white-space: nowrap;
}
.tabs a:hover { color: var(--text); text-decoration: none; }
.tabs a[aria-current="page"] { background: var(--surface); color: var(--text); box-shadow: var(--shadow); }

/* Cards and layout helpers */
.card {
  margin: 0 0 16px;
  padding: 18px 20px;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  box-shadow: var(--shadow);
  overflow-wrap: anywhere;
}
.card > h2 { display: flex; align-items: center; gap: 8px; margin-bottom: 12px; }
.card > summary { font-weight: 600; }
.card[open] > summary { margin-bottom: 12px; }
a.card { display: block; color: var(--text); }
a.card:hover { border-color: var(--accent); text-decoration: none; }
.card-head { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-bottom: 12px; }
.card-head h2 { margin: 0; }
.stack { display: flex; flex-direction: column; gap: 16px; }
.stack > .card { margin: 0; }
.grid-2 { display: grid; grid-template-columns: minmax(0, 3fr) minmax(0, 2fr); gap: 16px; align-items: start; }
.cards { display: grid; grid-template-columns: repeat(auto-fill, minmax(240px, 1fr)); gap: 16px; }
.cards > .card { margin: 0; }
.muted { color: var(--muted); font-size: 0.9rem; }
.hint { color: var(--muted); font-size: 0.82rem; margin: 8px 0 0; }
.row { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; }
.big-num { font-size: 1.6rem; font-weight: 700; letter-spacing: -0.02em; }
.links { margin: 0; padding-left: 1.1em; }

/* Chips */
.chips { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; }
.chip, .badge {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 2px 9px;
  border: 0;
  border-radius: 99px;
  background: var(--gray-bg);
  color: var(--gray-fg);
  font-size: 0.75rem;
  font-weight: 600;
  line-height: 1.5;
  white-space: nowrap;
}
.chip-blue { background: var(--blue-bg); color: var(--blue-fg); }
.chip-amber { background: var(--amber-bg); color: var(--amber-fg); }
.chip-green { background: var(--green-bg); color: var(--green-fg); }
.chip-red { background: var(--red-bg); color: var(--red-fg); }
.chip-indigo, .badge.new-brief { background: var(--indigo-bg); color: var(--indigo-fg); }
.dot { display: inline-block; width: 8px; height: 8px; flex: none; border-radius: 50%; background: var(--fill-gray); }
.dot-blue { background: var(--fill-blue); }
.dot-amber { background: var(--fill-amber); }
.dot-green { background: var(--fill-green); }
.dot-red { background: var(--fill-red); }
.dot-indigo { background: var(--fill-indigo); }

/* Buttons */
button, .btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  min-height: 36px;
  padding: 0 14px;
  border: 1px solid var(--border-strong);
  border-radius: var(--radius-sm);
  background: var(--surface);
  color: var(--text);
  font: inherit;
  font-size: 0.9rem;
  font-weight: 500;
  white-space: nowrap;
  cursor: pointer;
  transition: background 0.15s, border-color 0.15s;
}
button:hover, .btn:hover { background: var(--surface-2); text-decoration: none; }
button.primary, .btn.primary { background: var(--accent); border-color: var(--accent); color: var(--accent-fg); }
button.primary:hover, .btn.primary:hover { background: var(--accent-hover); }
button.danger, .btn.danger { color: var(--red-fg); }
button.danger:hover, .btn.danger:hover { background: var(--red-bg); border-color: transparent; }
.btn.ghost { border-color: transparent; background: transparent; color: var(--text-2); }
.btn.ghost:hover { background: var(--surface-2); }
.btn.sm { min-height: 30px; padding: 0 10px; font-size: 0.82rem; }
.btn.block { width: 100%; }
.btn .icon { width: 16px; height: 16px; }
form.inline { display: inline-flex; margin: 0; }
.actions { display: flex; flex-wrap: wrap; gap: 6px; }

/* Forms */
input, select, textarea {
  max-width: 100%;
  min-height: 38px;
  padding: 8px 10px;
  border: 1px solid var(--border-strong);
  border-radius: var(--radius-sm);
  background: var(--surface);
  color: var(--text);
  font: inherit;
  font-size: 0.92rem;
}
input:focus, select:focus, textarea:focus { outline: 2px solid var(--accent); outline-offset: 0; border-color: var(--accent); }
textarea { width: 100%; min-height: 6em; line-height: 1.5; resize: vertical; }
label { color: var(--text-2); font-size: 0.85rem; font-weight: 500; }
.fields { display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); gap: 12px; }
.field { display: flex; flex-direction: column; gap: 6px; }
.field small { color: var(--muted); font-size: 0.78rem; font-weight: 400; }
.form-foot { display: flex; flex-wrap: wrap; align-items: center; gap: 10px 12px; margin-top: 12px; }
.form-stack { display: flex; flex-direction: column; gap: 10px; }
.search { display: flex; gap: 8px; margin-bottom: 20px; }
.search input { flex: 1; min-width: 0; }

/* Tables */
.table-wrap { overflow-x: auto; }
table { width: 100%; border-collapse: collapse; font-size: 0.9rem; }
th, td { padding: 10px 12px; border-bottom: 1px solid var(--border); text-align: left; vertical-align: middle; }
th { color: var(--muted); font-size: 0.75rem; font-weight: 600; letter-spacing: 0.04em; text-transform: uppercase; }
tr:last-child td { border-bottom: 0; }
.num { text-align: right; font-variant-numeric: tabular-nums; }

/* Toasts (inline without JS; floating with JS) */
.toasts { display: flex; flex-direction: column; gap: 8px; margin-bottom: 16px; }
.js .toasts { position: fixed; z-index: 50; top: 16px; right: 16px; width: min(380px, calc(100vw - 32px)); margin: 0; }
.toast {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 12px 14px;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: var(--surface);
  box-shadow: var(--shadow-lg);
  overflow-wrap: anywhere;
  transition: opacity 0.3s, transform 0.3s;
}
.toast > span { flex: 1; }
.toast.ok > .icon { color: var(--fill-green); }
.toast.err { border-color: var(--fill-red); }
.toast.err > .icon { color: var(--fill-red); }
.toast.hide { opacity: 0; transform: translateY(-6px); }
.toast-x { min-height: 0; padding: 2px; border: 0; background: transparent; color: var(--muted); }
.flash { padding: 10px 12px; border-radius: var(--radius-sm); margin: 10px 0; }
.flash.ok { background: var(--green-bg); color: var(--green-fg); }
.flash.err { background: var(--red-bg); color: var(--red-fg); }

/* Meters, scores */
.meter { position: relative; display: block; flex: 1; min-width: 60px; height: 6px; overflow: hidden; border-radius: 99px; background: var(--surface-2); }
.meter-fill { display: block; height: 100%; border-radius: inherit; background: var(--fill-indigo); }
.fill-gray { background: var(--fill-gray); }
.fill-blue { background: var(--fill-blue); }
.fill-amber { background: var(--fill-amber); }
.fill-green { background: var(--fill-green); }
.fill-red { background: var(--fill-red); }
.fill-indigo { background: var(--fill-indigo); }
.score { display: flex; align-items: center; gap: 8px; font-size: 0.85rem; }
.score-num { font-weight: 700; font-variant-numeric: tabular-nums; }
.score-word { color: var(--muted); }
.part { display: grid; grid-template-columns: 9.5rem 1fr 3rem; align-items: center; gap: 10px; margin: 8px 0; font-size: 0.85rem; }
.part-num { color: var(--muted); text-align: right; font-variant-numeric: tabular-nums; }

/* Home */
.tiles { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 16px; margin-bottom: 16px; }
.tile {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 16px 18px;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: var(--surface);
  box-shadow: var(--shadow);
  color: var(--text);
}
a.tile:hover { border-color: var(--accent); text-decoration: none; }
.tile-label { display: flex; align-items: center; gap: 6px; color: var(--muted); font-size: 0.8rem; font-weight: 500; }
.tile-value { font-size: 1.5rem; font-weight: 700; letter-spacing: -0.02em; font-variant-numeric: tabular-nums; }
.tile-sub { color: var(--muted); font-size: 0.8rem; }
.tile .meter { flex: none; margin-top: 6px; }
.todo { margin: 0; padding: 0; list-style: none; }
.todo li { display: flex; flex-wrap: wrap; align-items: center; gap: 8px 12px; padding: 12px 0; border-top: 1px solid var(--border); }
.todo li:first-child { border-top: 0; padding-top: 4px; }
.todo .what { flex: 1; min-width: 12rem; display: flex; flex-wrap: wrap; align-items: center; gap: 8px; font-weight: 500; }
.all-clear { display: flex; align-items: center; gap: 8px; margin: 0; color: var(--green-fg); font-weight: 500; }
.last-run { display: flex; flex-wrap: wrap; align-items: center; gap: 6px 10px; margin: 0 0 16px; color: var(--text-2); font-size: 0.9rem; }
.article-head { display: flex; flex-wrap: wrap; align-items: center; gap: 10px; margin-bottom: 12px; }

/* Markdown */
.prose { max-width: 70ch; line-height: 1.7; }
.md > :first-child { margin-top: 0; }
.md > :last-child { margin-bottom: 0; }
.md h1 { margin: 1.2em 0 0.5em; font-size: 1.35rem; }
.md h2 { margin: 1.2em 0 0.4em; font-size: 1.15rem; }
.md h3 { margin: 1em 0 0.3em; }
.md ul, .md ol { padding-left: 1.3em; }
.md li + li { margin-top: 0.25em; }
.md img { max-width: 100%; }
.md table { display: block; overflow-x: auto; }
.md blockquote { margin: 1em 0; padding: 2px 14px; border-left: 3px solid var(--border-strong); color: var(--text-2); }

/* Gaps board */
.filter { display: none; }
.board { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 16px; align-items: start; margin-bottom: 16px; }
.column { min-height: 120px; padding: 12px; border: 1px solid var(--border); border-radius: var(--radius); background: var(--surface-2); }
.column-head { display: flex; align-items: center; gap: 8px; margin: 2px 4px 12px; font-size: 0.85rem; }
.n { margin-left: auto; color: var(--muted); font-weight: 500; font-variant-numeric: tabular-nums; }
.column-empty { margin: 0; padding: 16px 0; color: var(--muted); font-size: 0.85rem; text-align: center; }
.gap-card {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-bottom: 10px;
  padding: 12px 14px;
  border: 1px solid var(--border);
  border-radius: 10px;
  background: var(--surface);
  box-shadow: var(--shadow);
  overflow-wrap: anywhere;
}
.gap-title { color: var(--text); font-weight: 600; }
.gap-meta { color: var(--muted); font-size: 0.8rem; }
.gap-foot { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 8px; color: var(--muted); font-size: 0.8rem; }
details.more > summary { list-style: none; }
details.more > summary::-webkit-details-marker { display: none; }
details.more[open] { flex-basis: 100%; }
details.more[open] > .actions { margin-top: 8px; }
.rejected > summary { display: flex; align-items: center; gap: 8px; }
.check .q { margin-bottom: 6px; font-size: 1.02rem; font-weight: 600; }
.check .why, .check .meta { color: var(--text-2); font-size: 0.9rem; }
dl.kv { display: grid; grid-template-columns: minmax(8rem, max-content) 1fr; gap: 6px 16px; margin: 0 0 8px; }
dl.kv dt { color: var(--muted); font-size: 0.85rem; }
dl.kv dd { margin: 0; }
dl.kv dd ul { margin: 0; padding-left: 1.1em; }

/* Lists, timeline, summary strip */
.list { margin: 0; padding: 0; list-style: none; }
.list > li { display: flex; flex-wrap: wrap; align-items: center; gap: 6px 12px; padding: 12px 0; border-top: 1px solid var(--border); }
.list > li:first-child { border-top: 0; padding-top: 0; }
.list .grow { flex: 1; min-width: 12rem; }
.list details { flex-basis: 100%; }
.id { color: var(--muted); font-size: 0.85rem; font-variant-numeric: tabular-nums; }
.timeline { position: relative; margin: 0; padding: 0; list-style: none; }
.timeline > li { position: relative; padding: 0 0 18px 30px; }
.timeline > li::before { content: ""; position: absolute; left: 7px; top: 22px; bottom: 0; width: 2px; background: var(--border); }
.timeline > li:last-child::before { display: none; }
.tl-dot { position: absolute; left: 0; top: 4px; width: 16px; height: 16px; border: 3px solid var(--accent); border-radius: 50%; background: var(--surface); }
.tl-head { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; margin-bottom: 6px; font-size: 0.9rem; }
.timeline .card { margin: 0; }
.strip { display: flex; flex-wrap: wrap; gap: 12px; margin-bottom: 16px; }
.stat {
  flex: 1;
  min-width: 130px;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 16px;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: var(--surface);
  color: var(--text-2);
}
.stat strong { color: var(--text); font-size: 1.3rem; }

/* Knowledge */
.sector-card { display: flex; flex-direction: column; gap: 8px; }
.sector-card h3 { margin: 0; font-size: 1rem; }
.sector-card .stats { color: var(--muted); font-size: 0.85rem; }

/* Costs: 14-day bar chart */
.bars { display: flex; align-items: stretch; gap: 6px; height: 150px; padding-top: 8px; }
.bar-col { flex: 1; min-width: 0; display: flex; flex-direction: column; align-items: center; gap: 6px; }
.bar-track { flex: 1; width: 100%; display: flex; align-items: flex-end; justify-content: center; }
.bar { width: 100%; max-width: 28px; min-height: 2px; border-radius: 4px 4px 0 0; background: var(--fill-indigo); }
.bar-col.today .bar { background: var(--fill-amber); }
.bar-label { color: var(--muted); font-size: 0.68rem; }

/* Empty states */
.empty { display: flex; flex-direction: column; align-items: center; gap: 10px; padding: 24px 16px; color: var(--muted); text-align: center; }
.empty p { margin: 0; max-width: 46ch; }
.empty-icon { width: 38px; height: 38px; padding: 9px; border-radius: 50%; background: var(--surface-2); color: var(--accent); }

/* Responsive */
@media (max-width: 1023.98px) {
  .tiles { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .grid-2 { grid-template-columns: minmax(0, 1fr); }
  .board { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
@media (max-width: 767.98px) {
  body.shell { display: block; padding-bottom: calc(68px + env(safe-area-inset-bottom)); }
  .sidebar { display: none; }
  .topbar {
    position: sticky;
    top: 0;
    z-index: 30;
    display: flex;
    align-items: center;
    gap: 10px;
    height: 56px;
    padding: 0 8px 0 16px;
    border-bottom: 1px solid var(--border);
    background: var(--surface);
  }
  .topbar .brand { padding: 0; }
  .topbar-title { flex: 1; overflow: hidden; font-weight: 600; text-overflow: ellipsis; white-space: nowrap; }
  .topbar button { min-width: 44px; min-height: 44px; padding: 0; border: 0; background: transparent; color: var(--muted); }
  .tabbar {
    position: fixed;
    z-index: 30;
    left: 0;
    right: 0;
    bottom: 0;
    display: flex;
    padding: 4px 4px env(safe-area-inset-bottom);
    border-top: 1px solid var(--border);
    background: var(--surface);
  }
  .tabbar a {
    position: relative;
    flex: 1;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 2px;
    min-height: 56px;
    color: var(--muted);
    font-size: 0.68rem;
    font-weight: 500;
  }
  .tabbar a:hover { text-decoration: none; }
  .tabbar a[aria-current="page"] { color: var(--accent); }
  .tabbar .icon { width: 22px; height: 22px; }
  .tabbar .count { position: absolute; top: 4px; left: calc(50% + 6px); min-width: 18px; margin: 0; font-size: 0.65rem; line-height: 18px; }
  .content { padding: 20px 16px 32px; }
  h1 { font-size: 1.35rem; }
  .card { padding: 16px; }
  .js .toasts { top: auto; bottom: calc(76px + env(safe-area-inset-bottom)); left: 16px; right: 16px; width: auto; }
  button, .btn, .btn.sm, input, select { min-height: 44px; }
  .filter { display: flex; gap: 6px; margin-bottom: 12px; padding-bottom: 2px; overflow-x: auto; }
  .filter a {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    min-height: 44px;
    padding: 0 14px;
    border: 1px solid var(--border);
    border-radius: 99px;
    background: var(--surface);
    color: var(--text-2);
    font-size: 0.85rem;
    white-space: nowrap;
  }
  .filter a:hover { text-decoration: none; }
  .filter a[aria-current="true"] { background: var(--accent); border-color: var(--accent); color: var(--accent-fg); }
  .filter .n { margin-left: 0; color: inherit; opacity: 0.85; }
  .board { display: block; }
  .column { display: none; min-height: 0; padding: 0; border: 0; background: transparent; }
  .column.is-selected { display: block; }
  .column-head { display: none; }
  .part { grid-template-columns: 7.5rem 1fr 2.6rem; }
  dl.kv { grid-template-columns: 1fr; }
  dl.kv dd { margin-bottom: 8px; }
}
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after { transition: none !important; scroll-behavior: auto !important; }
}
```

- [ ] **Step 6: Create `scout/web/static/app.js`**

```js
/* Gap Scout dashboard: small progressive enhancements. Every page also works without this file. */
(function () {
  "use strict";
  document.documentElement.classList.add("js");

  function hide(toast) {
    toast.classList.add("hide");
    setTimeout(function () { toast.remove(); }, 300);
  }

  function initToasts() {
    document.querySelectorAll("[data-toast]").forEach(function (toast) {
      var close = toast.querySelector("[data-dismiss]");
      if (close) close.addEventListener("click", function () { hide(toast); });
      if (!toast.hasAttribute("data-sticky")) setTimeout(function () { hide(toast); }, 5000);
    });
    // Forget ?msg= / ?err= so a reload does not show the same toast again.
    var url = new URL(window.location.href);
    if (url.searchParams.has("msg") || url.searchParams.has("err")) {
      url.searchParams.delete("msg");
      url.searchParams.delete("err");
      window.history.replaceState(null, "", url.pathname + url.search + url.hash);
    }
  }

  function initConfirm() {
    // <form data-confirm="Question?"> asks before submitting (replaces inline onsubmit handlers).
    document.addEventListener("submit", function (event) {
      var form = event.target;
      var message = form instanceof HTMLFormElement ? form.getAttribute("data-confirm") : null;
      if (message && !window.confirm(message)) event.preventDefault();
    });
  }

  function initOpeners() {
    // <button data-open="#id"> opens <details id="id"> and focuses its first field.
    document.querySelectorAll("[data-open]").forEach(function (button) {
      button.addEventListener("click", function () {
        var target = document.querySelector(button.getAttribute("data-open"));
        if (!target) return;
        target.open = true;
        target.scrollIntoView({ behavior: "smooth", block: "start" });
        var field = target.querySelector("textarea, input, select");
        if (field) field.focus({ preventScroll: true });
      });
    });
  }

  var GO = { h: "/", g: "/gaps", a: "/pipeline", k: "/knowledge", s: "/settings" };

  function typing(el) {
    return el && (el.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(el.tagName));
  }

  function initShortcuts() {
    // "g" then h/g/a/k/s jumps to a section; "/" focuses the search box where there is one.
    var gPressedAt = 0;
    document.addEventListener("keydown", function (event) {
      if (event.ctrlKey || event.metaKey || event.altKey || typing(event.target)) return;
      if (event.key === "/") {
        var search = document.querySelector("[data-search]");
        if (search) {
          event.preventDefault();
          search.focus();
          search.select();
        }
        return;
      }
      if (gPressedAt && Date.now() - gPressedAt < 1000 && GO[event.key]) {
        gPressedAt = 0;
        window.location.href = GO[event.key];
        return;
      }
      gPressedAt = event.key === "g" ? Date.now() : 0;
    });
  }

  initToasts();
  initConfirm();
  initOpeners();
  initShortcuts();
})();
```

- [ ] **Step 7: Create `scout/web/templates/_ui.html`**

```jinja
{# Shared UI macros. Import in every page: {% import "_ui.html" as ui with context %} #}

{% macro icon(name, cls="") -%}
<svg class="icon{{ ' ' ~ cls if cls }}" aria-hidden="true" focusable="false"><use href="/static/icons.svg?v={{ ASSET_VERSION }}#i-{{ name }}"></use></svg>
{%- endmacro %}

{% macro chip(text, tone="gray", title="", cls="") -%}
<span{% if title %} title="{{ title }}"{% endif %} class="chip chip-{{ tone }}{{ ' ' ~ cls if cls }}">{{ text }}</span>
{%- endmacro %}

{% macro status_chip(kind, value) -%}
{%- if kind == "task" %}{% set l = task_label(value) %}{% elif kind == "run" %}{% set l = run_label(value) %}{% else %}{% set l = status_label(value) %}{% endif -%}
{{ chip(l.text, l.tone, l.tip) }}
{%- endmacro %}

{% macro date(d) -%}
{%- if d %}<time datetime="{{ d | iso }}" title="{{ d | iso }}">{{ d | when }}</time>{% else %}—{% endif -%}
{%- endmacro %}

{% macro tabs(items, active) -%}
<nav class="tabs" aria-label="Pages in this section">
  {%- for href, label in items %}<a href="{{ href }}"{% if href == active %} aria-current="page"{% endif %}>{{ label }}</a>{% endfor -%}
</nav>
{%- endmacro %}

{% macro page_header(title, subtitle="") -%}
<header class="page-head">
  <div class="page-head-text">
    <h1>{{ title }}</h1>
    {% if subtitle %}<p class="subtitle">{{ subtitle }}</p>{% endif %}
  </div>
  {% if caller is defined %}<div class="page-actions">{{ caller() }}</div>{% endif %}
</header>
{%- set items = SECTION_TABS.get(active_section(request.url.path)) -%}
{%- if items and request.url.path in items | map("first") | list %}
{{ tabs(items, request.url.path) }}
{%- endif %}
{%- endmacro %}

{% macro score_bar(score) -%}
{%- set band = score_band(score) -%}
{%- if score is none -%}
<div class="score">{{ chip(band[0], band[1], "The scout has not scored this gap yet.") }}</div>
{%- else -%}
{%- set w = [[score, 0] | max, 100] | min -%}
<div class="score" title="Score {{ score }} of 100 ({{ band[0] }})">
  <span class="meter" role="meter" aria-label="Score" aria-valuemin="0" aria-valuemax="100" aria-valuenow="{{ w }}"><span class="meter-fill fill-{{ band[1] }}" style="width:{{ w }}%"></span></span>
  <span class="score-num">{{ score }}</span><span class="score-word">{{ band[0] }}</span>
</div>
{%- endif -%}
{%- endmacro %}

{% macro part_bar(label, value, top) -%}
{%- set v = [[value or 0, 0] | max, top] | min -%}
<div class="part">
  <span class="part-label">{{ label }}</span>
  <span class="meter"><span class="meter-fill fill-indigo" style="width:{{ (v / top * 100) | round(1) }}%"></span></span>
  <span class="part-num">{{ v }}/{{ top }}</span>
</div>
{%- endmacro %}

{% macro stat_tile(label, value, sub="", href="", progress=none, icon_name="") -%}
{%- set body -%}
  <span class="tile-label">{% if icon_name %}{{ icon(icon_name) }}{% endif %}{{ label }}</span>
  <span class="tile-value">{{ value }}</span>
  {% if sub %}<span class="tile-sub">{{ sub }}</span>{% endif %}
  {% if progress is not none %}{% set p = [[progress | float, 0] | max, 100] | min %}<span class="meter" aria-hidden="true"><span class="meter-fill {{ 'fill-red' if p >= 100 else 'fill-amber' if p >= 80 else 'fill-indigo' }}" style="width:{{ p | round(1) }}%"></span></span>{% endif %}
{%- endset -%}
{%- if href %}<a class="tile" href="{{ href }}">{{ body }}</a>{% else %}<div class="tile">{{ body }}</div>{% endif -%}
{%- endmacro %}

{% macro empty_state(icon_name, text, href="", link_text="") -%}
<div class="empty">{{ icon(icon_name, "empty-icon") }}<p>{{ text }}</p>{% if href %}<a class="btn sm" href="{{ href }}">{{ link_text }}</a>{% endif %}</div>
{%- endmacro %}

{% macro post_button(action, label, fields={}, cls="", icon_name="", confirm="") -%}
<form class="inline" method="post" action="{{ action }}"{% if confirm %} data-confirm="{{ confirm }}"{% endif %}>
  {%- for k, v in fields.items() %}<input type="hidden" name="{{ k }}" value="{{ v }}">{% endfor -%}
  <button class="btn{{ ' ' ~ cls if cls }}">{% if icon_name %}{{ icon(icon_name) }}{% endif %}<span>{{ label }}</span></button>
</form>
{%- endmacro %}

{% macro confirm_button(action, label, message, fields={}, cls="danger", icon_name="x") -%}
{{ post_button(action, label, fields, cls, icon_name, message) }}
{%- endmacro %}

{% macro gap_actions(g, finalists, flagged, next) -%}
{%- set status_url = "/gaps/%d/status" | format(g.id) -%}
{%- set flag_url = "/gaps/%d/flag" | format(g.id) -%}
<div class="actions">
  {%- if g.status != "killed" %}
    {%- if g.id in flagged %}{{ post_button(flag_url, "Cancel check", {"next": next, "unflag": "1"}, "sm", "x") }}
    {%- else %}{{ post_button(flag_url, "Check this again", {"next": next}, "sm", "refresh-cw") }}{% endif %}
    {{ post_button("/gaps/%d/finalist" | format(g.id), "Remove finalist" if g.id in finalists else "Make finalist", {"next": next}, "sm", "star") }}
  {%- endif %}
  {%- if g.status not in ("parked", "killed") %}
    {{ post_button(status_url, "Put on hold", {"next": next, "action": "park"}, "sm", "pause") }}
  {%- endif %}
  {%- if g.status != "killed" %}
    {{ confirm_button(status_url, "Reject", "Reject this gap? It stays rejected until you reopen it.", {"next": next, "action": "kill"}, "sm danger") }}
  {%- endif %}
  {%- if g.status in ("parked", "killed") %}
    {{ post_button(status_url, "Reopen", {"next": next, "action": "reopen"}, "sm", "rotate-ccw") }}
  {%- endif %}
</div>
{%- endmacro %}
```

- [ ] **Step 8: Replace `base.html`, `login.html` and `error.html`**

`scout/web/templates/base.html`:

```jinja
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
  <meta name="referrer" content="no-referrer">
  <meta name="color-scheme" content="light dark">
  <title>{% block title %}Scout{% endblock %} · Gap Scout</title>
  <link rel="preload" href="/static/fonts/inter-latin-wght-normal.woff2" as="font" type="font/woff2" crossorigin>
  <link rel="stylesheet" href="/static/app.css?v={{ ASSET_VERSION }}">
  <script src="/static/app.js?v={{ ASSET_VERSION }}" defer></script>
</head>
{%- import "_ui.html" as ui with context %}
{%- macro nav_links(here, badges) %}
  {%- for s in SECTIONS %}
  <a href="{{ s.href }}"{% if s.key == here %} aria-current="page"{% endif %}>{{ ui.icon(s.icon) }}<span>{{ s.label }}</span>{% set n = badges.get(s.key, 0) %}{% if n %}<span class="count" data-badge="{{ s.key }}" title="{{ n }} to look at">{{ n }}</span>{% endif %}</a>
  {%- endfor %}
{%- endmacro %}
<body class="{{ 'bare' if hide_nav else 'shell' }}">
{%- if not hide_nav %}
  {%- set here = active_section(request.url.path) %}
  {%- set badges = nav_badges or {} %}
  <aside class="sidebar">
    <a class="brand" href="/">{{ ui.icon("target") }}<span>Gap Scout</span></a>
    <nav class="side-nav" aria-label="Main">{{ nav_links(here, badges) }}</nav>
    <div class="side-foot">
      {%- if nav_phase %}{% set ph = phase_info(nav_phase) %}
      <div class="phase-pill" title="The scout's current phase">Phase<strong>{{ ph.text }}</strong>{{ ph.tip }}</div>
      {%- endif %}
      <form method="post" action="/logout"><button class="btn ghost block">{{ ui.icon("log-out") }}<span>Log out</span></button></form>
    </div>
  </aside>
  <header class="topbar">
    <a class="brand" href="/" aria-label="Gap Scout home">{{ ui.icon("target") }}</a>
    <span class="topbar-title">{{ self.title() }}</span>
    <form method="post" action="/logout"><button aria-label="Log out">{{ ui.icon("log-out") }}</button></form>
  </header>
  <nav class="tabbar" aria-label="Main (phone)">{{ nav_links(here, badges) }}</nav>
{%- endif %}
  <main class="content">
    <div class="toasts" aria-live="polite">
      {%- if msg %}
      <div class="toast ok" role="status" data-toast>{{ ui.icon("circle-check") }}<span>{{ msg }}</span><button type="button" class="toast-x js-only" data-dismiss aria-label="Dismiss">{{ ui.icon("x") }}</button></div>
      {%- endif %}
      {%- if err %}
      <div class="toast err" role="alert" data-toast data-sticky>{{ ui.icon("triangle-alert") }}<span>{{ err }}</span><button type="button" class="toast-x js-only" data-dismiss aria-label="Dismiss">{{ ui.icon("x") }}</button></div>
      {%- endif %}
    </div>
    {% block content %}{% endblock %}
  </main>
</body>
</html>
```

`scout/web/templates/login.html`:

```jinja
{% extends "base.html" %}
{% import "_ui.html" as ui with context %}
{% set hide_nav = True %}
{% block title %}Log in{% endblock %}
{% block content %}
<div class="card auth-card">
  <div class="brand">{{ ui.icon("target") }}<span>Gap Scout</span></div>
  <p class="muted">Your daily scout for business gaps in Kosovo.</p>
  <form method="post" action="/login" class="form-stack">
    <label for="token">Dashboard token</label>
    <input id="token" name="token" type="password" autocomplete="current-password" required autofocus>
    <button class="btn primary block">Log in</button>
  </form>
</div>
{% endblock %}
```

`scout/web/templates/error.html`:

```jinja
{% extends "base.html" %}
{% import "_ui.html" as ui with context %}
{% set hide_nav = True %}
{% block title %}Something went wrong{% endblock %}
{% block content %}
<div class="card auth-card">
  {{ ui.empty_state("triangle-alert", message, "/", "Back to Home") }}
</div>
{% endblock %}
```

- [ ] **Step 9: Run the full suite**

Run: `TEST_DATABASE_URL=postgresql://scout:scout@localhost:55432/scout_test_t1 uv run pytest -q && uv run ruff check scout tests && uv run ruff format --check scout tests`
Expected: all tests pass, including every old page test: the old templates still extend
`base.html` and keep the legacy classes `card`, `muted`, `row`, `badge`, `flash` and
`button.primary`, which `app.css` still styles.

- [ ] **Step 10: Commit**

```bash
git add scout/web/static/app.css scout/web/static/app.js scout/web/templates/_ui.html \
  scout/web/templates/base.html scout/web/templates/login.html scout/web/templates/error.html \
  scout/web/app.py scout/web/auth.py scout/web/deps.py tests/test_web_shell.py
git commit -m "feat(web): design system, sidebar/tab-bar shell, toasts and nav badges" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01363MMeXh1CX8iLQ1mddmG7" | cat
```

---

### Task 3: Home page

**Files:**
- Modify: `scout/web/pages/today.py`
- Replace: `scout/web/templates/today.html`
- Test: `tests/test_web_app.py` (append tests; keep the existing ones)
- Test DB: `scout_test_t2`

**Interfaces:**
- Consumes:
  - from Task 2: `deps.page(..., session=)` and the `_ui.html` macros (`page_header`, `icon`,
    `chip`, `date`, `post_button`, `stat_tile`, `status_chip`, `empty_state`) and the `eur`
    filter;
  - from Task 1: `ui.greeting`, `ui.next_run_text` and `ui.OPEN_GAP_STATUSES`;
  - `founder.effective_cap(session, settings, phase, day)`.
- Produces: the Home page. Nothing else depends on it.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_web_app.py`:

```python
def test_home_needs_you_lists_every_actionable_item(web, db_session):
    from datetime import date

    repo.save_brief(db_session, run_id=None, day=date(2026, 10, 9), markdown="# Hi")
    repo.add_field_check(db_session, gap_id=None, question="q?", why="w", due=date(2026, 10, 11))
    t = repo.enqueue_task(db_session, profile="news-scan", payload={}, priority=40)
    t.status = "failed"
    db_session.commit()
    html = web.get("/").text
    assert "New brief for" in html and "1 field check to answer" in html
    assert "1 failed task" in html and "All clear" not in html
    assert 'href="#brief"' in html and 'action="/brief/' in html


def test_home_is_all_clear_on_an_empty_database(web):
    html = web.get("/").text
    assert "All clear ✓" in html
    for tile in ("Spent today", "This month", "Open gaps", "Next run"):
        assert tile in html
    assert "Today 0" in html or "Tomorrow 0" in html  # next run, e.g. "Tomorrow 07:00"
    assert any(g in html for g in ("Good morning", "Good afternoon", "Good evening"))


def test_home_counts_open_gaps_and_survives_a_zero_cap(web, db_session):
    from scout import founder
    from scout.clock import local_today
    from scout.seeds import seed_all

    seed_all(db_session)
    a, _ = repo.propose_gap(db_session, title="Pet sitting", sector_slug="pets")
    b, _ = repo.propose_gap(db_session, title="Vet booking", sector_slug="pets")
    b.status = "killed"
    db_session.commit()
    founder.set_today_cap(db_session, "0", today=local_today("Europe/Belgrade"))
    r = web.get("/")
    assert r.status_code == 200 and "of €0.00 limit" in r.text
    assert '<span class="tile-value">1</span>' in r.text  # only the open gap counts
```

- [ ] **Step 2: Run the tests and confirm they fail**

Run: `TEST_DATABASE_URL=postgresql://scout:scout@localhost:55432/scout_test_t2 uv run pytest tests/test_web_app.py -q`
Expected: the three new tests FAIL (for example, "All clear" is not found).

- [ ] **Step 3: Replace `scout/web/pages/today.py`**

```python
"""Home: what needs the founder, four numbers, the last run and the latest brief."""

from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from scout import founder
from scout.db import repo
from scout.db.models import Gap, Task
from scout.web import ui
from scout.web.deps import back, get_session, local_day, page

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
def today_page(request: Request, session: Session = Depends(get_session)):
    settings = request.app.state.settings
    day = local_day(request)
    now = datetime.now(UTC)
    now_local = now.astimezone(ZoneInfo(settings.timezone))
    brief = repo.latest_brief(session)
    read_id = (repo.get_setting(session, "brief_read") or {}).get("id")
    phase = (repo.get_setting(session, "phase") or {}).get("value") or settings.phase

    def count(stmt) -> int:
        return session.scalar(stmt) or 0

    return page(
        request,
        "today.html",
        session=session,
        brief=brief,
        unread=brief is not None and brief.id != read_id,
        last=repo.last_run(session),
        spent_today=repo.spent_on(session, day),
        spent_month=repo.spent_between(session, day.replace(day=1), day),
        cap=founder.effective_cap(session, settings, phase, day),
        open_checks=len(repo.open_field_checks(session)),
        failed=count(select(func.count()).select_from(Task).where(Task.status == "failed")),
        open_gaps=count(
            select(func.count()).select_from(Gap).where(Gap.status.in_(ui.OPEN_GAP_STATUSES))
        ),
        greeting=ui.greeting(now_local),
        now_local=now_local,
        next_run=ui.next_run_text(now, settings.timezone),
    )


@router.post("/brief/{brief_id}/read")
def mark_read(brief_id: int, session: Session = Depends(get_session)):
    repo.set_setting(session, "brief_read", {"id": brief_id})
    return back("/")
```

- [ ] **Step 4: Replace `scout/web/templates/today.html`**

```jinja
{% extends "base.html" %}
{% import "_ui.html" as ui with context %}
{% block title %}Home{% endblock %}
{% block content %}
{{ ui.page_header(greeting, now_local.strftime("%A, %B ") ~ now_local.day ~ " — what needs you, and what the scout did.") }}

<section class="card needs" aria-labelledby="needs-title">
  <h2 id="needs-title">{{ ui.icon("inbox") }} Needs you</h2>
  {% if not ((brief and unread) or open_checks or failed) %}
  <p class="all-clear">{{ ui.icon("circle-check") }} All clear ✓ — nothing needs you right now.</p>
  {% else %}
  <ul class="todo">
    {% if brief and unread %}
    <li>
      <span class="what">{{ ui.icon("sparkles") }} New brief for {{ ui.date(brief.day) }} {{ ui.chip("New", "indigo", cls="new-brief") }}</span>
      <a class="btn sm primary" href="#brief">Read</a>
      {{ ui.post_button("/brief/%d/read" | format(brief.id), "Mark read", cls="sm") }}
    </li>
    {% endif %}
    {% if open_checks %}
    <li>
      <span class="what">{{ ui.icon("message-circle-question") }} {{ open_checks }} field check{{ "" if open_checks == 1 else "s" }} to answer</span>
      <a class="btn sm primary" href="/field-checks">Answer</a>
    </li>
    {% endif %}
    {% if failed %}
    <li>
      <span class="what">{{ ui.icon("triangle-alert") }} {{ failed }} failed task{{ "" if failed == 1 else "s" }}</span>
      <a class="btn sm" href="/pipeline">Review</a>
    </li>
    {% endif %}
  </ul>
  {% endif %}
</section>

<div class="tiles">
  {{ ui.stat_tile("Spent today", spent_today | eur, "of " ~ (cap | eur) ~ " limit", "/costs", (spent_today / cap * 100) if cap else (100 if spent_today else 0), "euro") }}
  {{ ui.stat_tile("This month", spent_month | eur, "since the 1st", "/costs", none, "calendar") }}
  {{ ui.stat_tile("Open gaps", open_gaps, "new, being checked or confirmed", "/gaps", none, "lightbulb") }}
  {{ ui.stat_tile("Next run", next_run, "the scout runs by itself every morning", "/pipeline", none, "clock") }}
</div>

<p class="last-run">
  {% if last %}
  Last run {{ ui.status_chip("run", last.status) }} {{ ui.date(last.day) }} · {{ last.tasks_done }} done · {{ last.tasks_failed }} failed · {{ last.spent_eur | eur }}
  <a href="/pipeline">Details →</a>
  {% else %}
  No runs yet — the first one starts by itself ({{ next_run }}).
  {% endif %}
</p>

<section id="brief" class="card">
  {% if brief %}
  <div class="article-head">
    <h2>Brief for {{ ui.date(brief.day) }}</h2>
    {% if unread %}{{ ui.chip("New", "indigo", cls="new-brief") }}{% endif %}
  </div>
  <article class="md prose">{{ brief.markdown | md }}</article>
  {% else %}
  {{ ui.empty_state("sparkles", "No brief yet. The first one appears after the next run.") }}
  {% endif %}
</section>
{% endblock %}
```

- [ ] **Step 5: Run the tests and confirm they pass**

Run: `TEST_DATABASE_URL=postgresql://scout:scout@localhost:55432/scout_test_t2 uv run pytest -q && uv run ruff check scout tests && uv run ruff format --check scout tests`
Expected: all pass. The existing tests still hold: "No brief yet", the `New` chip, and the absence
of `'new-brief">New'` after Mark read.

- [ ] **Step 6: Commit**

```bash
git add scout/web/pages/today.py scout/web/templates/today.html tests/test_web_app.py
git commit -m "feat(web): Home page with Needs-you card, stat tiles and readable brief" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01363MMeXh1CX8iLQ1mddmG7" | cat
```

---

### Task 4: Gaps — board, detail and field checks

**Files:**
- Modify:
  - `scout/web/pages/gaps.py`
  - `scout/web/pages/field_checks.py` (success message only)
- Create: `scout/web/templates/_gaps.html`
- Replace:
  - `scout/web/templates/gaps.html`
  - `scout/web/templates/gap.html`
  - `scout/web/templates/field_checks.html`
- Delete: `scout/web/templates/_gap_actions.html`
- Test: `tests/test_web_gaps.py` (update one assertion; append tests)
- Test DB: `scout_test_t3`

**Interfaces:**
- Consumes:
  - from Task 2: the `_ui.html` macros, including `gap_actions(g, finalists, flagged, next)`,
    `score_bar`, `part_bar`, `chip`, `status_chip`, `date`, `empty_state` and `page_header`;
  - the globals `status_label`, `flag_label`, `presence_label` and `SCORE_PARTS`;
  - the filters `pct` and `md`.
- Produces:
  - **`_gaps.html` macros:**
    - `gap_card(g, sector_name, finalists, flagged, next)`;
    - `gap_chips(g, is_finalist, is_flagged)`;
    - `readable(value)`.
  - **Constants in `gaps.py`:** `BOARD_COLUMNS = ("candidate", "verifying", "verified", "parked")`,
    which replaces `STATUS_ORDER`.

- [ ] **Step 1: Write the failing tests**

In `tests/test_web_gaps.py`:
- change the import line to `from scout.db.models import GapAssessment` (added under the existing
  imports);
- replace the two lines of `test_answer_field_check_from_the_page` that check the success page
  (the `ok = …` line and the `assert ok.status_code == 200 …` line);
- append the new tests.

```python
    ok = web.post(f"/field-checks/{fc.id}/answer", data={"answer": "Two vets, no sitters"})
    assert ok.status_code == 200 and "Answer saved" in ok.text
```

```python
def test_empty_gap_pages_explain_themselves(web):
    assert "No gaps yet" in web.get("/gaps").text
    assert "No questions for you right now" in web.get("/field-checks").text


def test_board_uses_plain_labels_and_collapses_rejected(web, gap):
    html = web.get("/gaps").text
    for label in ("New idea", "Being checked", "Confirmed gap", "On hold", "Rejected"):
        assert label in html, label
    assert '<details class="rejected' in html
    assert "Check this again" in html and "Make finalist" in html and "Put on hold" in html
    assert 'data-confirm="Reject this gap?' in html and "onsubmit=" not in html
    assert '<a href="/field-checks">Field checks</a>' in html  # section tab
    assert "not scored yet" in html


def test_status_filter_for_phones(web, gap, db_session):
    assert 'href="/gaps?status=candidate" aria-current="true"' in web.get("/gaps").text
    parked = web.get("/gaps", params={"status": "parked"}).text
    assert 'href="/gaps?status=parked" aria-current="true"' in parked
    for junk in ("killed", "<script>alert(1)</script>", "nope"):
        r = web.get("/gaps", params={"status": junk})
        assert r.status_code == 200
        assert 'href="/gaps?status=candidate" aria-current="true"' in r.text
        assert "<script>alert(1)</script>" not in r.text
    gap.status = "parked"
    db_session.commit()
    assert 'href="/gaps?status=parked" aria-current="true"' in web.get("/gaps").text


def test_status_change_message_uses_plain_words(web, gap):
    r = web.post(f"/gaps/{gap.id}/status", data={"action": "park"})
    assert r.status_code == 200 and "Pet sitting: On hold" in r.text


def test_detail_shows_scores_and_readable_critic_json(web, gap, db_session):
    html = web.get(f"/gaps/{gap.id}").text
    assert "not scored yet" in html and "No critic review yet" in html
    db_session.add(
        GapAssessment(
            gap_id=gap.id,
            model="claude-opus-5-5",
            strategist=None,
            critic={"verdict": "kill", "concerns": ["payments", {"who": "banks"}], "score": None},
            score_total=31,
            confidence=0.4,
        )
    )
    gap.score_total = 31
    gap.score_components = {"proof": 10, "absence": 12, "demand": 5, "founder_fit": 4, "risk": 0}
    db_session.commit()
    html = web.get(f"/gaps/{gap.id}").text
    assert "poor" in html and "Proven elsewhere" in html and "10/25" in html
    assert "<dt>Verdict</dt>" in html and "payments" in html and "<dt>Who</dt>" in html
    assert "40% sure" in html and "Raw data" in html
```

- [ ] **Step 2: Run the tests and confirm they fail**

Run: `TEST_DATABASE_URL=postgresql://scout:scout@localhost:55432/scout_test_t3 uv run pytest tests/test_web_gaps.py -q`
Expected: the new tests FAIL (for example, "No gaps yet" and "New idea" are not found).

- [ ] **Step 3: Update `scout/web/pages/gaps.py`**

Replace the module docstring, imports, `STATUS_ORDER` and `gaps_page`. Also change the success
messages in `gap_status`, `gap_flag` and `gap_finalist` as shown. `gap_detail` and every route
signature stay unchanged.

```python
"""Gaps board: status columns (a filter on phones), detail, and the founder's buttons."""

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
from scout.web import ui
from scout.web.deps import back, get_session, local_day, local_path, page

router = APIRouter()
BOARD_COLUMNS = ("candidate", "verifying", "verified", "parked")  # Rejected sits below, collapsed


@router.get("/gaps", response_class=HTMLResponse)
def gaps_page(request: Request, status: str = "", session: Session = Depends(get_session)):
    all_gaps = repo.list_gaps(session)
    columns = [(st, [g for g in all_gaps if g.status == st]) for st in BOARD_COLUMNS]
    if status not in BOARD_COLUMNS:  # phones show one column: default to the first non-empty one
        status = next((st for st, items in columns if items), BOARD_COLUMNS[0])
    return page(
        request,
        "gaps.html",
        columns=columns,
        rejected=[g for g in all_gaps if g.status == "killed"],
        selected=status,
        total=len(all_gaps),
        sectors={s.id: s for s in repo.list_sectors(session)},
        finalists=set(founder.finalists(session)),
        flagged=set(founder.flagged(session)),
    )
```

In `gap_status`, change the success line:

```python
    return back(local_path(next), msg=f"{gap.title}: {ui.status_label(gap.status).text}")
```

In `gap_flag`, change the success `msg=`:

```python
        msg="Check cancelled" if unflag == "1" else "Check requested — the scout re-checks it next run",
```

In `gap_finalist`, change the success line:

```python
    return back(
        local_path(next), msg="Added to finalists" if gap_id in ids else "Removed from finalists"
    )
```

In `scout/web/pages/field_checks.py`, change the final line of `answer`:

```python
    return back(
        "/field-checks",
        msg="Answer saved — the scout will re-check this gap" if fc.gap_id else "Answer saved",
    )
```

- [ ] **Step 4: Create `scout/web/templates/_gaps.html`**

```jinja
{# Gap-page macros. Import with: {% import "_gaps.html" as gaps_ui with context %} #}
{% import "_ui.html" as ui with context %}

{% macro gap_chips(g, is_finalist, is_flagged) -%}
{%- if is_finalist or is_flagged or g.critic_flag %}
<div class="chips">
  {%- if is_finalist %}{{ ui.chip("★ Finalist", "indigo", "You picked this as a finalist.") }}{% endif %}
  {%- if is_flagged %}{{ ui.chip("Check requested", "amber", "The scout re-checks this gap in its next run.") }}{% endif %}
  {%- if g.critic_flag %}{% set f = flag_label(g.critic_flag) %}{{ ui.chip(f.text, f.tone, f.tip) }}{% endif %}
</div>
{%- endif %}
{%- endmacro %}

{% macro gap_card(g, sector_name, finalists, flagged, next) -%}
<article class="gap-card">
  <a class="gap-title" href="/gaps/{{ g.id }}">{{ g.title }}</a>
  {% if sector_name %}<div class="gap-meta">{{ sector_name }}</div>{% endif %}
  {{ ui.score_bar(g.score_total if g.score_components else none) }}
  {{ gap_chips(g, g.id in finalists, g.id in flagged) }}
  <div class="gap-foot">
    <span>updated {{ ui.date(g.updated_at) }}</span>
    <details class="more">
      <summary class="btn sm ghost">Actions</summary>
      {{ ui.gap_actions(g, finalists, flagged, next) }}
    </details>
  </div>
</article>
{%- endmacro %}

{% macro readable(v) -%}
{%- if v is none %}—
{%- elif v is string %}{{ v }}
{%- elif v is mapping %}<dl class="kv">{% for k, x in v.items() %}<dt>{{ k | string | replace("_", " ") | capitalize }}</dt><dd>{{ readable(x) }}</dd>{% endfor %}</dl>
{%- elif v is iterable %}<ul>{% for x in v %}<li>{{ readable(x) }}</li>{% endfor %}</ul>
{%- else %}{{ v }}
{%- endif %}
{%- endmacro %}
```

- [ ] **Step 5: Replace `gaps.html`, `gap.html` and `field_checks.html`, and delete `_gap_actions.html`**

`scout/web/templates/gaps.html`:

```jinja
{% extends "base.html" %}
{% import "_ui.html" as ui with context %}
{% import "_gaps.html" as gaps_ui with context %}
{% block title %}Gaps{% endblock %}
{% block content %}
{{ ui.page_header("Gaps", "Business ideas the scout found that may be missing in Kosovo.") }}
{% if total == 0 %}
<div class="card">
  {{ ui.empty_state("lightbulb", "No gaps yet — the scout proposes gaps after it maps sectors and finds proven models.", "/pipeline", "See what the scout is doing") }}
</div>
{% else %}
<nav class="filter" aria-label="Show gaps by status">
  {%- for st, items in columns %}
  <a href="/gaps?status={{ st }}"{% if st == selected %} aria-current="true"{% endif %}>{{ status_label(st).text }} <span class="n">{{ items | length }}</span></a>
  {%- endfor %}
</nav>
<div class="board">
  {% for st, items in columns %}{% set l = status_label(st) %}
  <section class="column{{ ' is-selected' if st == selected }}" aria-labelledby="col-{{ st }}">
    <h2 class="column-head" id="col-{{ st }}" title="{{ l.tip }}"><span class="dot dot-{{ l.tone }}"></span>{{ l.text }}<span class="n">{{ items | length }}</span></h2>
    {% for g in items %}
      {{ gaps_ui.gap_card(g, sectors[g.sector_id].name_en if g.sector_id in sectors else "", finalists, flagged, "/gaps?status=" ~ st) }}
    {% else %}
      <p class="column-empty">Nothing here.</p>
    {% endfor %}
  </section>
  {% endfor %}
</div>
<details class="rejected card">
  <summary><span class="dot dot-red"></span>{{ status_label("killed").text }}<span class="n">{{ rejected | length }}</span></summary>
  {% for g in rejected %}
    {{ gaps_ui.gap_card(g, sectors[g.sector_id].name_en if g.sector_id in sectors else "", finalists, flagged, "/gaps") }}
  {% else %}
    <p class="muted">Nothing rejected.</p>
  {% endfor %}
</details>
{% endif %}
{% endblock %}
```

`scout/web/templates/gap.html`:

```jinja
{% extends "base.html" %}
{% import "_ui.html" as ui with context %}
{% import "_gaps.html" as gaps_ui with context %}
{% block title %}{{ gap.title }}{% endblock %}
{% block content %}
{% set latest = assessments[0] if assessments else none %}
<a class="back" href="/gaps">← Gaps</a>
<header class="page-head">
  <div class="page-head-text">
    <h1>{{ gap.title }}</h1>
    <div class="chips">
      {{ ui.status_chip("gap", gap.status) }}
      {% if sector %}{{ ui.chip(sector.name_en) }}{% endif %}
      {{ ui.chip(presence_label(gap.presence_level), "gray", "How present this already is in Kosovo") }}
    </div>
    {{ gaps_ui.gap_chips(gap, is_finalist, is_flagged) }}
  </div>
  <div class="page-actions">{{ ui.gap_actions(gap, [gap.id] if is_finalist else [], [gap.id] if is_flagged else [], "/gaps/" ~ gap.id) }}</div>
</header>
<div class="grid-2">
  <div class="stack">
    <section class="card">
      <h2>Summary</h2>
      <div class="md prose">{{ gap.hypothesis_md | md }}</div>
      {% if gap.why_not_yet_md %}<h3>Why nobody does it yet</h3><div class="md prose">{{ gap.why_not_yet_md | md }}</div>{% endif %}
      {% if gap.test_plan_md %}<h3>How to test it cheaply</h3><div class="md prose">{{ gap.test_plan_md | md }}</div>{% endif %}
    </section>
    <section class="card">
      <h2>{{ ui.icon("trending-up") }} Why it might work</h2>
      {% if model %}
      <p><strong>{{ model.name }}</strong> — {{ model.description }}</p>
      {% if model.markets %}<p class="muted">Works in: {{ model.markets | join(", ") }}</p>{% endif %}
      <ul class="links">
        {%- for u in (model.source_urls or []) if u is string %}{% set t = u | trim %}
        <li>{% if (t | lower).startswith("http://") or (t | lower).startswith("https://") %}<a href="{{ t }}" rel="noopener noreferrer" target="_blank">{{ t }} {{ ui.icon("external-link") }}</a>{% else %}{{ u }}{% endif %}</li>
        {%- endfor %}
      </ul>
      {% else %}
      {{ ui.empty_state("search", "No proven model linked yet — the scout links one when it finds where this works.") }}
      {% endif %}
    </section>
    <section class="card">
      <h2>{{ ui.icon("flag") }} Critic's concerns</h2>
      {% if latest and latest.critic %}
      {{ gaps_ui.readable(latest.critic) }}
      <details><summary class="muted">Raw data</summary><pre>{{ latest.critic | tojson(indent=2) }}</pre></details>
      {% else %}
      {{ ui.empty_state("message-circle-question", "No critic review yet — the scout reviews a gap when it checks it.") }}
      {% endif %}
    </section>
  </div>
  <div class="stack">
    <section class="card">
      <h2>{{ ui.icon("target") }} Scores</h2>
      {{ ui.score_bar(gap.score_total if gap.score_components else none) }}
      {% if gap.score_components %}
        {% for key, label, top in SCORE_PARTS if key in gap.score_components %}{{ ui.part_bar(label, gap.score_components[key], top) }}{% endfor %}
      {% endif %}
      <p class="muted">Confidence {{ gap.confidence | pct }}</p>
    </section>
    <section class="card">
      <h2>{{ ui.icon("message-circle-question") }} Field checks</h2>
      {% if checks %}
      <ul class="list">
        {% for fc in checks %}
        <li><div class="grow"><strong>{{ fc.question }}</strong>
          {% if fc.why %}<div class="muted">{{ fc.why }}</div>{% endif %}
          <div>{% if fc.answer %}{{ fc.answer }}{% else %}<a href="/field-checks">Waiting for your answer →</a>{% endif %}</div>
        </div></li>
        {% endfor %}
      </ul>
      {% else %}
      <p class="muted">No questions about this gap.</p>
      {% endif %}
    </section>
    <section class="card">
      <h2>{{ ui.icon("clock") }} History</h2>
      {% if assessments %}
      <ol class="timeline">
        {% for a in assessments %}
        <li><span class="tl-dot"></span>
          <div class="tl-head">{{ ui.date(a.created_at) }} · score {{ a.score_total }} · {{ a.confidence | pct }} sure</div>
          <div class="muted">{{ a.model }}</div>
        </li>
        {% endfor %}
      </ol>
      {% else %}
      <p class="muted">Not assessed yet.</p>
      {% endif %}
    </section>
  </div>
</div>
{% endblock %}
```

`scout/web/templates/field_checks.html`:

```jinja
{% extends "base.html" %}
{% import "_ui.html" as ui with context %}
{% block title %}Field checks{% endblock %}
{% block content %}
{{ ui.page_header("Field checks", "Quick questions only you can answer — from what you know or one phone call (≤ 3 minutes each).") }}
{% for fc in open_checks %}
<form class="card check" method="post" action="/field-checks/{{ fc.id }}/answer">
  <p class="q">{{ fc.question }}</p>
  {% if fc.why %}<p class="why"><strong>Why it matters:</strong> {{ fc.why }}</p>{% endif %}
  <p class="meta">
    {%- if fc.gap_id and fc.gap_id in gaps %}For <a href="/gaps/{{ fc.gap_id }}">{{ gaps[fc.gap_id].title }}</a>{% endif %}
    {%- if fc.due %} · due {{ ui.date(fc.due) }}{% endif %}
  </p>
  <label class="sr-only" for="answer-{{ fc.id }}">Your answer</label>
  <textarea id="answer-{{ fc.id }}" name="answer" required placeholder="What did you find out?"></textarea>
  <div class="form-foot">
    <button class="btn primary">{{ ui.icon("check") }}<span>Save answer</span></button>
    <span class="hint">The scout turns your answer into a fact and re-checks the gap.</span>
  </div>
</form>
{% else %}
<div class="card">
  {{ ui.empty_state("circle-check", "No questions for you right now. The scout asks when only a local check can settle a gap.") }}
</div>
{% endfor %}
{% if answered %}
<details class="card">
  <summary>Answered recently <span class="muted">({{ answered | length }})</span></summary>
  <ul class="list">
    {% for fc in answered %}
    <li><div class="grow"><strong>{{ fc.question }}</strong>
      <div class="muted">{{ fc.answer or "—" }}{% if fc.answered_at %} · {{ ui.date(fc.answered_at) }}{% endif %}</div>
    </div></li>
    {% endfor %}
  </ul>
</details>
{% endif %}
{% endblock %}
```

Then delete the old partial:

```bash
git rm scout/web/templates/_gap_actions.html | cat
```

- [ ] **Step 6: Run the tests and confirm they pass**

Run: `TEST_DATABASE_URL=postgresql://scout:scout@localhost:55432/scout_test_t3 uv run pytest -q && uv run ruff check scout tests && uv run ruff format --check scout tests`
Expected: all pass. The existing assertions still hold: `action="/gaps/{id}/status"`,
"Finalist" (from "★ Finalist"), "Sitters in Prizren?" and the javascript href guard.

- [ ] **Step 7: Commit**

```bash
git add scout/web/pages/gaps.py scout/web/pages/field_checks.py scout/web/templates/_gaps.html \
  scout/web/templates/gaps.html scout/web/templates/gap.html scout/web/templates/field_checks.html \
  tests/test_web_gaps.py
git commit -m "feat(web): gaps board with phone filter, readable gap detail, field-check cards" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01363MMeXh1CX8iLQ1mddmG7" | cat
```

---

### Task 5: Activity — pipeline and journal

**Files:**
- Modify: `scout/web/pages/pipeline.py`
- Replace:
  - `scout/web/templates/pipeline.html`
  - `scout/web/templates/journal.html`
- Test: `tests/test_web_pipeline.py` (update assertions; append tests)
- Test DB: `scout_test_t4`

**Interfaces:**
- Consumes:
  - from Task 2: the `_ui.html` macros (`page_header`, `icon`, `chip`, `status_chip`, `date`,
    `post_button`, `empty_state`);
  - the globals `profile_label`, `task_target` and `phase_info`;
  - the filters `eur` and `md`.
  - from Task 1: `ui.next_run_text`.
- Produces: nothing other tasks use.

- [ ] **Step 1: Write the failing tests**

In `tests/test_web_pipeline.py`:
- replace the `r = web.get("/pipeline")` assertion block of `test_queue_runs_failures_and_retry`;
- replace the last two lines of `test_journal_shows_scout_and_founder_entries`;
- append the new tests.

```python
    r = web.get("/pipeline")
    assert f"#{q.id}" in r.text and "boom: &lt;b&gt;bad&lt;/b&gt;" in r.text
    assert "Culture research" in r.text and "News scan" in r.text and "Retry" in r.text
    assert f"Run #{run.id}" in r.text and "Foundation" in r.text
    assert re.search(r'data-stat="failed">.*?<strong>1</strong>', r.text, re.S)
    assert re.search(r'data-stat="waiting">.*?<strong>1</strong>', r.text, re.S)
```

```python
    r = web.get("/journal")
    assert "<strong>pets</strong>" in r.text and "Founder: kill gap #1" in r.text
    assert "Scout · run #1" in r.text and ">You</span>" in r.text
```

Add `import re` to the imports at the top of the file. Then append:

```python
def test_empty_activity_pages_explain_themselves(web):
    pipeline = web.get("/pipeline").text
    assert "Nothing waiting" in pipeline and "No runs yet" in pipeline
    assert "Nothing in the journal yet" in web.get("/journal").text


def test_add_task_form_uses_plain_names(web):
    html = web.get("/pipeline").text
    assert '<option value="map-sector">Map a sector</option>' in html
    assert "0–100, higher runs sooner" in html and "Queue task" in html
    assert '<a href="/journal">Journal</a>' in html  # section tab


def test_queued_message_names_the_task_plainly(web, db_session):
    seed_all(db_session)
    r = web.post("/tasks", data={"profile": "map-sector", "sector": "pets", "priority": "70"})
    assert "Queued task #" in r.text and "Map a sector" in r.text


def test_a_dry_run_shows_as_plan_only(web, db_session):
    run = repo.start_run(
        db_session,
        day=date(2026, 10, 9),
        phase="foundation",
        budget_cap_eur=Decimal("1.00"),
        started_at=datetime(2026, 10, 9, 6, tzinfo=UTC),
    )
    run.status = "dry-run"
    db_session.commit()
    r = web.get("/pipeline")
    assert r.status_code == 200 and "Plan only" in r.text
```

- [ ] **Step 2: Run the tests and confirm they fail**

Run: `TEST_DATABASE_URL=postgresql://scout:scout@localhost:55432/scout_test_t4 uv run pytest tests/test_web_pipeline.py -q`
Expected: FAIL (for example, "Culture research" and "Nothing waiting" are not found).

- [ ] **Step 3: Update `scout/web/pages/pipeline.py`**

Replace the imports and `pipeline_page`, and change the success message of `add_task`.
`_int_or_none`, `retry` and the route signatures stay the same.

```python
"""Pipeline: failures to retry, tasks waiting for the next run, running tasks and past runs."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from scout import founder
from scout.db import repo
from scout.db.models import Run, Task
from scout.founder import FounderError
from scout.web import ui
from scout.web.deps import back, get_session, local_day, page

router = APIRouter()


@router.get("/pipeline", response_class=HTMLResponse)
def pipeline_page(request: Request, session: Session = Depends(get_session)):
    last = repo.last_run(session)
    failed = select(Task).where(Task.status == "failed")
    return page(
        request,
        "pipeline.html",
        queue=repo.queued_tasks(session),
        running=session.scalars(
            select(Task).where(Task.status == "running").order_by(Task.id)
        ).all(),
        failed=session.scalars(failed.order_by(Task.id.desc()).limit(20)).all(),
        failed_count=session.scalar(select(func.count()).select_from(failed.subquery())) or 0,
        last=last,
        last_tasks=repo.tasks_for_run(session, last.id if last else None),
        runs=session.scalars(select(Run).order_by(Run.id.desc()).limit(14)).all(),
        profiles=founder.TASK_PROFILES,
        sectors=repo.list_sectors(session),
        next_run=ui.next_run_text(datetime.now(UTC), request.app.state.settings.timezone),
    )
```

In `add_task`, change the success line:

```python
    return back("/pipeline", msg=f"Queued task #{task.id}: {ui.profile_label(task.profile)}")
```

- [ ] **Step 4: Replace `pipeline.html` and `journal.html`**

`scout/web/templates/pipeline.html`:

```jinja
{% extends "base.html" %}
{% import "_ui.html" as ui with context %}
{% block title %}Pipeline{% endblock %}
{% block content %}
{% macro what(t) -%}
<strong>{{ profile_label(t.profile) }}</strong>{% set target = task_target(t.payload) %}{% if target %} · {{ target }}{% endif %}
{%- endmacro %}
{{ ui.page_header("Pipeline", "What the scout is doing: failures to retry, tasks waiting for the next run, and past runs.") }}

<div class="strip">
  <div class="stat" data-stat="waiting">{{ ui.icon("clock") }}<span><strong>{{ queue | length }}</strong> waiting</span></div>
  <div class="stat" data-stat="running">{{ ui.icon("activity") }}<span><strong>{{ running | length }}</strong> running</span></div>
  <div class="stat" data-stat="failed">{{ ui.icon("triangle-alert") }}<span><strong>{{ failed_count }}</strong> failed</span></div>
</div>

{% if failed %}
<section class="card">
  <h2>{{ ui.icon("triangle-alert") }} Failed — retry or leave them</h2>
  <ul class="list">
    {% for t in failed %}
    <li>
      <span class="id">#{{ t.id }}</span>
      <span class="grow">{{ what(t) }} <span class="muted">· tried {{ t.attempts }}× · {{ ui.date(t.finished_at or t.created_at) }}</span></span>
      {{ ui.post_button("/tasks/%d/retry" | format(t.id), "Retry", cls="sm", icon_name="refresh-cw") }}
      {% if t.error %}<details><summary class="muted">Show error</summary><pre>{{ t.error }}</pre></details>{% endif %}
    </li>
    {% endfor %}
  </ul>
</section>
{% endif %}

<section class="card">
  <h2>{{ ui.icon("clock") }} Waiting for the next run</h2>
  {% if queue %}
  <ul class="list">
    {% for t in queue %}
    <li>
      <span class="id">#{{ t.id }}</span>
      <span class="grow">{{ what(t) }}</span>
      <span class="muted">priority {{ t.priority }} · about {{ t.est_cost_eur | eur }}</span>
    </li>
    {% endfor %}
  </ul>
  {% else %}
  {{ ui.empty_state("clock", "Nothing waiting. The scout plans its own tasks at the start of each daily run; add one below to push something first.") }}
  {% endif %}
</section>

{% if running %}
<section class="card">
  <h2>{{ ui.icon("activity") }} Running now</h2>
  <ul class="list">
    {% for t in running %}
    <li><span class="id">#{{ t.id }}</span><span class="grow">{{ what(t) }}</span>{{ ui.status_chip("task", t.status) }}<span class="muted">started {{ ui.date(t.started_at) }}</span></li>
    {% endfor %}
  </ul>
</section>
{% endif %}

<form class="card" method="post" action="/tasks">
  <h2>{{ ui.icon("plus") }} Add a task</h2>
  <div class="fields">
    <div class="field"><label for="profile">What</label>
      <select id="profile" name="profile" required>{% for p in profiles %}<option value="{{ p }}">{{ profile_label(p) }}</option>{% endfor %}</select></div>
    <div class="field"><label for="sector">Sector</label>
      <select id="sector" name="sector"><option value="">— none —</option>{% for s in sectors %}<option value="{{ s.slug }}">{{ s.name_en }}</option>{% endfor %}</select></div>
    <div class="field"><label for="gap_id">Gap id</label>
      <input id="gap_id" name="gap_id" inputmode="numeric" placeholder="e.g. 12"></div>
    <div class="field"><label for="theme">Culture theme</label>
      <input id="theme" name="theme" placeholder="e.g. weddings"></div>
    <div class="field"><label for="priority">Priority</label>
      <input id="priority" name="priority" inputmode="numeric" value="70"><small>0–100, higher runs sooner</small></div>
  </div>
  <p class="hint">“Map a sector” and “Find proven models” need a sector; “Check a gap” and “Deep dive” need a gap id; “Culture research” needs a theme.</p>
  <div class="form-foot"><button class="btn primary">{{ ui.icon("plus") }}<span>Queue task</span></button></div>
</form>

<section class="card">
  <h2>{{ ui.icon("list-checks") }} Recent runs</h2>
  {% if runs %}
  <ol class="timeline">
    {% for r in runs %}{% set ph = phase_info(r.phase) %}
    <li><span class="tl-dot"></span>
      <div class="tl-head"><strong>Run #{{ r.id }}</strong> {{ ui.date(r.day) }} {{ ui.status_chip("run", r.status) }} {{ ui.chip(ph.text, "gray", ph.tip) }}</div>
      <div class="muted">{{ r.tasks_done }} done · {{ r.tasks_failed }} failed · spent {{ r.spent_eur | eur }} of {{ r.budget_cap_eur | eur }}</div>
      {% if r.summary_md %}<details><summary class="muted">Summary</summary><div class="md prose">{{ r.summary_md | md }}</div></details>{% endif %}
      {% if last and r.id == last.id and last_tasks %}
      <details><summary class="muted">Tasks in this run ({{ last_tasks | length }})</summary>
        <ul class="list">
          {% for t in last_tasks %}
          <li>
            <span class="id">#{{ t.id }}</span><span class="grow">{{ what(t) }}</span>
            {{ ui.status_chip("task", t.status) }}<span class="muted">{{ t.actual_cost_eur | eur }}</span>
            {% if t.error or t.result_md %}<details><summary class="muted">Result</summary>
              {% if t.error %}<pre>{{ t.error }}</pre>{% endif %}
              <div class="md prose">{{ t.result_md | md }}</div>
            </details>{% endif %}
          </li>
          {% endfor %}
        </ul>
      </details>
      {% endif %}
    </li>
    {% endfor %}
  </ol>
  {% else %}
  {{ ui.empty_state("list-checks", "No runs yet — the first one starts by itself (" ~ next_run ~ ").") }}
  {% endif %}
</section>
{% endblock %}
```

`scout/web/templates/journal.html`:

```jinja
{% extends "base.html" %}
{% import "_ui.html" as ui with context %}
{% block title %}Journal{% endblock %}
{% block content %}
{{ ui.page_header("Journal", "A diary of what the scout did and learned each day, plus the changes you made.") }}
{% if entries %}
<ol class="timeline">
  {% for e in entries %}
  <li><span class="tl-dot"></span>
    <div class="tl-head">
      {{ ui.date(e.day) }}
      {% if e.run_id %}{{ ui.chip("Scout · run #" ~ e.run_id, "indigo", "Written by the scout after a run") }}
      {% else %}{{ ui.chip("You", "green", "Changes you made in the dashboard or the command line") }}{% endif %}
    </div>
    <div class="card">
      {% if e.did_md %}<h3>What happened</h3><div class="md prose">{{ e.did_md | md }}</div>{% endif %}
      {% if e.learned_md %}<h3>Learned</h3><div class="md prose">{{ e.learned_md | md }}</div>{% endif %}
      {% if e.tomorrow_md %}<h3>Next</h3><div class="md prose">{{ e.tomorrow_md | md }}</div>{% endif %}
    </div>
  </li>
  {% endfor %}
</ol>
{% else %}
<div class="card">
  {{ ui.empty_state("book-open", "Nothing in the journal yet — the scout writes an entry after every run, and your changes appear here too.") }}
</div>
{% endif %}
{% endblock %}
```

- [ ] **Step 5: Run the tests and confirm they pass**

Run: `TEST_DATABASE_URL=postgresql://scout:scout@localhost:55432/scout_test_t4 uv run pytest -q && uv run ruff check scout tests && uv run ruff format --check scout tests`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add scout/web/pages/pipeline.py scout/web/templates/pipeline.html \
  scout/web/templates/journal.html tests/test_web_pipeline.py
git commit -m "feat(web): Activity section — pipeline with summary strip and runs timeline, journal timeline" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01363MMeXh1CX8iLQ1mddmG7" | cat
```

---

### Task 6: Knowledge, Settings and Budget & costs

**Files:**
- Modify: `scout/web/pages/costs.py`
- Replace:
  - `scout/web/templates/knowledge.html`
  - `scout/web/templates/sector.html`
  - `scout/web/templates/digest.html`
  - `scout/web/templates/settings.html`
  - `scout/web/templates/costs.html`
- Test: `tests/test_web_knowledge.py` (append tests; keep the existing ones)
- Test DB: `scout_test_t5`

**Interfaces:**
- Consumes:
  - from Task 2: the `_ui.html` macros (`page_header` with `{% call %}`, `icon`, `chip`,
    `status_chip`, `date`, `post_button`, `empty_state`);
  - the globals `phase_info` and `presence_label`;
  - the filters `eur`, `pct`, `iso`, `when` and `md`.
  - from Task 1: `ui.phase_info`.
  - `scout.director.planner.PHASE_RULES`.
- Produces: nothing other tasks use.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_web_knowledge.py`:

```python
def test_empty_knowledge_and_settings_explain_themselves(web):
    assert "No sectors yet" in web.get("/knowledge").text
    assert "No facts match" in web.get("/knowledge", params={"q": "zzz"}).text
    settings = web.get("/settings").text
    assert "No finalists yet" in settings and "Foundation" in settings
    assert "building the knowledge base" in settings
    assert '<a href="/costs">Budget &amp; costs</a>' in settings  # section tab


def test_knowledge_cards_and_digest_editor(web, db_session):
    seed_all(db_session)
    repo.set_digest(db_session, "sector:pets", "Pets", "## Vets", now=NOW)
    html = web.get("/knowledge").text
    assert 'href="/knowledge/sectors/pets"' in html and "not mapped yet" in html
    assert "data-search" in html
    digest = web.get("/knowledge/digests/sector:pets").text
    assert 'data-open="#edit"' in digest and '<details class="card" id="edit">' in digest
    assert 'action="/knowledge/digests/sector:pets"' in digest


def test_costs_chart_cap_source_and_clear(web, db_session):
    from scout.clock import local_today

    html = web.get("/costs").text
    assert html.count('class="bar-col') == 14
    assert "Foundation phase cap" in html and "Clear my cap" not in html
    founder.set_today_cap(db_session, "1.25", today=local_today("Europe/Belgrade"))
    html = web.get("/costs").text
    assert "your cap for today" in html and "Clear my cap" in html and "€1.25" in html


def test_settings_lists_use_plain_buttons(web, db_session):
    seed_all(db_session)
    g, _ = repo.propose_gap(db_session, title="Pet sitting", sector_slug="pets")
    founder.toggle_finalist(db_session, g.id, today=date(2026, 10, 9))
    founder.flag_gap(db_session, g.id, today=date(2026, 10, 9))
    html = web.get("/settings").text
    assert "Remove" in html and "Cancel check" in html and "New idea" in html
```

- [ ] **Step 2: Run the tests and confirm they fail**

Run: `TEST_DATABASE_URL=postgresql://scout:scout@localhost:55432/scout_test_t5 uv run pytest tests/test_web_knowledge.py -q`
Expected: the new tests FAIL (for example, "No sectors yet" and `bar-col` are not found).

- [ ] **Step 3: Replace `scout/web/pages/costs.py`**

```python
"""Budget & costs: today's limit and where it comes from, 14 days of spend, cost per model, and
source health; the founder can set or clear today's cap."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from scout import founder
from scout.db import repo
from scout.db.models import Cost, Source
from scout.director.planner import PHASE_RULES
from scout.founder import FounderError
from scout.web import ui
from scout.web.deps import back, get_session, local_day, page

router = APIRouter()
CHART_DAYS = 14


@router.get("/costs", response_class=HTMLResponse)
def costs_page(request: Request, session: Session = Depends(get_session)):
    settings = request.app.state.settings
    day = local_day(request)
    month_start = day.replace(day=1)
    total = func.sum(Cost.cost_eur)
    by_day = dict(
        session.execute(
            select(Cost.day, total)
            .where(Cost.day >= day - timedelta(days=CHART_DAYS - 1), Cost.day <= day)
            .group_by(Cost.day)
        ).all()
    )
    bars = [
        (d, by_day.get(d) or Decimal("0"))
        for d in (day - timedelta(days=n) for n in range(CHART_DAYS - 1, -1, -1))
    ]
    per_model = session.execute(
        select(Cost.kind, Cost.provider, Cost.model, func.count(), total)
        .where(Cost.day >= month_start, Cost.day <= day)
        .group_by(Cost.kind, Cost.provider, Cost.model)
        .order_by(total.desc())
    ).all()
    phase = (repo.get_setting(session, "phase") or {}).get("value") or settings.phase
    founder_cap = founder.today_cap(session, day)
    if founder_cap is not None:
        cap_source = "your cap for today"
    elif PHASE_RULES[phase]["cap"] <= Decimal(settings.daily_budget_eur):
        cap_source = f"the {ui.phase_info(phase).text} phase cap"
    else:
        cap_source = "the daily budget (SCOUT_DAILY_BUDGET_EUR on Render)"
    return page(
        request,
        "costs.html",
        day=day,
        spent_today=repo.spent_on(session, day),
        spent_month=repo.spent_between(session, month_start, day),
        cap=founder.effective_cap(session, settings, phase, day),
        cap_source=cap_source,
        founder_cap=founder_cap,
        max_cap=founder.MAX_TODAY_CAP_EUR,
        bars=bars,
        bar_max=max(eur for _, eur in bars),
        per_model=per_model,
        sources=session.scalars(select(Source).order_by(Source.tier, Source.name)).all(),
    )


@router.post("/costs/cap")
def set_cap(request: Request, eur: str = Form(""), session: Session = Depends(get_session)):
    try:
        value = founder.set_today_cap(session, eur, today=local_day(request))
    except FounderError as e:
        return back("/costs", err=str(e))
    return back(
        "/costs", msg=f"Today's cap: €{value}" if value is not None else "Today's cap cleared"
    )
```

The test asserts "Foundation phase cap" while the page prints "the Foundation phase cap"; the
substring matches.

- [ ] **Step 4: Replace the five templates**

`scout/web/templates/knowledge.html`:

```jinja
{% extends "base.html" %}
{% import "_ui.html" as ui with context %}
{% block title %}Knowledge{% endblock %}
{% block content %}
{{ ui.page_header("Knowledge", "Everything the scout has learned about Kosovo: sectors, businesses, proven models and facts.") }}
<form class="search" method="get" action="/knowledge" role="search">
  <label class="sr-only" for="q">Search facts</label>
  <input id="q" name="q" value="{{ q }}" placeholder="Search facts, e.g. pet sitting Prizren" data-search>
  <button class="btn primary">{{ ui.icon("search") }}<span>Search</span></button>
</form>
{% if q %}
<section class="card">
  <h2>Facts for “{{ q }}”</h2>
  {% if facts %}
  <ul class="list">
    {% for f in facts %}{% set u = (f.source_url or "") | trim %}
    <li>
      <span class="grow">{{ f.claim }}<span class="muted"> · {{ f.source_name }} · {{ f.confidence | pct }} sure · {{ ui.date(f.observed_at) }}</span></span>
      {% if (u | lower).startswith("http://") or (u | lower).startswith("https://") %}<a href="{{ u }}" rel="noopener noreferrer" target="_blank">source {{ ui.icon("external-link") }}</a>{% endif %}
    </li>
    {% endfor %}
  </ul>
  {% else %}
  {{ ui.empty_state("search", "No facts match “" ~ q ~ "”. Try fewer or different words.") }}
  {% endif %}
</section>
{% endif %}

<h2 class="section-title">Sectors</h2>
{% if sectors %}
<div class="cards">
  {% for s in sectors %}
  <a class="card sector-card" href="/knowledge/sectors/{{ s.slug }}">
    <h3>{{ s.name_en }}</h3>
    <div class="chips">
      {{ ui.chip("priority " ~ s.priority, "gray", "Higher-priority sectors are researched first") }}
      {% if s.last_mapped_at %}{{ ui.chip("Mapped", "green", "Mapped " ~ (s.last_mapped_at | when)) }}{% else %}{{ ui.chip("not mapped yet") }}{% endif %}
      {% if s.last_hunted_at %}{{ ui.chip("Hunted", "blue", "Proven models searched " ~ (s.last_hunted_at | when)) }}{% endif %}
    </div>
    <span class="stats">{{ business_counts.get(s.id, 0) }} businesses · {{ model_counts.get(s.id, 0) }} proven models</span>
  </a>
  {% endfor %}
</div>
{% else %}
<div class="card">{{ ui.empty_state("book-open", "No sectors yet — run “scout seed” once to add the starting sectors.") }}</div>
{% endif %}

<h2 class="section-title">Other notes</h2>
<section class="card">
  {% if other_digests %}
  <ul class="list">
    {% for d in other_digests %}
    <li><a class="grow" href="/knowledge/digests/{{ d.key }}">{{ d.title }}</a><span class="muted">{{ d.key }} · updated {{ ui.date(d.updated_at) }}</span></li>
    {% endfor %}
  </ul>
  {% else %}
  <p class="muted">No other notes yet.</p>
  {% endif %}
</section>
{% endblock %}
```

`scout/web/templates/sector.html`:

```jinja
{% extends "base.html" %}
{% import "_ui.html" as ui with context %}
{% block title %}{{ sector.name_en }}{% endblock %}
{% block content %}
<a class="back" href="/knowledge">← Knowledge</a>
{% call ui.page_header(sector.name_en, "What the scout knows about this sector.") %}
  {{ ui.chip("priority " ~ sector.priority) }}
  {% if sector.presence_level %}{{ ui.chip(presence_label(sector.presence_level), "gray", "How present this already is in Kosovo") }}{% endif %}
{% endcall %}
<section class="card">
  <div class="card-head">
    <h2>Digest</h2>
    {% if digest %}<a class="btn sm" href="/knowledge/digests/{{ digest.key }}">{{ ui.icon("pencil") }}<span>Edit</span></a>{% endif %}
  </div>
  {% if digest %}
  <div class="md prose">{{ digest.body_md | md }}</div>
  {% else %}
  {{ ui.empty_state("book-open", "Not mapped yet — the scout writes this digest when it maps the sector.", "/pipeline", "Queue “Map a sector”") }}
  {% endif %}
</section>
<section class="card">
  <h2>{{ ui.icon("lightbulb") }} Gaps</h2>
  {% if gaps %}
  <ul class="list">
    {% for g in gaps %}
    <li><a class="grow" href="/gaps/{{ g.id }}">{{ g.title }}</a>{{ ui.status_chip("gap", g.status) }}<span class="muted">score {{ g.score_total }}</span></li>
    {% endfor %}
  </ul>
  {% else %}
  <p class="muted">No gaps in this sector yet.</p>
  {% endif %}
</section>
<section class="card">
  <h2>Businesses in Kosovo <span class="muted">({{ businesses | length }})</span></h2>
  {% if businesses %}
  <ul class="list">
    {% for b in businesses %}
    <li><div class="grow"><strong>{{ b.name }}</strong> <span class="muted">{{ b.kind }}{% if b.city %} · {{ b.city }}{% endif %}</span>
      {% if b.note %}<div>{{ b.note }}</div>{% endif %}</div></li>
    {% endfor %}
  </ul>
  {% else %}
  <p class="muted">None found yet.</p>
  {% endif %}
</section>
<section class="card">
  <h2>Proven models abroad <span class="muted">({{ models | length }})</span></h2>
  {% if models %}
  <ul class="list">
    {% for m in models %}
    <li><div class="grow"><strong>{{ m.name }}</strong> — {{ m.description }}
      <div class="muted">Works in: {{ m.markets | join(", ") or "—" }} · {{ m.nearby_count }} nearby</div></div></li>
    {% endfor %}
  </ul>
  {% else %}
  <p class="muted">None found yet.</p>
  {% endif %}
</section>
{% endblock %}
```

`scout/web/templates/digest.html`:

```jinja
{% extends "base.html" %}
{% import "_ui.html" as ui with context %}
{% block title %}{{ digest.title }}{% endblock %}
{% block content %}
<a class="back" href="/knowledge">← Knowledge</a>
{% call ui.page_header(digest.title, "The scout's notes on this topic. It reads them before every task here, so your edits steer it.") %}
  <button type="button" class="btn js-only" data-open="#edit">{{ ui.icon("pencil") }}<span>Edit</span></button>
{% endcall %}
<p class="muted">{{ digest.key }} · updated {{ ui.date(digest.updated_at) }} · about {{ digest.token_estimate }} tokens</p>
<article class="card"><div class="md prose">{{ digest.body_md | md }}</div></article>
<details class="card" id="edit">
  <summary>Edit this digest</summary>
  <form method="post" action="/knowledge/digests/{{ digest.key }}">
    <label class="sr-only" for="body_md">Digest text (Markdown)</label>
    <textarea id="body_md" name="body_md" rows="18">{{ digest.body_md }}</textarea>
    <div class="form-foot">
      <button class="btn primary">Save</button>
      <span class="hint">Markdown. Your edit is journaled.</span>
    </div>
  </form>
</details>
{% endblock %}
```

`scout/web/templates/settings.html`:

```jinja
{% extends "base.html" %}
{% import "_ui.html" as ui with context %}
{% block title %}Settings{% endblock %}
{% block content %}
{{ ui.page_header("Settings", "How the scout works: its phase, which sectors come first, and your shortlists.") }}
{% set current = phase_info(phase) %}
<section class="card">
  <h2>{{ ui.icon("target") }} Phase</h2>
  <p>Now: <strong>{{ current.text }}</strong> — {{ current.tip }}.</p>
  <form method="post" action="/settings/phase" class="form-foot">
    <label class="sr-only" for="phase">Switch phase</label>
    <select id="phase" name="phase">
      {% for p in phases %}{% set info = phase_info(p) %}<option value="{{ p }}"{% if p == phase %} selected{% endif %}>{{ info.text }} — {{ info.tip }}</option>{% endfor %}
    </select>
    <button class="btn primary">Switch phase</button>
  </form>
</section>

<section class="card">
  <h2>{{ ui.icon("trending-up") }} Sector priorities</h2>
  <p class="hint">0–100. The scout researches higher-priority sectors first.</p>
  {% if sectors %}
  <div class="table-wrap">
    <table>
      <thead><tr><th>Sector</th><th class="num">Priority</th></tr></thead>
      <tbody>
        {% for s in sectors %}
        <tr>
          <td>{{ s.name_en }}</td>
          <td class="num">
            <form class="inline" method="post" action="/settings/sector-priority">
              <input type="hidden" name="slug" value="{{ s.slug }}">
              <input name="priority" value="{{ s.priority }}" inputmode="numeric" size="3" aria-label="Priority for {{ s.name_en }}">
              <button class="btn sm">Save</button>
            </form>
          </td>
        </tr>
        {% endfor %}
      </tbody>
    </table>
  </div>
  {% else %}
  {{ ui.empty_state("book-open", "No sectors yet — run “scout seed” once to add them.") }}
  {% endif %}
</section>

<section class="card">
  <h2>{{ ui.icon("star") }} Your lists</h2>
  <h3>Finalists</h3>
  {% if finalist_gaps %}
  <ul class="list">
    {% for g in finalist_gaps %}
    <li><a class="grow" href="/gaps/{{ g.id }}">{{ g.title }}</a>{{ ui.status_chip("gap", g.status) }}{{ ui.post_button("/gaps/%d/finalist" | format(g.id), "Remove", {"next": "/settings"}, "sm") }}</li>
    {% endfor %}
  </ul>
  {% else %}
  <p class="muted">No finalists yet — use “Make finalist” on a gap.</p>
  {% endif %}
  <h3>Checks you requested</h3>
  {% if flagged_gaps %}
  <ul class="list">
    {% for g in flagged_gaps %}
    <li><a class="grow" href="/gaps/{{ g.id }}">{{ g.title }}</a>{{ ui.status_chip("gap", g.status) }}{{ ui.post_button("/gaps/%d/flag" | format(g.id), "Cancel check", {"next": "/settings", "unflag": "1"}, "sm") }}</li>
    {% endfor %}
  </ul>
  {% else %}
  <p class="muted">None — use “Check this again” on a gap to have the scout re-check it.</p>
  {% endif %}
</section>

<section class="card">
  <h2>{{ ui.icon("settings") }} Environment</h2>
  <p class="hint">Set on Render; shown here read-only.</p>
  <dl class="kv">{% for k, v in env.items() %}<dt>{{ k }}</dt><dd>{{ v }}</dd>{% endfor %}</dl>
</section>
{% endblock %}
```

`scout/web/templates/costs.html`:

```jinja
{% extends "base.html" %}
{% import "_ui.html" as ui with context %}
{% block title %}Budget & costs{% endblock %}
{% block content %}
{{ ui.page_header("Budget & costs", "What the scout spends on AI and data, and today's spending limit.") }}
<div class="grid-2">
  <section class="card">
    <h2>{{ ui.icon("euro") }} Today's limit</h2>
    <p><span class="big-num">{{ cap | eur }}</span> <span class="muted">from {{ cap_source }}</span></p>
    <form method="post" action="/costs/cap" class="form-foot">
      <label for="eur">Your cap for today (€0–{{ max_cap }})</label>
      <input id="eur" name="eur" inputmode="decimal" size="6" value="{{ founder_cap if founder_cap is not none else '' }}">
      <button class="btn primary">Save</button>
    </form>
    {% if founder_cap is not none %}<div class="form-foot">{{ ui.post_button("/costs/cap", "Clear my cap", {"eur": ""}, "sm ghost", "x") }}</div>{% endif %}
    <p class="hint">Applies to runs started today. The daily run starts at 07:00 Kosovo time in winter (08:00 in summer), so setting it after the morning run only affects a manual run.</p>
  </section>
  <section class="card">
    <h2>{{ ui.icon("trending-up") }} Spend</h2>
    <p>Today <strong>{{ spent_today | eur }}</strong> · This month <strong>{{ spent_month | eur }}</strong></p>
    <div class="bars" role="img" aria-label="Spend per day over the last 14 days">
      {% for d, cost in bars %}
      <div class="bar-col{{ ' today' if d == day }}" title="{{ d | iso }}: {{ cost | eur }}">
        <span class="bar-track"><span class="bar" style="height:{{ ((cost / bar_max * 100) if bar_max else 0) | round(1) }}%"></span></span>
        <span class="bar-label">{{ d.day }}</span>
      </div>
      {% endfor %}
    </div>
  </section>
</div>

<section class="card">
  <h2>This month by model</h2>
  {% if per_model %}
  <div class="table-wrap">
    <table>
      <thead><tr><th>What</th><th>Provider</th><th>Model</th><th class="num">Calls</th><th class="num">Cost</th></tr></thead>
      <tbody>
        {% for kind, provider, model, n, cost in per_model %}
        <tr><td>{{ kind }}</td><td>{{ provider }}</td><td>{{ model or "—" }}</td><td class="num">{{ n }}</td><td class="num">{{ cost | eur }}</td></tr>
        {% endfor %}
      </tbody>
    </table>
  </div>
  {% else %}
  {{ ui.empty_state("euro", "No spend yet this month.") }}
  {% endif %}
</section>

<section class="card">
  <h2>Data sources</h2>
  {% if sources %}
  <div class="table-wrap">
    <table>
      <thead><tr><th>Source</th><th>Tier</th><th>Status</th><th>Last worked</th><th class="num">Failures</th></tr></thead>
      <tbody>
        {% for s in sources %}
        <tr><td>{{ s.name }}</td><td>{{ s.tier }}</td>
          <td>{% if s.enabled %}{{ ui.chip("On", "green") }}{% else %}{{ ui.chip("Off") }}{% endif %}</td>
          <td>{{ ui.date(s.last_ok_at) }}</td><td class="num">{{ s.failure_count }}</td></tr>
        {% endfor %}
      </tbody>
    </table>
  </div>
  {% else %}
  <p class="muted">No sources yet — run “scout seed” once.</p>
  {% endif %}
</section>
{% endblock %}
```

- [ ] **Step 5: Run the tests and confirm they pass**

Run: `TEST_DATABASE_URL=postgresql://scout:scout@localhost:55432/scout_test_t5 uv run pytest -q && uv run ruff check scout tests && uv run ruff format --check scout tests`
Expected: all pass. The existing assertions still hold:
- "Pets (vets, sitting, supplies)" and `<h2>Vets</h2>`;
- "Applies to runs started today", "07:00 Kosovo time in winter" and "manual run";
- "claude-sonnet-5-5" and "0.42" (rendered as €0.42);
- "foundation" (the option value) and "Saved".

- [ ] **Step 6: Commit**

```bash
git add scout/web/pages/costs.py scout/web/templates/knowledge.html scout/web/templates/sector.html \
  scout/web/templates/digest.html scout/web/templates/settings.html scout/web/templates/costs.html \
  tests/test_web_knowledge.py
git commit -m "feat(web): Knowledge cards and search, Settings cards, Budget & costs with 14-day chart" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01363MMeXh1CX8iLQ1mddmG7" | cat
```

---

### Task 7: Cross-page checks (after wave 2 is merged)

**Files:**
- Create: `tests/test_web_pages.py`
- Test DB: `scout_test`

**Interfaces:**
- Consumes: every page from Tasks 2–6. Tasks 3–6 are merged into `feat/dashboard-redesign` first.
- Produces: a regression net. If a check fails, fix the template it names (this is the one task
  allowed to touch any template), then re-run.

- [ ] **Step 1: Write the tests**

```python
# tests/test_web_pages.py
"""Checks every page must pass: renders with data, no inline handlers, icons exist, plain header."""

import re
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from scout.db import repo
from scout.db.models import GapAssessment
from scout.seeds import seed_all
from scout.web import deps

pytestmark = pytest.mark.db
SECTION_PAGES = ("/", "/gaps", "/field-checks", "/pipeline", "/journal", "/knowledge", "/costs", "/settings")
SPRITE = set(re.findall(r'id="i-([a-z-]+)"', (deps.STATIC_DIR / "icons.svg").read_text()))


@pytest.fixture
def populated(db_session):
    seed_all(db_session)
    gap, _ = repo.propose_gap(db_session, title="Pet sitting", sector_slug="pets", hypothesis_md="h")
    db_session.add(
        GapAssessment(
            gap_id=gap.id, model="m", strategist={}, critic={"risk": "x"}, score_total=50, confidence=0.5
        )
    )
    gap.score_components = {"proof": 10, "absence": 10, "demand": 10, "founder_fit": 10, "risk": 10}
    gap.score_total = 50
    db_session.commit()
    repo.add_field_check(db_session, gap_id=gap.id, question="q?", why="w", due=date(2026, 10, 11))
    run = repo.start_run(
        db_session,
        day=date(2026, 10, 9),
        phase="foundation",
        budget_cap_eur=Decimal("1.00"),
        started_at=datetime(2026, 10, 9, 6, tzinfo=UTC),
    )
    t = repo.enqueue_task(db_session, profile="news-scan", payload={}, priority=40, run_id=run.id)
    t.status, t.error = "failed", "boom"
    db_session.commit()
    repo.enqueue_task(db_session, profile="map-sector", payload={"sector": "pets"}, priority=70)
    repo.save_brief(db_session, run_id=run.id, day=date(2026, 10, 9), markdown="# Brief")
    repo.write_journal(
        db_session, run_id=run.id, day=date(2026, 10, 9), did_md="d", learned_md="", tomorrow_md=""
    )
    repo.set_digest(db_session, "sector:pets", "Pets", "## Vets", now=datetime.now(UTC))
    return gap


def _pages(gap):
    return (
        *SECTION_PAGES,
        f"/gaps/{gap.id}",
        "/knowledge/sectors/pets",
        "/knowledge/digests/sector:pets",
        "/knowledge?q=pets",
    )


def test_every_page_renders_without_inline_handlers_and_with_real_icons(web, populated):
    for path in _pages(populated):
        r = web.get(path)
        assert r.status_code == 200, path
        assert not re.search(r"\son[a-z]+=", r.text), f"inline event handler on {path}"
        assert "<script>" not in r.text, path
        for name in re.findall(r"icons\.svg\?v=[0-9a-f]+#i-([a-z-]+)", r.text):
            assert name in SPRITE, f"{path} uses missing icon {name}"


def test_every_section_page_explains_itself(web, populated):
    for path in SECTION_PAGES:
        html = web.get(path).text
        assert '<header class="page-head">' in html and '<p class="subtitle">' in html, path


def test_no_raw_status_words_on_the_board(web, populated):
    html = web.get("/gaps").text
    assert ">candidate<" not in html and ">killed<" not in html


def test_login_and_error_pages_have_no_inline_handlers(web, db_session, db_engine, settings):
    assert not re.search(r"\son[a-z]+=", web.get("/gaps/99999999999").text)
    from fastapi.testclient import TestClient

    from scout.db.base import make_session_factory
    from scout.web.app import create_app

    anon = TestClient(create_app(settings, make_session_factory(db_engine)), base_url="https://testserver")
    assert not re.search(r"\son[a-z]+=", anon.get("/login").text)


def test_the_old_gap_actions_partial_is_gone():
    assert not (deps.STATIC_DIR.parent / "templates" / "_gap_actions.html").exists()
```

- [ ] **Step 2: Run them**

Run: `TEST_DATABASE_URL=postgresql://scout:scout@localhost:55432/scout_test uv run pytest -q && uv run ruff check scout tests && uv run ruff format scout tests && uv run ruff format --check scout tests`
Expected: all pass. If one fails, the message names the page and the problem; fix that template
and re-run.

- [ ] **Step 3: Commit**

```bash
git add tests/test_web_pages.py scout/web/templates
git commit -m "test(web): cross-page checks — no inline handlers, real icons, plain headers" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01363MMeXh1CX8iLQ1mddmG7" | cat
```

---

## After the tasks

1. **Final review:** run a whole-branch review on the most capable model, with the spec and this
   plan as its references.
2. **Merge:**
   - Merge `feat/dashboard-redesign` into `main` and push.
   - Render auto-deploys `scout-dashboard`.
   - Verify `/healthz` returns 200, `/static/app.css` returns 200 without a cookie, and all
     eight section pages return 200 after login.
3. **Manual check for the founder:**
   - light and dark mode;
   - phone width 375px (bottom tab bar, gaps filter);
   - keyboard: Tab focus rings, and `g` then `g` opens Gaps.
