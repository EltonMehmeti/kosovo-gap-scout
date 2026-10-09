import re
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
    assert f"#{q.id}" in r.text and "boom: &lt;b&gt;bad&lt;/b&gt;" in r.text
    assert "Culture research" in r.text and "News scan" in r.text and "Retry" in r.text
    assert f"Run #{run.id}" in r.text and "Foundation" in r.text
    assert re.search(r'data-stat="failed">.*?<strong>1</strong>', r.text, re.S)
    assert re.search(r'data-stat="waiting">.*?<strong>1</strong>', r.text, re.S)
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
    assert "<strong>pets</strong>" in r.text and "Founder: kill gap #1" in r.text
    assert "Scout · run #1" in r.text and ">You</span>" in r.text


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
