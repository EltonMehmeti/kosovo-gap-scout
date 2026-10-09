from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from scout.director import planner as P

MONDAY = date(2026, 10, 19)
SUNDAY = date(2026, 10, 25)
NOW = datetime(2026, 10, 19, 6, 0, tzinfo=UTC)


def _state(**over):
    base = dict(
        today=MONDAY,
        sectors=[
            P.SectorInfo("pets", "Pets", 2, "unmapped", None, None),
            P.SectorInfo("home-services", "Home services", 1, "unmapped", None, None),
            P.SectorInfo(
                "tutoring-education", "Tutoring", 1, "mapped", NOW - timedelta(days=3), None
            ),
            P.SectorInfo(
                "car-services",
                "Cars",
                2,
                "mapped",
                NOW - timedelta(days=30),
                NOW - timedelta(days=10),
            ),
        ],  # map is stale (>14 d), hunt is not (<21 d)
        culture_themes_missing=["payments-and-trust"],
        gaps=[
            P.GapInfo(1, "Pet sitting", "pets", 70, 0.5, "candidate", False),
            P.GapInfo(2, "Dentist booking", "health-booking", 65, 0.5, "verifying", True),
            P.GapInfo(3, "Dead idea", "pets", 10, 0.2, "killed", False),
        ],
        open_field_checks=0,
        spent_today=Decimal("0"),
        cap=Decimal("3.00"),
        flagged_gap_ids=[],
        deep_dive_done_this_month=False,
        done_today=set(),
    )
    base.update(over)
    return P.PlannerState(**base)


def _profiles(tasks):
    return [t.profile for t in tasks]


def test_foundation_monday_plan():
    tasks = P.plan_tasks(_state(), "foundation")
    assert _profiles(tasks) == [
        "verify-gap",
        "map-sector",
        "map-sector",
        "hunt-models",
        "chart-diff",
        "news-scan",
        "culture",
    ]
    assert [t.payload["sector"] for t in tasks if t.profile == "map-sector"] == [
        "home-services",
        "pets",
    ]
    assert tasks[0].payload["gap_id"] == 1  # a gap without a fresh presence check is verified first
    assert tasks[3].payload["sector"] == "tutoring-education"  # mapped, never hunted
    assert tasks[-1].payload["theme"] == "payments-and-trust"
    assert sum(t.est_cost_eur for t in tasks) <= Decimal("3.00")


def test_nothing_when_cap_spent_and_dedupe_against_done_today():
    assert P.plan_tasks(_state(spent_today=Decimal("3.00")), "foundation") == []
    tasks = P.plan_tasks(
        _state(done_today={("map-sector", "home-services"), ("news-scan", "")}), "foundation"
    )
    assert ("news-scan", "") not in {(t.profile, t.payload.get("sector", "")) for t in tasks}
    assert [t.payload["sector"] for t in tasks if t.profile == "map-sector"] == [
        "pets",
        "car-services",
    ]


def test_budget_trims_lowest_priority_first():
    tasks = P.plan_tasks(_state(cap=Decimal("0.80")), "foundation")
    assert _profiles(tasks) == [
        "verify-gap",
        "map-sector",
        "chart-diff",
    ]  # 0.40 + 0.35 + 0.05 = 0.80


def test_sunday_deep_dive_and_verification_phase():
    tasks = P.plan_tasks(_state(today=SUNDAY), "verification")
    assert _profiles(tasks) == ["verify-gap", "verify-gap", "news-scan", "deep-dive"]
    assert tasks[-1].payload["gap_id"] == 1 and tasks[-1].payload["gap_title"] == "Pet sitting"
    assert {t.payload["gap_id"] for t in tasks[:2]} == {1, 2}


def test_maintenance_only_flagged_gaps_and_first_sunday_deep_dive():
    assert _profiles(P.plan_tasks(_state(today=date(2026, 11, 2)), "maintenance")) == [
        "chart-diff",
        "news-scan",
    ]
    tasks = P.plan_tasks(
        _state(today=date(2026, 11, 1), flagged_gap_ids=[2]), "maintenance"
    )  # Sunday, 1st
    assert _profiles(tasks) == ["verify-gap", "news-scan", "deep-dive"] and tasks[0].priority == 90


def test_field_check_limit_blocks_verify_of_unchecked_gaps():
    tasks = P.plan_tasks(_state(open_field_checks=5), "foundation")
    verify = [t for t in tasks if t.profile == "verify-gap"]
    assert (
        verify and verify[0].payload["gap_id"] == 2
    )  # unchecked gap 1 waits for the founder's answers


def test_dedupe_keeps_two_gaps_in_same_sector():
    gaps = [
        P.GapInfo(1, "Pet sitting", "pets", 70, 0.5, "candidate", False),
        P.GapInfo(4, "Pet food", "pets", 68, 0.5, "candidate", False),
    ]
    tasks = P.plan_tasks(_state(gaps=gaps), "verification")
    assert {t.payload["gap_id"] for t in tasks if t.profile == "verify-gap"} == {1, 4}


def test_flagged_gaps_get_one_priority_verify_per_day_so_maintenance_keeps_its_news_scan():
    gaps = [P.GapInfo(i, f"G{i}", "pets", 50, 0.5, "verifying", True) for i in (4, 5, 6)]
    tasks = P.plan_tasks(_state(gaps=gaps, flagged_gap_ids=[4, 5, 6]), "maintenance")
    verify = [t for t in tasks if t.profile == "verify-gap"]
    assert len(verify) == 1 and verify[0].priority == 90 and verify[0].payload["gap_id"] == 4
    assert "news-scan" in _profiles(tasks)
    assert sum(t.est_cost_eur for t in tasks) <= P.PHASE_RULES["maintenance"]["cap"]


def test_extra_flagged_gaps_use_the_regular_verify_slots_outside_maintenance():
    gaps = [P.GapInfo(i, f"G{i}", "pets", 50, 0.5, "verifying", True) for i in (4, 5, 6)]
    tasks = P.plan_tasks(_state(gaps=gaps, flagged_gap_ids=[4, 5, 6]), "verification")
    verify = [(t.payload["gap_id"], t.priority) for t in tasks if t.profile == "verify-gap"]
    assert verify[0] == (4, 90) and len(verify) == 3  # 1 flagged slot + 2 regular slots


def test_ads_sweep_only_on_monday_with_a_token():
    assert "ads-sweep" in _profiles(P.plan_tasks(_state(social_enabled=True), "foundation"))
    assert "ads-sweep" not in _profiles(P.plan_tasks(_state(), "foundation"))
    tuesday = _state(social_enabled=True, today=MONDAY + timedelta(days=1))
    assert "ads-sweep" not in _profiles(P.plan_tasks(tuesday, "foundation"))
