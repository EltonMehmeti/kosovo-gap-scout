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
    assert [k for k, _, _ in ui.SCORE_PARTS] == [
        "proof",
        "absence",
        "demand",
        "founder_fit",
        "risk",
    ]
