from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import anthropic
import httpx
import pytest

from scout.db import repo
from scout.db.base import make_session_factory
from scout.db.repo import FactIn
from scout.director import run as R
from scout.seeds import seed_all
from scout.sources.types import ChartEntry
from scout.strategy import schemas as S
from tests.fakes import FakeClient, FakeMessage, fake_runner_factory, text_block, tool_use_block

pytestmark = pytest.mark.db
MONDAY = date(2026, 10, 19)
NOW = datetime(2026, 10, 19, 4, 0, tzinfo=UTC)  # 06:00 in Kosovo


def CLOCK():  # fixed clock: tests never read the wall clock
    return NOW


def _chart(country, limit=25, http=None):
    return [ChartEntry(1, "1", "Wolt", "Wolt", (), "u")]


def _conversation():
    return [
        FakeMessage(content=[tool_use_block("kb_search", {"query": "x"})], stop_reason="tool_use"),
        FakeMessage(content=[text_block("Did research.\nleads: none")], stop_reason="end_turn"),
    ]


@pytest.fixture
def world(db_session, db_engine, settings):
    seed_all(db_session)
    # keep the plan small: only two sectors unmapped
    for s in repo.list_sectors(db_session):
        if s.slug not in ("pets", "home-services"):
            repo.set_sector_status(db_session, s.slug, "mapped", now=NOW)
            s.last_hunted_at = NOW
    db_session.commit()
    gap, _ = repo.propose_gap(
        db_session, title="Pet sitting marketplace", sector_slug="pets", hypothesis_md="h"
    )
    repo.upsert_fact(
        db_session,
        FactIn(
            claim="Pawshake works in Croatia",
            entity_type="proven_model",
            entity_key="pet-sitting",
            confidence=0.8,
            sector_slug="pets",
            source_url="https://x",
        ),
        run_id=None,
        observed_at=NOW,
    )
    settings.director_review = False
    return {"gap": gap, "factory": make_session_factory(db_engine)}


def _client(gap_id):
    strategist = S.StrategistOutput(
        assessments=[
            S.GapAssessment(
                gap_id=gap_id,
                scores=S.ComponentScores(
                    proof=18, absence=25, demand=12, founder_fit=12, risk_penalty=4
                ),
                presence_level="absent",
                confidence=0.8,
                hard_filter_failed="none",
                reasoning="r",
                field_check_question="Ask a vet in Prizren?",
                recommended_status="verifying",
            )
        ],
        new_gaps=[],
        headline="Pets look promising",
    )
    critic = S.CriticOutput(
        verdicts=[
            S.CriticVerdict(
                gap_id=gap_id,
                strongest_objection="o",
                kosovo_killer="k",
                risk_penalty=6,
                confidence=0.7,
                decision="needs_field_check",
                field_check_question="Ask a vet in Prizren?",
            )
        ]
    )
    return FakeClient(
        [
            FakeMessage(content=[text_block("{}")], parsed_output=strategist),
            FakeMessage(content=[text_block("{}")], parsed_output=critic),
            FakeMessage(content=[text_block("Narrative.")]),
        ]
    )


def test_full_day_with_fakes(world, settings):
    calls = []
    script = [
        _conversation() for _ in range(5)
    ]  # verify, map, map, news, culture (chart-diff uses no runner)
    summary = R.run_once(
        settings,
        today=MONDAY,
        now=NOW,
        clock=CLOCK,
        client=_client(world["gap"].id),
        session_factory=world["factory"],
        apple_fetch=_chart,
        play_fetch=_chart,
        runner_factory=fake_runner_factory(script, calls),
    )
    assert summary.planned == 6 and summary.done == 6 and summary.failed == 0
    assert summary.phase == "foundation" and summary.stopped_reason == "queue empty"
    s = world["factory"]()
    run = repo.last_run(s)
    assert run.status == "done" and run.spent_eur == summary.spent_eur > 0
    assert repo.spent_on(s, MONDAY) == run.spent_eur
    assert [t.status for t in repo.tasks_for_run(s, run.id)] == ["done"] * 6
    gap = repo.get_gap(s, world["gap"].id)
    assert (
        gap.score_total == 18 + 12 + 12 + 12 + (15 - 6)
        and gap.status == "verifying"
        and gap.confidence == 0.5
    )
    assert len(repo.open_field_checks(s)) == 1
    assert "What changed" in summary.brief_md and repo.latest_brief(s).markdown == summary.brief_md
    assert repo.latest_journal(s)[0].did_md and "pets" in repo.latest_journal(s)[0].did_md
    metrics = s.query(repo.Scorecard).one().metrics
    assert metrics["days_run"] == 1 and metrics["gaps_by_status"]["verifying"] == 1
    assert all(kw["system"] is calls[0]["system"] for kw in calls)  # frozen prefix across the day
    s.close()


def test_second_run_same_day_does_not_repeat_work_and_dry_run_does_not_execute(world, settings):
    calls = []
    R.run_once(
        settings,
        today=MONDAY,
        now=NOW,
        clock=CLOCK,
        client=_client(world["gap"].id),
        session_factory=world["factory"],
        apple_fetch=_chart,
        play_fetch=_chart,
        runner_factory=fake_runner_factory([_conversation() for _ in range(5)], calls),
    )
    again = R.run_once(
        settings,
        today=MONDAY,
        now=NOW,
        clock=CLOCK,
        client=FakeClient([]),
        session_factory=world["factory"],
        apple_fetch=_chart,
        play_fetch=_chart,
        runner_factory=fake_runner_factory([], calls),
        dry_run=True,
    )
    # nothing from the first run is planned again; only the follow-up hunts that mapping unlocked
    assert (
        again.planned == 2 and again.stopped_reason == "dry run" and "hunt-models" in again.brief_md
    )
    assert "map-sector" not in again.brief_md and "news-scan" not in again.brief_md
    s = world["factory"]()
    assert repo.last_run(s).status == "dry-run"
    s.close()


def test_budget_stop_marks_run_and_leaves_queue(world, settings):
    calls = []
    summary = R.run_once(
        settings,
        today=MONDAY,
        now=NOW,
        clock=CLOCK,
        client=_client(world["gap"].id),
        session_factory=world["factory"],
        apple_fetch=_chart,
        play_fetch=_chart,
        runner_factory=fake_runner_factory([_conversation() for _ in range(5)], calls),
        budget_override=Decimal("0.45"),
    )
    assert summary.planned == 2 and summary.stopped_reason in (
        "queue empty",
        "budget",
    )  # 0.40 + 0.05 fit
    s = world["factory"]()
    assert repo.last_run(s).budget_cap_eur == Decimal("0.45")
    s.close()


def test_review_plan_drops_and_reorders(world, settings):
    s = world["factory"]()
    run = repo.start_run(
        s, day=MONDAY, phase="foundation", budget_cap_eur=Decimal("3"), started_at=NOW
    )
    t1 = repo.enqueue_task(
        s, profile="map-sector", payload={"sector": "pets"}, priority=80, run_id=run.id
    )
    t2 = repo.enqueue_task(
        s, profile="map-sector", payload={"sector": "home-services"}, priority=80, run_id=run.id
    )
    t3 = repo.enqueue_task(s, profile="news-scan", payload={}, priority=60, run_id=run.id)
    review = S.DirectorReview(
        keep_task_ids_in_order=[t3.id, t1.id],
        dropped=[S.DroppedTask(task_id=t2.id, reason="dup")],
        note="news first",
    )
    from scout.budget.guard import BudgetGuard
    from scout.llm.gateway import LLM

    llm = LLM(
        FakeClient([FakeMessage(content=[text_block("{}")], parsed_output=review)]),
        BudgetGuard(s, day=MONDAY, daily_cap_eur=Decimal("3"), run_id=run.id),
        Decimal("0.92"),
    )
    kept, notes = R.review_plan(llm, [t1, t2, t3], journal_md="")
    s.expire_all()
    assert [t.id for t in kept] == [t3.id, t1.id] and notes == [
        "dropped map-sector home-services: dup",
        "news first",
    ]
    assert repo.claim_next_task(s, "w", now=NOW).id == t3.id
    assert s.get(repo.Task, t2.id).status == "skipped"
    s.close()


def test_time_limit_stops_before_first_task_but_still_writes_brief(world, settings):
    late = NOW + timedelta(minutes=settings.run_max_minutes + 1)
    summary = R.run_once(
        settings,
        today=MONDAY,
        now=NOW,
        clock=lambda: late,
        client=_client(world["gap"].id),
        session_factory=world["factory"],
        apple_fetch=_chart,
        play_fetch=_chart,
        runner_factory=fake_runner_factory([], []),
    )
    assert summary.stopped_reason == "time limit" and summary.done == 0
    s = world["factory"]()
    assert repo.last_run(s).status == "done" and repo.latest_brief(s) is not None
    s.close()


def test_failing_task_and_strategy_error_do_not_end_the_day(world, settings):
    def boom(**kwargs):
        raise RuntimeError("runner exploded")

    err = anthropic.APIConnectionError(request=httpx.Request("POST", "http://x"))
    summary = R.run_once(
        settings,
        today=MONDAY,
        now=NOW,
        clock=CLOCK,
        client=FakeClient([err, err]),
        session_factory=world["factory"],
        apple_fetch=_chart,
        play_fetch=_chart,
        runner_factory=boom,
    )
    assert summary.failed >= 1 and summary.done >= 1  # chart-diff still ran
    s = world["factory"]()
    assert repo.last_run(s).status == "done" and repo.latest_brief(s).markdown == summary.brief_md
    assert "strategy skipped" in repo.latest_journal(s)[0].tomorrow_md
    s.close()


def test_deep_dive_sets_month_setting_and_test_plan(world, settings):
    sunday = date(2026, 10, 25)
    s = world["factory"]()
    repo.enqueue_task(
        s, profile="deep-dive", payload={"gap_id": world["gap"].id, "gap_title": "x"}, priority=99
    )
    s.close()
    R.run_once(
        settings,
        today=sunday,
        now=NOW,
        clock=CLOCK,
        client=_client(world["gap"].id),
        session_factory=world["factory"],
        apple_fetch=_chart,
        play_fetch=_chart,
        runner_factory=fake_runner_factory([_conversation() for _ in range(6)], []),
    )
    s = world["factory"]()
    assert repo.get_setting(s, "deep-dive-done:2026-10-01") is True
    assert repo.get_gap(s, world["gap"].id).test_plan_md
    s.close()
