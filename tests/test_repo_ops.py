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
    high = repo.enqueue_task(
        db_session, profile="map-sector", payload={"sector": "pets"}, priority=90
    )
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
    run = repo.start_run(
        db_session, day=DAY, phase="foundation", budget_cap_eur=Decimal("3"), started_at=NOW
    )
    repo.enqueue_task(db_session, profile="map-sector", payload={"sector": "pets"}, run_id=run.id)
    assert repo.task_exists_today(db_session, "map-sector", "sector", "pets", DAY)
    assert not repo.task_exists_today(db_session, "map-sector", "sector", "cars", DAY)


def test_costs_sum_per_explicit_day(db_session):
    run = repo.start_run(
        db_session, day=DAY, phase="foundation", budget_cap_eur=Decimal("3"), started_at=NOW
    )
    repo.record_cost(
        db_session,
        CostRecord("llm", "anthropic", "claude-sonnet-5-5", {"input_tokens": 1}, Decimal("0.10")),
        day=DAY,
        run_id=run.id,
    )
    repo.record_cost(
        db_session,
        CostRecord("search", "anthropic", None, {"web_search_requests": 2}, Decimal("0.02")),
        day=DAY,
        run_id=run.id,
    )
    repo.record_cost(
        db_session,
        CostRecord("places", "google", None, {"calls": 1}, Decimal("0")),
        day=date(2026, 10, 20),
        run_id=run.id,
    )
    assert repo.spent_on(db_session, DAY) == Decimal("0.120000")
    assert repo.spent_on(db_session, date(2026, 10, 20)) == Decimal("0.000000")
    assert repo.places_calls_in_month(db_session, date(2026, 10, 20)) == 1
    repo.finish_run(
        db_session,
        run,
        spent_eur=Decimal("0.12"),
        tasks_done=2,
        tasks_failed=0,
        summary_md="fine",
        finished_at=NOW,
    )
    assert repo.last_run(db_session).status == "done"


def test_journal_brief_scorecard_settings(db_session):
    repo.write_journal(db_session, run_id=1, day=DAY, did_md="a", learned_md="b", tomorrow_md="c")
    repo.write_journal(
        db_session, run_id=2, day=date(2026, 10, 20), did_md="d", learned_md="e", tomorrow_md="f"
    )
    assert [j.did_md for j in repo.latest_journal(db_session, limit=1)] == ["d"]
    repo.save_brief(db_session, run_id=1, day=DAY, markdown="# Brief")
    assert repo.latest_brief(db_session).markdown == "# Brief"
    repo.save_scorecard(db_session, day=DAY, metrics={"gaps": 1})
    repo.save_scorecard(db_session, day=DAY, metrics={"gaps": 2})
    assert repo.set_setting(db_session, "phase", {"value": "verification"}) is None
    assert repo.get_setting(db_session, "phase") == {"value": "verification"}
    assert repo.get_setting(db_session, "missing", "x") == "x"


def test_chart_snapshots(db_session):
    n = repo.save_chart_snapshot(
        db_session,
        store="apple",
        country="xk",
        chart="top-free",
        entries=[ChartEntryIn(1, "123", "Wolt"), ChartEntryIn(2, "456", "APTV")],
        captured_on=DAY,
    )
    assert n == 2
    # saving again the same day is idempotent
    assert (
        repo.save_chart_snapshot(
            db_session,
            store="apple",
            country="xk",
            chart="top-free",
            entries=[ChartEntryIn(1, "123", "Wolt")],
            captured_on=DAY,
        )
        == 0
    )
    rows = repo.chart_snapshot(
        db_session, store="apple", country="xk", chart="top-free", captured_on=DAY
    )
    assert [r.app_key for r in rows] == ["123", "456"]
    assert (
        repo.latest_chart_date(
            db_session, store="apple", country="xk", chart="top-free", before=date(2026, 10, 26)
        )
        == DAY
    )
    assert repo.app_ever_in_chart(db_session, store="apple", country="xk", app_key="456")
    assert not repo.app_ever_in_chart(db_session, store="play", country="xk", app_key="456")


def test_field_checks(db_session):
    repo.get_or_create_sector(db_session, "pets", "Pets")
    gap, _ = repo.propose_gap(db_session, title="Pet sitting", sector_slug="pets")
    fc = repo.add_field_check(
        db_session,
        gap_id=gap.id,
        question="Any pet sitters in Prizren?",
        why="confidence 0.4",
        due=date(2026, 10, 25),
    )
    assert [f.id for f in repo.open_field_checks(db_session)] == [fc.id]
    repo.answer_field_check(db_session, fc, answer="No, only vets", answered_at=NOW)
    assert repo.open_field_checks(db_session) == [] and fc.status == "answered"
