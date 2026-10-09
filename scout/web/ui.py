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
    """ "today", "yesterday", "Oct 7" (with the year when it is not this year)."""
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
