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
from scout.strategy.strategist import Strategist
from scout.worker.research import ResearchWorker, TaskOutcome
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
    assert summary.planned == 2 and summary.stopped_reason == "queue empty"  # 0.40 + 0.05 fit
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
    # five runner tasks fail (after one retry each, counted once); chart-diff still ran
    assert summary.failed == 5 and summary.done == 1
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


def _kw(world, **extra):
    base = dict(
        today=MONDAY,
        now=NOW,
        clock=CLOCK,
        session_factory=world["factory"],
        apple_fetch=_chart,
        play_fetch=_chart,
    )
    return base | extra


def test_unexpected_error_closes_run_failed_and_releases_task(world, settings, monkeypatch):
    def boom(self, *a, **k):
        raise ValueError("not an llm error")

    monkeypatch.setattr(Strategist, "apply", boom)
    with pytest.raises(ValueError):
        R.run_once(
            settings,
            **_kw(
                world,
                client=_client(world["gap"].id),
                runner_factory=fake_runner_factory([_conversation() for _ in range(5)], []),
            ),
        )
    s = world["factory"]()
    run = repo.last_run(s)
    assert run.status == "failed" and run.finished_at is not None and "ValueError" in run.summary_md
    assert not [t for t in repo.tasks_for_run(s, run.id) if t.status == "running"]
    s.close()


def test_stale_running_task_is_released_at_start(world, settings):
    s = world["factory"]()
    t = repo.enqueue_task(s, profile="news-scan", payload={}, priority=1)
    repo.claim_next_task(s, "ghost", now=NOW - timedelta(hours=3))
    s.close()
    R.run_once(
        settings,
        **_kw(
            world,
            client=_client(world["gap"].id),
            runner_factory=fake_runner_factory([_conversation() for _ in range(6)], []),
        ),
    )
    s = world["factory"]()
    assert s.get(repo.Task, t.id).status == "done"
    s.close()


def test_budget_stop_before_claim_leaves_task_queued_untouched(world, settings):
    s = world["factory"]()
    t = repo.enqueue_task(s, profile="map-sector", payload={"sector": "pets"}, priority=99)
    s.close()
    summary = R.run_once(
        settings,
        **_kw(
            world,
            client=_client(world["gap"].id),
            runner_factory=fake_runner_factory([], []),
            budget_override=Decimal("0.10"),
        ),
    )
    assert summary.stopped_reason == "budget" and summary.done == 0 and summary.failed == 0
    s = world["factory"]()
    task = s.get(repo.Task, t.id)
    assert task.status == "queued" and task.attempts == 0
    assert repo.last_run(s).status == "done"
    s.close()


def test_cap_already_spent_refuses_work_but_writes_brief(world, settings):
    s = world["factory"]()
    repo.record_cost(
        s,
        repo.CostRecord("llm", "anthropic", "claude-sonnet-5-5", {}, Decimal("3.00")),
        day=MONDAY,
        run_id=None,
    )
    s.close()
    client = FakeClient([])
    summary = R.run_once(
        settings,
        **_kw(world, client=client, runner_factory=fake_runner_factory([], [])),
    )
    assert summary.stopped_reason == "budget" and summary.planned == 0 and summary.done == 0
    s = world["factory"]()
    assert repo.tasks_for_run(s, summary.run_id) == [] and repo.latest_brief(s) is not None
    assert repo.last_run(s).status == "done"
    s.close()


def test_dry_run_has_no_side_effects(world, settings):
    s = world["factory"]()
    queued = repo.enqueue_task(s, profile="news-scan", payload={}, priority=5)
    before = s.query(repo.Task).count()
    s.close()
    client = FakeClient([])
    settings.director_review = True
    summary = R.run_once(
        settings,
        **_kw(world, client=client, runner_factory=fake_runner_factory([], []), dry_run=True),
    )
    assert summary.stopped_reason == "dry run" and summary.planned >= 2
    assert client.messages.calls == []
    s = world["factory"]()
    assert s.query(repo.Task).count() == before
    t = s.get(repo.Task, queued.id)
    assert t.status == "queued" and t.run_id is None and t.priority == 5
    assert repo.last_run(s).status == "dry-run"
    s.close()


@pytest.mark.parametrize("flag", ["budget_stopped", "truncated"])
def test_cut_short_task_does_not_commit_success_effects(world, settings, monkeypatch, flag):
    def cut(self, task_id, profile, brief, ctx):
        return TaskOutcome(
            summary_md="(stopped early)",
            stop_reason="end_turn",
            iterations=1,
            cost_eur=Decimal("0.01"),
            restarts=0,
            tool_calls=0,
            truncated=flag == "truncated",
            budget_stopped=flag == "budget_stopped",
        )

    monkeypatch.setattr(ResearchWorker, "run", cut)
    s = world["factory"]()
    repo.enqueue_task(
        s, profile="deep-dive", payload={"gap_id": world["gap"].id, "gap_title": "x"}, priority=99
    )
    s.close()
    R.run_once(
        settings,
        **_kw(world, client=_client(world["gap"].id), runner_factory=fake_runner_factory([], [])),
    )
    s = world["factory"]()
    assert repo.get_setting(s, "deep-dive-done:2026-10-01") is None
    assert repo.get_gap(s, world["gap"].id).test_plan_md == ""
    assert repo.get_sector(s, "pets").status == "unmapped"  # map-sector pets was cut short too
    s.close()


def test_post_processing_error_does_not_requeue_paid_task(world, settings, monkeypatch):
    calls = []

    def bad(session, task, outcome, **kw):
        raise RuntimeError("side effect failed")

    monkeypatch.setattr(R, "_apply_outcome", bad)
    R.run_once(
        settings,
        **_kw(
            world,
            client=_client(world["gap"].id),
            runner_factory=fake_runner_factory([_conversation() for _ in range(5)], calls),
        ),
    )
    assert len(calls) == 5  # each research task ran exactly once
    s = world["factory"]()
    assert repo.last_run(s).status == "done"
    assert not [t for t in s.query(repo.Task) if t.status == "queued"]
    s.close()


def test_strategist_skipped_when_no_fresh_facts(world, settings):
    later = NOW + timedelta(hours=1)  # the seeded fact predates this run
    client = FakeClient([FakeMessage(content=[text_block("Narrative.")])])

    def boom(**kwargs):
        raise RuntimeError("x")

    R.run_once(
        settings,
        **_kw(world, now=later, clock=lambda: later, client=client, runner_factory=boom),
    )
    assert not [c for c in client.messages.calls if "output_format" in c]


def test_dry_run_on_capped_day_writes_nothing(world, settings):
    s = world["factory"]()
    repo.record_cost(
        s,
        repo.CostRecord("llm", "anthropic", "claude-sonnet-5-5", {}, Decimal("3.00")),
        day=MONDAY,
        run_id=None,
    )
    tasks_before = s.query(repo.Task).count()
    s.close()
    client = FakeClient([])
    summary = R.run_once(settings, **_kw(world, client=client, runner_factory=None, dry_run=True))
    assert summary.stopped_reason == "dry run" and client.messages.calls == []
    s = world["factory"]()
    assert repo.last_run(s).status == "dry-run"
    assert repo.latest_brief(s) is None and repo.latest_journal(s) == []
    assert s.query(repo.Scorecard).count() == 0 and s.query(repo.Task).count() == tasks_before
    s.close()


class _Crash(BaseException):
    pass


def test_crash_after_claim_requeues_exactly_that_task(world, settings):
    def crash(**kwargs):
        raise _Crash("simulated kill")

    s = world["factory"]()
    other = repo.enqueue_task(s, profile="news-scan", payload={}, priority=1, run_id=999)
    other = repo.claim_next_task(s, "other-run", now=NOW)  # another run's claimed task
    s.close()
    with pytest.raises(_Crash):
        R.run_once(
            settings,
            **_kw(world, client=_client(world["gap"].id), runner_factory=crash),
        )
    s = world["factory"]()
    run = repo.last_run(s)
    assert run.status == "failed"
    running = [t for t in s.query(repo.Task) if t.status == "running"]
    assert [t.id for t in running] == [other.id]  # the other run's claim is untouched
    claimed = [t for t in repo.tasks_for_run(s, run.id) if t.attempts == 0 and t.status == "queued"]
    assert claimed  # the crashed task was released with its attempt given back
    s.close()


def test_tool_context_carries_task_profile_and_payload(world, settings, monkeypatch):
    seen = []

    def capture(self, task_id, profile, brief, ctx):
        seen.append((ctx.profile, dict(ctx.payload)))
        return TaskOutcome("done", "end_turn", 1, Decimal("0.01"), 0, 0, False, False)

    monkeypatch.setattr(ResearchWorker, "run", capture)
    R.run_once(
        settings,
        **_kw(world, client=_client(world["gap"].id), runner_factory=fake_runner_factory([], [])),
    )
    verify = [p for p in seen if p[0] == "verify-gap"]
    assert verify and verify[0][1]["gap_id"] == world["gap"].id
    assert {p[0] for p in seen} >= {"verify-gap", "map-sector"}


def test_critic_failure_still_applies_strategist_output(world, settings):
    client = _client(world["gap"].id)
    err = anthropic.APIConnectionError(request=httpx.Request("POST", "http://x"))
    client.messages._responses.insert(1, err)  # the Critic call fails
    del client.messages._responses[2]  # (the critic answer it replaced)
    summary = R.run_once(
        settings,
        **_kw(
            world,
            client=client,
            runner_factory=fake_runner_factory([_conversation() for _ in range(5)], []),
        ),
    )
    with world["factory"]() as s:
        gap = repo.get_gap(s, world["gap"].id)
        journal = repo.latest_journal(s)[0].tomorrow_md
        assert gap.score_total is not None and gap.last_assessed_run_id == repo.last_run(s).id
    assert gap.status != "verified"
    assert "critic skipped" in journal and "strategy skipped" not in journal
    assert summary.done == 6


def test_strategist_sees_only_changed_sectors(world, settings, monkeypatch):
    seen = {}
    real = Strategist.collect_inputs

    def spy(self, **kwargs):
        seen.update(kwargs)
        return real(self, **kwargs)

    monkeypatch.setattr(Strategist, "collect_inputs", spy)
    R.run_once(
        settings,
        **_kw(
            world,
            client=_client(world["gap"].id),
            runner_factory=fake_runner_factory([_conversation() for _ in range(5)], []),
        ),
    )
    assert seen["sector_slugs"] == ["pets"]


def test_strategist_skipped_when_fresh_facts_touch_no_sector(world, settings):
    later = NOW + timedelta(hours=1)
    with world["factory"]() as s:
        repo.upsert_fact(
            s,
            FactIn(
                claim="Kosovo population 1.6m", entity_type="stat", entity_key="pop", confidence=0.9
            ),
            run_id=None,
            observed_at=later,
        )
    client = FakeClient([FakeMessage(content=[text_block("Narrative.")])])

    def boom(**kwargs):
        raise RuntimeError("x")

    R.run_once(
        settings, **_kw(world, now=later, clock=lambda: later, client=client, runner_factory=boom)
    )
    assert not [c for c in client.messages.calls if "output_format" in c]


@pytest.mark.parametrize("cut", [None, "budget_stopped", "truncated"])
def test_completed_verify_gap_clears_the_founder_flag(world, settings, cut):
    gid = world["gap"].id
    with world["factory"]() as s:
        repo.set_setting(s, "flagged_gaps", [gid, 999])
        task = repo.enqueue_task(s, profile="verify-gap", payload={"gap_id": gid}, priority=90)
        outcome = TaskOutcome(
            "checked",
            "end_turn",
            3,
            Decimal("0.2"),
            0,
            5,
            cut == "truncated",
            cut == "budget_stopped",
        )
        R._apply_outcome(s, task, outcome, today=MONDAY, now=NOW)
        flags = repo.get_setting(s, "flagged_gaps")
    assert flags == ([999] if cut is None else [gid, 999])
