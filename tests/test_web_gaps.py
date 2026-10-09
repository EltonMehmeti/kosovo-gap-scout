from datetime import date

import pytest

from scout import founder
from scout.db import repo
from scout.seeds import seed_all

pytestmark = pytest.mark.db


@pytest.fixture
def gap(db_session):
    seed_all(db_session)
    g, _ = repo.propose_gap(
        db_session, title="Pet sitting", sector_slug="pets", hypothesis_md="**bold** idea"
    )
    return g


def test_pages_render_on_an_empty_database(web):
    for path in ("/gaps", "/field-checks"):
        assert web.get(path).status_code == 200


def test_board_and_detail(web, gap):
    r = web.get("/gaps")
    assert "Pet sitting" in r.text and f'action="/gaps/{gap.id}/status"' in r.text
    d = web.get(f"/gaps/{gap.id}")
    assert d.status_code == 200 and "<strong>bold</strong>" in d.text
    assert web.get("/gaps/999").status_code == 404


def test_park_kill_reopen_buttons(web, gap, db_session):
    r = web.post(f"/gaps/{gap.id}/status", data={"action": "park"}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"].startswith("/gaps?msg=")
    db_session.expire_all()
    assert repo.get_gap(db_session, gap.id).status == "parked"
    web.post(f"/gaps/{gap.id}/status", data={"action": "kill", "next": f"/gaps/{gap.id}"})
    db_session.expire_all()
    assert repo.get_gap(db_session, gap.id).status == "killed"
    bad = web.post(f"/gaps/{gap.id}/status", data={"action": "verified"}, follow_redirects=False)
    assert bad.status_code == 303 and "err=" in bad.headers["location"]


def test_verify_and_finalist_buttons(web, gap, db_session):
    web.post(f"/gaps/{gap.id}/flag")
    web.post(f"/gaps/{gap.id}/finalist")
    db_session.expire_all()
    assert founder.flagged(db_session) == [gap.id] and founder.finalists(db_session) == [gap.id]
    assert "Finalist" in web.get("/gaps").text
    web.post(f"/gaps/{gap.id}/flag", data={"unflag": "1"})
    db_session.expire_all()
    assert founder.flagged(db_session) == []


def test_next_cannot_redirect_off_site(web, gap):
    r = web.post(f"/gaps/{gap.id}/flag", data={"next": "https://evil.com"}, follow_redirects=False)
    assert r.headers["location"].startswith("/?msg=")


def test_answer_field_check_from_the_page(web, gap, db_session):
    fc = repo.add_field_check(
        db_session, gap_id=gap.id, question="Sitters in Prizren?", why="w", due=date(2026, 10, 11)
    )
    assert "Sitters in Prizren?" in web.get("/field-checks").text
    empty = web.post(f"/field-checks/{fc.id}/answer", data={"answer": " "}, follow_redirects=False)
    assert "err=" in empty.headers["location"]
    ok = web.post(f"/field-checks/{fc.id}/answer", data={"answer": "Two vets, no sitters"})
    assert ok.status_code == 200 and "verify-gap queued" in ok.text
    db_session.expire_all()
    assert repo.open_field_checks(db_session) == []
    assert repo.queued_tasks(db_session)[0].profile == "verify-gap"
