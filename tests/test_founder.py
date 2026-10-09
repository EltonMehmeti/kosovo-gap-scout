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
    assert (
        founder.set_gap_status(db_session, gap.id, "park", today=TODAY, now=NOW).status == "parked"
    )
    assert (
        founder.set_gap_status(db_session, gap.id, "kill", today=TODAY, now=NOW).status == "killed"
    )
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
    assert t.payload == {
        "sector": "pets",
        "sector_name": "Pets (vets, sitting, supplies)",
        "founder": True,
    }
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


def test_park_is_remembered_until_reopen_or_kill(db_session, gap):
    founder.set_gap_status(db_session, gap.id, "park", today=TODAY, now=NOW)
    assert founder.founder_parked(db_session) == [gap.id]
    founder.set_gap_status(db_session, gap.id, "reopen", today=TODAY, now=NOW)
    assert founder.founder_parked(db_session) == []
    founder.set_gap_status(db_session, gap.id, "park", today=TODAY, now=NOW)
    founder.set_gap_status(db_session, gap.id, "kill", today=TODAY, now=NOW)
    assert founder.founder_parked(db_session) == []
