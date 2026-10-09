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
        data={
            "profile": "map-sector",
            "sector": "pets",
            "gap_id": "",
            "theme": "",
            "priority": "80",
        },
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
    assert (
        f"#{q.id}" in r.text and "boom: &lt;b&gt;bad&lt;/b&gt;" in r.text and "foundation" in r.text
    )
    web.post(f"/tasks/{t.id}/retry")
    db_session.expire_all()
    assert db_session.get(type(t), t.id).status == "queued"
    again = web.post(f"/tasks/{t.id}/retry", follow_redirects=False)
    assert "err=" in again.headers["location"]


def test_journal_shows_scout_and_founder_entries(web, db_session):
    repo.write_journal(
        db_session,
        run_id=1,
        day=date(2026, 10, 9),
        did_md="mapped **pets**",
        learned_md="l",
        tomorrow_md="t",
    )
    repo.write_journal(
        db_session,
        run_id=None,
        day=date(2026, 10, 9),
        did_md="- Founder: kill gap #1",
        learned_md="",
        tomorrow_md="",
    )
    r = web.get("/journal")
    assert "<strong>pets</strong>" in r.text and "Founder: kill gap #1" in r.text
    assert "Run #1" in r.text and "Founder" in r.text
